import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  attachCharactersToScene,
  deleteSceneCharacterLink,
  listSceneCharacters,
  updateSceneCharacterLink,
} from "../api/sceneCharacters";
import { getAssetUrl } from "../api/client";
import { createMaterialSet, listMaterialSets } from "../api/materialSets";
import { usePresets } from "../hooks/usePresets";
import type { MaterialSet, SceneNodeCharacter, PresetOption } from "../shared/types";

interface CharacterSelectorProps {
  sceneId: string;
  projectId?: string;
  onUpdate?: () => void;
}

export default function CharacterSelector({ sceneId, projectId, onUpdate }: CharacterSelectorProps) {
  const navigate = useNavigate();
  const { data: presets, isLoading: presetsLoading } = usePresets(projectId);
  const [attachedCharacters, setAttachedCharacters] = useState<SceneNodeCharacter[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [attaching, setAttaching] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [materialSets, setMaterialSets] = useState<MaterialSet[]>([]);
  const [materialLoading, setMaterialLoading] = useState(false);
  const [materialBusy, setMaterialBusy] = useState<string | null>(null);

  useEffect(() => {
    loadAttachedCharacters();
  }, [sceneId]);

  useEffect(() => {
    if (!projectId) {
      setMaterialSets([]);
      return;
    }
    void loadMaterialSets(projectId);
  }, [projectId]);

  async function loadAttachedCharacters() {
    try {
      setLoading(true);
      const data = await listSceneCharacters(sceneId);
      setAttachedCharacters(data);
    } catch (error) {
      console.error("Failed to load characters:", error);
    } finally {
      setLoading(false);
    }
  }

  async function loadMaterialSets(projectIdValue: string) {
    try {
      setMaterialLoading(true);
      const items = await listMaterialSets(projectIdValue, { asset_type: "character" });
      setMaterialSets(items);
    } catch (error) {
      console.error("Failed to load material sets:", error);
    } finally {
      setMaterialLoading(false);
    }
  }

  async function handleAttach() {
    if (selectedIds.length === 0) return;

    try {
      setError(null);
      setAttaching(true);
      await attachCharactersToScene(sceneId, selectedIds);
      await loadAttachedCharacters();
      setSelectedIds([]);
      if (onUpdate) onUpdate();
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      setError(
        detail === "Character preset not found"
          ? "Пресет персонажа не найден. Создайте пресет в студии и импортируйте его в этот проект."
          : detail || "Не удалось привязать персонажей.",
      );
      console.error("Failed to attach characters:", error);
    } finally {
      setAttaching(false);
    }
  }

  function updateLocal(linkId: string, patch: Partial<SceneNodeCharacter>) {
    setAttachedCharacters((prev) => prev.map((c) => (c.id === linkId ? { ...c, ...patch } : c)));
  }

  async function patchLink(linkId: string, patch: Partial<SceneNodeCharacter>) {
    try {
      setError(null);
      const updated = await updateSceneCharacterLink(sceneId, linkId, patch);
      setAttachedCharacters((prev) => prev.map((c) => (c.id === linkId ? updated : c)));
      if (onUpdate) onUpdate();
    } catch (error) {
      console.error("Failed to update character link:", error);
    }
  }

  async function handleRemove(linkId: string) {
    try {
      setError(null);
      await deleteSceneCharacterLink(sceneId, linkId);
      setAttachedCharacters((prev) => prev.filter((c) => c.id !== linkId));
      if (onUpdate) onUpdate();
    } catch (error) {
      console.error("Failed to remove character link:", error);
    }
  }

  function toggleSelection(id: string) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  if (loading || presetsLoading || !presets) {
    return <div className="graph-panel">Загрузка персонажей...</div>;
  }

  const attachedIds = new Set(attachedCharacters.map((c: SceneNodeCharacter) => c.character_preset_id));
  const availableCharacters = presets.characters.filter((c: PresetOption) => !attachedIds.has(c.id));

  const inFrameCount = attachedCharacters.filter((c) => c.in_frame !== false).length;

  return (
    <div className="character-selector">
      <div className="character-selector-header">
        <h3>Пресеты персонажей</h3>
        <span className="graph-pill">{inFrameCount} в кадре</span>
      </div>
      {error && <div className="character-selector-error">{error}</div>}

      {attachedCharacters.length > 0 && (
        <div className="character-selector-section">
          <div className="character-selector-label">Привязаны</div>
          <div className="character-selector-list">
            {attachedCharacters.map((char) => {
              const preset = presets.characters.find((p: PresetOption) => p.id === char.character_preset_id);
              const thumb = preset?.preview_thumbnail_url ? getAssetUrl(preset.preview_thumbnail_url) : null;
              const availableSets = materialSets.filter((set) => set.asset_id === char.character_preset_id);
              return (
                <div
                  key={char.id}
                  className="character-selector-card"
                  style={{ display: "grid", gridTemplateColumns: "56px 1fr", gap: 12, alignItems: "start" }}
                >
                  {thumb ? (
                    <img
                      src={thumb}
                      alt={preset?.name || "персонаж"}
                      style={{ width: 56, height: 56, objectFit: "cover", borderRadius: 8 }}
                    />
                  ) : (
                    <div
                      style={{
                        width: 56,
                        height: 56,
                        borderRadius: 8,
                        background: "rgba(255,255,255,0.06)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontWeight: 700,
                      }}
                    >
                      {(preset?.name || "?").slice(0, 1).toUpperCase()}
                    </div>
                  )}

                  <div>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                      <strong>{preset?.name || char.character_preset_id}</strong>
                      <button className="secondary" onClick={() => handleRemove(char.id)}>Удалить</button>
                    </div>
                    {preset?.description ? <div className="muted" style={{ marginTop: 2 }}>{preset.description}</div> : null}

                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 8 }}>
                      <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        <input
                          type="checkbox"
                          checked={char.in_frame !== false}
                          onChange={(e) => patchLink(char.id, { in_frame: e.target.checked })}
                        />
                        В кадре
                      </label>

                      <label style={{ display: "flex", gap: 6, alignItems: "center" }}>Позиция<select
                          value={char.position || ""}
                          onChange={(e) => patchLink(char.id, { position: e.target.value || null })}
                        >
                          <option value="">Авто</option>
                          <option value="left">Слева</option>
                          <option value="center">По центру</option>
                          <option value="right">Справа</option>
                          <option value="foreground">Передний план</option>
                          <option value="background">Фон</option>
                        </select>
                      </label>
                    </div>
                    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 8 }}>
                      <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        Набор материалов
                        <select
                          value={char.material_set_id || ""}
                          onChange={(event) => patchLink(char.id, { material_set_id: event.target.value || null })}
                          disabled={materialLoading || !projectId}
                        >
                          <option value="">По умолчанию</option>
                          {availableSets.map((set) => (
                            <option key={set.id} value={set.id}>
                              {set.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        className="secondary"
                        type="button"
                        disabled={!projectId || materialBusy === char.id}
                        onClick={async () => {
                          if (!projectId) return;
                          const defaultLabel = preset?.name ? `${preset.name} v1` : "Персонаж v1";
                          const label = window.prompt("Название набора материалов", defaultLabel);
                          if (!label?.trim()) return;
                          try {
                            setMaterialBusy(char.id);
                            const created = await createMaterialSet(projectId, {
                              asset_type: "character",
                              asset_id: char.character_preset_id,
                              label: label.trim(),
                            });
                            setMaterialSets((prev) => [created, ...prev]);
                            await patchLink(char.id, { material_set_id: created.id });
                          } catch (error) {
                            console.error("Failed to create material set:", error);
                            setError("Не удалось создать набор материалов.");
                          } finally {
                            setMaterialBusy(null);
                          }
                        }}
                      >
                        {materialBusy === char.id ? "Создание..." : "Новый набор материалов"}
                      </button>
                    </div>

                    <textarea
                      value={char.scene_context || ""}
                      placeholder="Заметки по сцене (поза, выражение, действие, реквизит)"
                      onChange={(e) => updateLocal(char.id, { scene_context: e.target.value })}
                      onBlur={() => patchLink(char.id, { scene_context: char.scene_context || null })}
                      style={{ width: "100%", marginTop: 8, minHeight: 60 }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {availableCharacters.length > 0 && (
        <div className="character-selector-section">
          <div className="character-selector-label">Добавить персонажей</div>
          <div className="character-selector-list">
            {availableCharacters.map((char: PresetOption) => {
              const thumb = char.preview_thumbnail_url ? getAssetUrl(char.preview_thumbnail_url) : null;
              return (
                <label
                  key={char.id}
                  className={`character-selector-option ${selectedIds.includes(char.id) ? "selected" : ""}`}
                >
                  <input type="checkbox" checked={selectedIds.includes(char.id)} onChange={() => toggleSelection(char.id)} />
                  {thumb ? (
                    <img
                      src={thumb}
                      alt={char.name}
                      style={{ width: 32, height: 32, objectFit: "cover", borderRadius: 6, marginRight: 8 }}
                    />
                  ) : null}
                  <div>
                    <strong>{char.name}</strong>
                    {char.description && <span>{char.description}</span>}
                  </div>
                </label>
              );
            })}
          </div>
          <button
            onClick={handleAttach}
            disabled={attaching || selectedIds.length === 0}
            className="primary"
          >
            {attaching ? "Привязка..." : `Привязать ${selectedIds.length} персонаж(а)`}
          </button>
        </div>
      )}

      {availableCharacters.length === 0 && attachedCharacters.length === 0 && (
        <div className="character-selector-empty">
          <div className="muted">В этом проекте пока нет пресетов персонажей.</div>
          <div className="character-selector-actions">
            <button className="secondary" onClick={() => navigate("/studio")}>
              Создать в студии
            </button>
            {projectId && (
              <button className="secondary" onClick={() => navigate(`/projects/${projectId}/world`)}>
                Импортировать из студии
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
