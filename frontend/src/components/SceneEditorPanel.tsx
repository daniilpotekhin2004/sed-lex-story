import { useEffect, useMemo, useState } from "react";
import { listLegalConcepts } from "../api/legal";
import { updateScene } from "../api/scenario";
import { previewScenePrompt, generateSceneImage, getSceneImages } from "../api/generation";
import { listArtifacts, listLocations } from "../api/world";
import CharacterSelector from "./CharacterSelector";
import PromptWarning from "./PromptWarning";
import SDOptionsPanel from "./SDOptionsPanel";
import type { Artifact, LegalConcept, Location, PromptBundle, SceneNode, ImageVariant } from "../shared/types";
import { trackEvent } from "../utils/tracker";
import { waitForGenerationJob } from "../utils/waitForGenerationJob";
import { useGenerationJobStore } from "../hooks/useGenerationJobStore";

type Props = {
  scene: SceneNode;
  projectId?: string;
  onSceneUpdated?: (scene: SceneNode) => void;
  onImagesUpdated?: (images: ImageVariant[]) => void;
  showWritingFields?: boolean;
};

export default function SceneEditorPanel({
  scene,
  projectId,
  onSceneUpdated,
  onImagesUpdated,
  showWritingFields = true,
}: Props) {
  const [form, setForm] = useState({
    title: scene.title,
    content: scene.content,
    synopsis: scene.synopsis || "",
    scene_type: scene.scene_type,
    shot: (scene.context?.shot as string) || "",
    legal_concept_ids: (scene.legal_concepts || []).map((c) => c.id),
    location_id: scene.location_id || "",
    location_overrides: JSON.stringify(scene.location_overrides || {}, null, 2),
    artifacts: (scene.artifacts || []).map((a) => a.artifact_id),
  });
  const [legal, setLegal] = useState<LegalConcept[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [saving, setSaving] = useState(false);
  const [prompt, setPrompt] = useState<PromptBundle | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [overrideError, setOverrideError] = useState<string | null>(null);
  const upsertJob = useGenerationJobStore((s) => s.upsert);

  useEffect(() => {
    setForm({
      title: scene.title,
      content: scene.content,
      synopsis: scene.synopsis || "",
      scene_type: scene.scene_type,
      shot: (scene.context?.shot as string) || "",
      legal_concept_ids: (scene.legal_concepts || []).map((c) => c.id),
      location_id: scene.location_id || "",
      location_overrides: JSON.stringify(scene.location_overrides || {}, null, 2),
      artifacts: (scene.artifacts || []).map((a) => a.artifact_id),
    });
    refreshPrompt();
    refreshImages();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene]);

  useEffect(() => {
    loadLegal();
  }, []);

  useEffect(() => {
    if (!projectId) return;
    void loadWorld(projectId);
  }, [projectId]);

  async function loadLegal() {
    try {
      const items = await listLegalConcepts();
      setLegal(items);
    } catch (error) {
      console.error("Failed to load legal concepts", error);
    }
  }

  async function loadWorld(projectIdValue: string) {
    try {
      const [locs, arts] = await Promise.all([listLocations(projectIdValue), listArtifacts(projectIdValue)]);
      setLocations(locs);
      setArtifacts(arts);
    } catch (error) {
      console.error("Failed to load world library", error);
    }
  }

  async function refreshPrompt() {
    try {
      const bundle = await previewScenePrompt(scene.id);
      setPrompt(bundle);
    } catch (error) {
      console.error("Failed to preview prompt", error);
    }
  }

  async function refreshImages() {
    try {
      const variants = await getSceneImages(scene.id);
      onImagesUpdated?.(variants);
    } catch (error) {
      console.error("Failed to load images", error);
    }
  }

  async function handleSave() {
    try {
      setSaving(true);
      const overrides = parseOverrides(form.location_overrides);
      if (overrides === undefined) {
        setSaving(false);
        return;
      }
      const payload: Parameters<typeof updateScene>[1] = {
        legal_concept_ids: form.legal_concept_ids,
        location_id: form.location_id || null,
        context: {
          ...(scene.context || {}),
          // Empty string means "auto" (PromptEngine will ignore it)
          shot: form.shot || undefined,
        },
        location_overrides: overrides,
        artifacts: form.artifacts.map((artifactId) => ({ artifact_id: artifactId })),
      };
      if (showWritingFields) {
        payload.title = form.title;
        payload.content = form.content;
        payload.synopsis = form.synopsis;
        payload.scene_type = form.scene_type as "story" | "decision";
      }
      const updated = await updateScene(scene.id, payload);
      onSceneUpdated?.(updated);
      trackEvent("scene_saved", { sceneId: scene.id, legalConcepts: form.legal_concept_ids.length });
      await refreshPrompt();
    } catch (error) {
      console.error("Failed to save scene", error);
    } finally {
      setSaving(false);
    }
  }

  async function handleGenerate() {
    try {
      const job = await generateSceneImage(scene.id, { use_prompt_engine: true, num_variants: 1 });
      setJobStatus(job.status);
      upsertJob(job);
      trackEvent("scene_generate", { sceneId: scene.id, jobId: job.id });
      const completed = await waitForGenerationJob(job.id, {
        intervalMs: 2000,
        maxAttempts: 60,
        onUpdate: (updated) => setJobStatus(updated.status),
      });
      if (completed.status === "done") {
        await refreshImages();
      } else if (completed.status === "failed") {
        setJobStatus("failed");
      } else {
        setJobStatus(completed.status || "timeout");
      }
    } catch (error) {
      console.error("Failed to generate", error);
    }
  }

  const legalOptions = useMemo(() => legal || [], [legal]);
  const locationOptions = useMemo(() => locations || [], [locations]);
  const artifactOptions = useMemo(() => artifacts || [], [artifacts]);
  const artifactSet = useMemo(() => new Set(form.artifacts), [form.artifacts]);
  const jobStatusLabel = useMemo(() => {
    if (!jobStatus) return null;
    if (jobStatus === "queued") return "Ожидание в очереди";
    if (jobStatus === "running") return "Рендеринг";
    if (jobStatus === "done") return "Готово";
    if (jobStatus === "failed") return "Ошибка";
    if (jobStatus === "timeout") return "Тайм-аут";
    return jobStatus;
  }, [jobStatus]);

  function parseOverrides(raw: string): Record<string, unknown> | null | undefined {
    if (!raw.trim()) {
      setOverrideError(null);
      return null;
    }
    try {
      const parsed = JSON.parse(raw);
      setOverrideError(null);
      return parsed;
    } catch (err) {
      setOverrideError("Переопределения локации должны быть корректным JSON.");
      return undefined;
    }
  }

  return (
    <div className="graph-editor-panel">
      {showWritingFields && (
        <>
          <div className="graph-form-grid">
            <label className="graph-field">
              <span>Заголовок</span>
              <input
                className="graph-input"
                value={form.title}
                onChange={(event) => setForm({ ...form, title: event.target.value })}
              />
            </label>
            <label className="graph-field">
              <span>Тип сцены</span>
              <select
                className="graph-select"
                value={form.scene_type}
                onChange={(event) => setForm({ ...form, scene_type: event.target.value as "story" | "decision" })}
              >
                <option value="story">История</option>
                <option value="decision">Решение</option>
              </select>
            </label>
          </div>

          <label className="graph-field">
            <span>Синопсис</span>
            <textarea
              rows={2}
              className="graph-textarea"
              value={form.synopsis}
              onChange={(event) => setForm({ ...form, synopsis: event.target.value })}
            />
          </label>

          <label className="graph-field">
            <span>Содержание</span>
            <textarea
              rows={5}
              className="graph-textarea"
              value={form.content}
              onChange={(event) => setForm({ ...form, content: event.target.value })}
            />
          </label>
        </>
      )}

      <div className="graph-section">
        <div className="graph-section-title">Правовые понятия</div>
        <div className="graph-tag-grid">
          {legalOptions.map((concept) => {
            const checked = form.legal_concept_ids.includes(concept.id);
            return (
              <label key={concept.id} className={`graph-tag ${checked ? "active" : ""}`}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => {
                    setForm((prev) => ({
                      ...prev,
                      legal_concept_ids: checked
                        ? prev.legal_concept_ids.filter((id) => id !== concept.id)
                        : [...prev.legal_concept_ids, concept.id],
                    }));
                  }}
                />
                <span>{concept.title}</span>
              </label>
            );
          })}
        </div>
      </div>

      <div className="graph-section">
        <div className="graph-section-title">Локация</div>
        <select
          className="graph-select"
          value={form.location_id}
          onChange={(event) => setForm({ ...form, location_id: event.target.value })}
        >
          <option value="">Нет локации</option>
          {locationOptions.map((location) => (
            <option key={location.id} value={location.id}>
              {location.name}
            </option>
          ))}
        </select>
        {form.location_id && (
          <textarea
            rows={3}
            className="graph-textarea"
            placeholder="Переопределения локации (JSON)"
            value={form.location_overrides}
            onChange={(event) => setForm({ ...form, location_overrides: event.target.value })}
          />
        )}
        {overrideError && <div className="graph-error">{overrideError}</div>}
      </div>

      <div className="graph-section">
        <div className="graph-section-title">Пресет кадра</div>
        <select
          className="graph-select"
          value={form.shot}
          onChange={(event) => setForm({ ...form, shot: event.target.value })}
        >
          <option value="">Авто</option>
          <option value="establishing">Общий план (широкий)</option>
          <option value="medium">Средний план</option>
          <option value="portrait">Портрет (крупный)</option>
          <option value="action">Действие</option>
        </select>
        <div className="muted" style={{ marginTop: 6 }}>
          Это подсказывает Prompt Engine, как кадрировать изображение.
        </div>
      </div>

      <div className="graph-section">
        <div className="graph-section-title">Артефакты</div>
        {artifactOptions.length === 0 ? (
          <div className="muted">Артефактов пока нет.</div>
        ) : (
          <div className="graph-tag-grid">
            {artifactOptions.map((artifact) => {
              const checked = artifactSet.has(artifact.id);
              return (
                <label key={artifact.id} className={`graph-tag ${checked ? "active" : ""}`}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      setForm((prev) => ({
                        ...prev,
                        artifacts: checked
                          ? prev.artifacts.filter((id) => id !== artifact.id)
                          : [...prev.artifacts, artifact.id],
                      }));
                    }}
                  />
                  <span>{artifact.name}</span>
                </label>
              );
            })}
          </div>
        )}
      </div>

      <div className="graph-actions">
        <button onClick={handleSave} disabled={saving} className="primary">
          {saving ? "Сохранение..." : "Сохранить сцену"}
        </button>
        <button onClick={handleGenerate} className="secondary">Генерировать</button>
        {jobStatusLabel && <span className="muted">Генерация: {jobStatusLabel}</span>}
      </div>

      <CharacterSelector sceneId={scene.id} projectId={projectId} onUpdate={refreshPrompt} />

      <div className="graph-panel graph-panel-tight">
        <div className="graph-panel-header">
          <h3>Настройки SD</h3>
        </div>
        <SDOptionsPanel compact />
      </div>

      <div className="graph-panel graph-panel-tight">
        <div className="graph-panel-header">
          <h3>Предпросмотр промпта</h3>
        </div>
        {prompt ? (
          <div className="graph-prompt">
            <div>
              <strong>Промпт</strong>
              <span>{prompt.prompt}</span>
              <PromptWarning prompt={prompt.prompt} />
            </div>
            {prompt.negative_prompt && (
              <div>
                <strong>Негативный</strong>
                <span>{prompt.negative_prompt}</span>
              </div>
            )}
            <pre className="graph-code">{JSON.stringify(prompt.config, null, 2)}</pre>
          </div>
        ) : (
          <div className="muted">Нет предпросмотра.</div>
        )}
      </div>
    </div>
  );
}
