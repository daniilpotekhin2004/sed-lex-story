import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { listProjects, createProject, deleteProject, updateProject } from "../api/projects";
import type { Project } from "../shared/types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({ name: "", description: "" });
  const navigate = useNavigate();

  useEffect(() => {
    loadProjects();
  }, []);

  async function loadProjects() {
    try {
      setLoading(true);
      const data = await listProjects();
      setProjects(data);
    } catch (error) {
      console.error("Failed to load projects:", error);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate() {
    if (!formData.name.trim()) return;
    
    try {
      setCreating(true);
      const project = await createProject({
        name: formData.name,
        description: formData.description || null,
      });
      setProjects([...projects, project]);
      setFormData({ name: "", description: "" });
      setShowForm(false);
    } catch (error) {
      console.error("Failed to create project:", error);
    } finally {
      setCreating(false);
    }
  }

  if (loading) {
    return <div className="page">Загрузка проектов...</div>;
  }

  function startRename(project: Project) {
    setRenamingProjectId(project.id);
    setRenameValue(project.name);
  }

  function cancelRename() {
    setRenamingProjectId(null);
    setRenameValue("");
  }

  async function submitRename(project: Project) {
    const nextName = renameValue.trim();
    if (!nextName) {
      cancelRename();
      return;
    }
    if (nextName === project.name) {
      cancelRename();
      return;
    }
    try {
      setRenaming(true);
      const updated = await updateProject(project.id, { name: nextName });
      setProjects((prev) => prev.map((item) => (item.id === project.id ? updated : item)));
      cancelRename();
    } catch (error) {
      console.error("Failed to rename project:", error);
    } finally {
      setRenaming(false);
    }
  }

  async function handleDelete(project: Project) {
    if (!window.confirm(`Архивировать проект "${project.name}"?`)) {
      return;
    }
    const snapshot = projects;
    setProjects((prev) => prev.filter((item) => item.id !== project.id));
    if (renamingProjectId === project.id) {
      cancelRename();
    }
    try {
      setDeletingProjectId(project.id);
      await deleteProject(project.id);
    } catch (error) {
      console.error("Failed to archive project:", error);
      setProjects(snapshot);
      window.alert("Не удалось архивировать проект. Проект возвращён в список.");
    } finally {
      setDeletingProjectId(null);
    }
  }

  return (
    <div className="page projects-shell">
      <div className="projects-header">
        <h1>Проекты</h1>
        <button
          type="button"
          onClick={() => setShowForm(!showForm)}
          className={showForm ? "ghost" : "primary"}
        >
          {showForm ? "Отмена" : "Новый проект"}
        </button>
      </div>

      {showForm && (
        <section className="card projects-create-card">
          <div className="card-header">
            <h2>Создать проект</h2>
          </div>
          <label className="field">
            <span>Название</span>
            <input
              className="input"
              type="text"
              placeholder="Название проекта"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
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
              onClick={handleCreate}
              disabled={creating || !formData.name.trim()}
            >
              {creating ? "Создание..." : "Создать"}
            </button>
          </div>
        </section>
      )}

      <div className="projects-grid">
        {projects.map((project) => (
          <article key={project.id} className="projects-card">
            {renamingProjectId === project.id ? (
              <input
                className="input projects-title-input"
                autoFocus
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onBlur={() => void submitRename(project)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void submitRename(project);
                  }
                  if (e.key === "Escape") {
                    e.preventDefault();
                    cancelRename();
                  }
                }}
                disabled={renaming}
              />
            ) : (
              <button
                type="button"
                className="ghost projects-card-title projects-card-title-button"
                onClick={() => startRename(project)}
                title="Переименовать проект"
              >
                {project.name}
              </button>
            )}
            <div className="projects-card-desc">
              {project.description?.trim() || "Описание пока не задано"}
            </div>
            <div className="projects-card-actions">
              <button type="button" className="secondary" onClick={() => navigate(`/projects/${project.id}`)}>
                Открыть
              </button>
              <button
                type="button"
                className="ghost danger"
                onClick={() => void handleDelete(project)}
                disabled={deletingProjectId === project.id}
              >
                {deletingProjectId === project.id ? "Архивация..." : "Удалить"}
              </button>
            </div>
          </article>
        ))}
      </div>

      {projects.length === 0 && !showForm && (
        <div className="projects-empty">
          Проектов пока нет. Создайте первый проект, чтобы начать!
        </div>
      )}
    </div>
  );
}
