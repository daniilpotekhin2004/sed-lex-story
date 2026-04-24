import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { deleteProject, getProject, getProjectVoiceover, updateProject } from "../api/projects";
import { createGraph, deleteGraph, updateGraph } from "../api/scenario";
import ProjectReleasePanel from "../components/project/ProjectReleasePanel";
import type { Project, ProjectVoiceoverSummary, ScenarioGraph } from "../shared/types";

type GuideStep = {
  id: string;
  title: string;
  note: string;
  actionLabel: string;
  path: string;
};

const GUIDE_STORAGE_PREFIX = "lwq_project_guide";

function readGuideMarks(projectId: string): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(`${GUIDE_STORAGE_PREFIX}_${projectId}`);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

function writeGuideMarks(projectId: string, value: Record<string, boolean>) {
  try {
    localStorage.setItem(`${GUIDE_STORAGE_PREFIX}_${projectId}`, JSON.stringify(value));
  } catch {
    // ignore storage errors
  }
}

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [graphs, setGraphs] = useState<ScenarioGraph[]>([]);
  const [voiceSummary, setVoiceSummary] = useState<ProjectVoiceoverSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({ title: "", description: "" });
  const [creating, setCreating] = useState(false);
  const [editingProjectName, setEditingProjectName] = useState(false);
  const [projectNameDraft, setProjectNameDraft] = useState("");
  const [updatingProjectName, setUpdatingProjectName] = useState(false);
  const [archivingProject, setArchivingProject] = useState(false);
  const [editingGraphId, setEditingGraphId] = useState<string | null>(null);
  const [graphDraft, setGraphDraft] = useState({ title: "", description: "" });
  const [updatingGraphId, setUpdatingGraphId] = useState<string | null>(null);
  const [archivingGraphId, setArchivingGraphId] = useState<string | null>(null);
  const [guideMarks, setGuideMarks] = useState<Record<string, boolean>>({});
  const navigate = useNavigate();

  useEffect(() => {
    if (projectId) {
      setGuideMarks(readGuideMarks(projectId));
      void loadProject();
    }
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;
    writeGuideMarks(projectId, guideMarks);
  }, [guideMarks, projectId]);

  async function loadProject() {
    if (!projectId) return;
    try {
      setLoading(true);
      const data = await getProject(projectId);
      setProject(data);
      setGraphs(data?.graphs || []);
      setProjectNameDraft(data?.name || "");

      try {
        const voice = await getProjectVoiceover(projectId);
        setVoiceSummary(voice.summary);
      } catch {
        setVoiceSummary(null);
      }
    } catch (error) {
      console.error("Failed to load project:", error);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateGraph() {
    if (!formData.title.trim() || !projectId) return;

    try {
      setCreating(true);
      const graph = await createGraph(projectId, {
        title: formData.title,
        description: formData.description || null,
      });
      setGraphs([...graphs, graph]);
      setFormData({ title: "", description: "" });
      setShowForm(false);
    } catch (error) {
      console.error("Failed to create graph:", error);
    } finally {
      setCreating(false);
    }
  }

  function startProjectRename() {
    if (!project) return;
    setProjectNameDraft(project.name);
    setEditingProjectName(true);
  }

  function cancelProjectRename() {
    setEditingProjectName(false);
    setProjectNameDraft(project?.name || "");
  }

  async function saveProjectRename() {
    if (!project || !projectId) return;
    const nextName = projectNameDraft.trim();
    if (!nextName || nextName === project.name) {
      cancelProjectRename();
      return;
    }
    try {
      setUpdatingProjectName(true);
      const updated = await updateProject(projectId, { name: nextName });
      setProject((prev) => (prev ? { ...prev, ...updated } : prev));
      setProjectNameDraft(updated.name);
      setEditingProjectName(false);
    } catch (error) {
      console.error("Failed to rename project:", error);
    } finally {
      setUpdatingProjectName(false);
    }
  }

  async function handleArchiveProject() {
    if (!projectId || !project) return;
    if (!window.confirm(`Архивировать проект "${project.name}"?`)) {
      return;
    }
    try {
      setArchivingProject(true);
      await deleteProject(projectId);
      navigate("/projects");
    } catch (error) {
      console.error("Failed to archive project:", error);
    } finally {
      setArchivingProject(false);
    }
  }

  function startGraphEdit(graph: ScenarioGraph) {
    setEditingGraphId(graph.id);
    setGraphDraft({
      title: graph.title || "",
      description: graph.description || "",
    });
  }

  function cancelGraphEdit() {
    setEditingGraphId(null);
    setGraphDraft({ title: "", description: "" });
  }

  async function saveGraphEdit(graph: ScenarioGraph) {
    const nextTitle = graphDraft.title.trim();
    const nextDescription = graphDraft.description.trim();
    if (!nextTitle) {
      cancelGraphEdit();
      return;
    }
    if (nextTitle === graph.title && nextDescription === (graph.description || "")) {
      cancelGraphEdit();
      return;
    }
    try {
      setUpdatingGraphId(graph.id);
      const updated = await updateGraph(graph.id, {
        title: nextTitle,
        description: nextDescription || null,
      });
      setGraphs((prev) => prev.map((item) => (item.id === graph.id ? { ...item, ...updated } : item)));
      cancelGraphEdit();
    } catch (error) {
      console.error("Failed to update graph:", error);
    } finally {
      setUpdatingGraphId(null);
    }
  }

  async function handleArchiveGraph(graph: ScenarioGraph) {
    if (!window.confirm(`Архивировать граф "${graph.title}"?`)) {
      return;
    }
    try {
      setArchivingGraphId(graph.id);
      await deleteGraph(graph.id);
      setGraphs((prev) => prev.filter((item) => item.id !== graph.id));
      if (editingGraphId === graph.id) {
        cancelGraphEdit();
      }
    } catch (error) {
      console.error("Failed to archive graph:", error);
    } finally {
      setArchivingGraphId(null);
    }
  }

  const firstGraph = graphs[0] || null;
  const autoGuideDone = useMemo(() => {
    const hasGraphs = graphs.length > 0;
    const hasApprovedVoice = (voiceSummary?.approved_lines || 0) > 0;
    return {
      graph_ready: hasGraphs,
      voice_ready: hasApprovedVoice,
    };
  }, [graphs.length, voiceSummary?.approved_lines]);

  const guideSteps = useMemo<GuideStep[]>(() => {
    if (!projectId) return [];
    return [
      {
        id: "story_ready",
        title: "Шаг 1. Сформируйте основу сюжета",
        note: "Заполните мастер: от декомпозиции до критической проверки.",
        actionLabel: "Открыть мастер",
        path: `/projects/${projectId}/wizard`,
      },
      {
        id: "world_ready",
        title: "Шаг 2. Подготовьте библиотеку мира",
        note: "Уточните персонажей, локации и материалы в проектной библиотеке.",
        actionLabel: "Открыть библиотеку",
        path: `/projects/${projectId}/world?mode=creative&tab=characters`,
      },
      {
        id: "graph_ready",
        title: "Шаг 3. Соберите сценарный граф",
        note: "Создайте ветвления и проверьте порядок сцен в редакторе.",
        actionLabel: firstGraph ? "Открыть граф" : "Создать граф",
        path: firstGraph ? `/projects/${projectId}/graphs/${firstGraph.id}` : `/projects/${projectId}`,
      },
      {
        id: "voice_ready",
        title: "Шаг 4. Утвердите озвучку",
        note: "Сгенерируйте варианты, подтвердите реплики и сохраните итоговые файлы в проект.",
        actionLabel: "Открыть озвучку",
        path: `/projects/${projectId}/voiceover`,
      },
      {
        id: "playtest_ready",
        title: "Шаг 5. Пройдите проект в плеере",
        note: "Проверьте ветвления и соответствие аудио нужным экранам.",
        actionLabel: "Открыть плеер",
        path: `/player/${projectId}`,
      },
    ];
  }, [firstGraph, projectId]);

  const completedCount = useMemo(
    () =>
      guideSteps.filter((step) => {
        if (step.id === "graph_ready") return autoGuideDone.graph_ready || Boolean(guideMarks[step.id]);
        if (step.id === "voice_ready") return autoGuideDone.voice_ready || Boolean(guideMarks[step.id]);
        return Boolean(guideMarks[step.id]);
      }).length,
    [autoGuideDone.graph_ready, autoGuideDone.voice_ready, guideMarks, guideSteps],
  );

  const nextStep = useMemo(() => {
    return guideSteps.find((step) => {
      if (step.id === "graph_ready") return !(autoGuideDone.graph_ready || guideMarks[step.id]);
      if (step.id === "voice_ready") return !(autoGuideDone.voice_ready || guideMarks[step.id]);
      return !guideMarks[step.id];
    });
  }, [autoGuideDone.graph_ready, autoGuideDone.voice_ready, guideMarks, guideSteps]);

  function stepDone(stepId: string) {
    if (stepId === "graph_ready") return autoGuideDone.graph_ready || Boolean(guideMarks[stepId]);
    if (stepId === "voice_ready") return autoGuideDone.voice_ready || Boolean(guideMarks[stepId]);
    return Boolean(guideMarks[stepId]);
  }

  function toggleStep(stepId: string) {
    setGuideMarks((prev) => {
      const autoDone =
        stepId === "graph_ready"
          ? autoGuideDone.graph_ready
          : stepId === "voice_ready"
            ? autoGuideDone.voice_ready
            : false;
      const currentDone = autoDone || Boolean(prev[stepId]);
      return {
        ...prev,
        [stepId]: !currentDone,
      };
    });
  }

  if (loading) {
    return <div className="page">Загрузка проекта...</div>;
  }

  if (!project) {
    return <div className="page">Проект не найден</div>;
  }

  return (
    <div className="page project-detail-shell">
      <button type="button" onClick={() => navigate("/projects")} className="secondary project-detail-back">
        ← Назад к проектам
      </button>

      <section className="card project-detail-hero">
        <div className="project-detail-title">
          {editingProjectName ? (
            <div className="project-inline-edit">
              <input
                className="input"
                autoFocus
                value={projectNameDraft}
                onChange={(e) => setProjectNameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void saveProjectRename();
                  }
                  if (e.key === "Escape") {
                    e.preventDefault();
                    cancelProjectRename();
                  }
                }}
                disabled={updatingProjectName}
              />
              <button type="button" className="secondary" onClick={() => void saveProjectRename()}>
                {updatingProjectName ? "Сохранение..." : "Сохранить"}
              </button>
              <button type="button" className="ghost" onClick={cancelProjectRename} disabled={updatingProjectName}>
                Отмена
              </button>
            </div>
          ) : (
            <button type="button" className="ghost project-editable-title" onClick={startProjectRename}>
              {project.name}
            </button>
          )}
          {project.description && <p className="muted">{project.description}</p>}
        </div>
        <div className="project-detail-actions">
          <button
            type="button"
            className="primary"
            onClick={() => navigate(`/player/${project.id}`)}
          >
            Играть историю
          </button>
          <button type="button" onClick={() => navigate(`/projects/${project.id}/wizard`)} className="secondary">
            Мастер сюжета
          </button>
          <button type="button" onClick={() => navigate(`/projects/${project.id}/world`)} className="secondary">
            Библиотека мира
          </button>
          <button
            type="button"
            onClick={() => navigate(`/projects/${project.id}/world?mode=creative&tab=characters`)}
            className="secondary"
          >
            Творческая разработка
          </button>
          <button type="button" onClick={() => navigate(`/projects/${project.id}/voiceover`)} className="secondary">
            Озвучка проекта
          </button>
          <button
            type="button"
            onClick={() => void handleArchiveProject()}
            className="ghost danger"
            disabled={archivingProject}
          >
            {archivingProject ? "Архивация..." : "Удалить проект"}
          </button>
        </div>
      </section>

      <section className="card project-guide" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <h2>Интерактивный гайд по проекту</h2>
          <span className="pill">
            {completedCount}/{guideSteps.length}
          </span>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          Последовательно проведёт через формирование квеста и озвучки.
        </p>

        <div className="project-guide-list">
          {guideSteps.map((step) => {
            const done = stepDone(step.id);
            return (
              <article key={step.id} className={`project-guide-step ${done ? "done" : ""}`}>
                <div className="project-guide-step-main">
                  <div className="project-guide-step-title">{step.title}</div>
                  <div className="project-guide-step-note">{step.note}</div>
                </div>
                <div className="project-guide-step-actions">
                  <button className="secondary" onClick={() => navigate(step.path)}>
                    {step.actionLabel}
                  </button>
                  <label className="wizard-checkbox" style={{ marginBottom: 0 }}>
                    <input type="checkbox" checked={done} onChange={() => toggleStep(step.id)} />
                    <span>{done ? "Готово" : "Отметить"}</span>
                  </label>
                </div>
              </article>
            );
          })}
        </div>

        {nextStep ? (
          <div className="actions" style={{ marginTop: 12 }}>
            <button className="primary" onClick={() => navigate(nextStep.path)}>
              Продолжить: {nextStep.title}
            </button>
          </div>
        ) : (
          <div className="wizard-alert warn" style={{ marginTop: 12 }}>
            Гайд пройден. Можно запускать финальный плейтест.
          </div>
        )}
      </section>

      <ProjectReleasePanel projectId={project.id} graphs={graphs} />

      <div className="project-detail-graphs-header">
        <h2>Сценарные графы</h2>
        <button
          type="button"
          onClick={() => setShowForm(!showForm)}
          className={showForm ? "ghost" : "primary"}
        >
          {showForm ? "Отмена" : "Новый граф"}
        </button>
      </div>

      {showForm && (
        <section className="card project-detail-create-graph">
          <div className="card-header">
            <h3>Создать сценарный граф</h3>
          </div>
          <label className="field">
            <span>Название</span>
            <input
              className="input"
              type="text"
              placeholder="Название графа"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Описание</span>
            <textarea
              className="input"
              placeholder="Описание (необязательно)"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={3}
            />
          </label>
          <div className="actions">
            <button
              className="primary"
              type="button"
              onClick={handleCreateGraph}
              disabled={creating || !formData.title.trim()}
            >
              {creating ? "Создание..." : "Создать граф"}
            </button>
          </div>
        </section>
      )}

      <div className="project-detail-graphs-grid">
        {graphs.map((graph) => (
          <article key={graph.id} className="card project-detail-graph-card">
            {editingGraphId === graph.id ? (
              <div className="project-inline-edit project-graph-inline-edit">
                <input
                  className="input"
                  autoFocus
                  value={graphDraft.title}
                  onChange={(e) => setGraphDraft((prev) => ({ ...prev, title: e.target.value }))}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void saveGraphEdit(graph);
                    }
                    if (e.key === "Escape") {
                      e.preventDefault();
                      cancelGraphEdit();
                    }
                  }}
                  disabled={updatingGraphId === graph.id}
                />
                <textarea
                  className="input"
                  rows={3}
                  value={graphDraft.description}
                  onChange={(e) => setGraphDraft((prev) => ({ ...prev, description: e.target.value }))}
                  disabled={updatingGraphId === graph.id}
                />
                <div className="project-inline-edit-actions">
                  <button type="button" className="secondary" onClick={() => void saveGraphEdit(graph)}>
                    {updatingGraphId === graph.id ? "Сохранение..." : "Сохранить"}
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    onClick={cancelGraphEdit}
                    disabled={updatingGraphId === graph.id}
                  >
                    Отмена
                  </button>
                </div>
              </div>
            ) : (
              <>
                <button
                  type="button"
                  className="ghost project-graph-editable-title"
                  onClick={() => startGraphEdit(graph)}
                  title="Редактировать название и описание"
                >
                  {graph.title}
                </button>
                {graph.description ? (
                  <button
                    type="button"
                    className="ghost project-graph-editable-description"
                    onClick={() => startGraphEdit(graph)}
                    title="Редактировать название и описание"
                  >
                    {graph.description}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="ghost project-graph-editable-description project-graph-editable-placeholder"
                    onClick={() => startGraphEdit(graph)}
                    title="Добавить описание графа"
                  >
                    Добавить описание
                  </button>
                )}
              </>
            )}
            <div className="project-detail-graph-meta">
              {graph.scenes?.length || 0} сцен • {graph.edges?.length || 0} переходов
            </div>
            <div className="project-detail-graph-actions">
              <button
                type="button"
                className="secondary"
                onClick={() => navigate(`/projects/${projectId}/graphs/${graph.id}`)}
              >
                Редактировать
              </button>
              <button
                type="button"
                className="primary"
                onClick={() => navigate(`/player/${projectId}?graph=${graph.id}`)}
              >
                Играть
              </button>
              <button
                type="button"
                className="ghost"
                onClick={() => navigate(`/projects/${projectId}/graphs/${graph.id}/draft-runner`)}
              >
                Черновой прогон
              </button>
              <button
                type="button"
                className="ghost danger"
                onClick={() => void handleArchiveGraph(graph)}
                disabled={archivingGraphId === graph.id}
              >
                {archivingGraphId === graph.id ? "Архивация..." : "Удалить граф"}
              </button>
            </div>
          </article>
        ))}
      </div>

      {graphs.length === 0 && !showForm && (
        <div className="project-detail-empty muted">
          Сценарных графов пока нет. Создайте первый граф, чтобы начать историю!
        </div>
      )}
    </div>
  );
}
