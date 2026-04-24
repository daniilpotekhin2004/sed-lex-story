import { useEffect, useMemo, useState } from "react";
import {
  archiveProjectRelease,
  listProjectReleaseCandidateUsers,
  listProjectReleases,
  publishProjectRelease,
  replaceProjectReleaseAccess,
} from "../../api/projectReleases";
import { useAuth } from "../../auth/useAuth";
import type { ProjectRelease, ReleaseAssignedUser, ScenarioGraph } from "../../shared/types";

type Props = {
  projectId: string;
  graphs: ScenarioGraph[];
};

function toUserAccessDrafts(items: ProjectRelease[]) {
  return Object.fromEntries(items.map((release) => [release.id, release.assigned_users.map((user) => user.id)]));
}

function toCohortDrafts(items: ProjectRelease[]) {
  return Object.fromEntries(items.map((release) => [release.id, release.assigned_cohorts.join(", ")]));
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  return new Date(value).toLocaleString("ru-RU");
}

function isSameSelection(left: string[], right: string[]) {
  if (left.length !== right.length) return false;
  const leftSorted = [...left].sort();
  const rightSorted = [...right].sort();
  return leftSorted.every((item, index) => item === rightSorted[index]);
}

function normalizeCohortCodes(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[,\n;]+/)
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean),
    ),
  );
}

export default function ProjectReleasePanel({ projectId, graphs }: Props) {
  const { user } = useAuth();
  const [releases, setReleases] = useState<ProjectRelease[]>([]);
  const [candidateUsers, setCandidateUsers] = useState<ReleaseAssignedUser[]>([]);
  const [accessDrafts, setAccessDrafts] = useState<Record<string, string[]>>({});
  const [cohortDrafts, setCohortDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [publishBusy, setPublishBusy] = useState(false);
  const [refreshBusy, setRefreshBusy] = useState(false);
  const [archiveBusyId, setArchiveBusyId] = useState<string | null>(null);
  const [saveBusyId, setSaveBusyId] = useState<string | null>(null);
  const [selectedGraphId, setSelectedGraphId] = useState("");
  const [notes, setNotes] = useState("");
  const [candidateFilter, setCandidateFilter] = useState("");

  useEffect(() => {
    setSelectedGraphId((current) => {
      if (current && graphs.some((graph) => graph.id === current)) {
        return current;
      }
      return graphs[0]?.id ?? "";
    });
  }, [graphs]);

  async function loadReleaseData(showSpinner = true) {
    if (!user) return;
    if (showSpinner) {
      setLoading(true);
    } else {
      setRefreshBusy(true);
    }
    setError(null);
    try {
      const [releaseItems, candidateItems] = await Promise.all([
        listProjectReleases(projectId),
        listProjectReleaseCandidateUsers(projectId, { limit: 200 }),
      ]);
      setReleases(releaseItems);
      setCandidateUsers(candidateItems);
      setAccessDrafts(toUserAccessDrafts(releaseItems));
      setCohortDrafts(toCohortDrafts(releaseItems));
    } catch (err) {
      const message = (err as { message?: string })?.message || "Не удалось загрузить публикации.";
      setError(message);
    } finally {
      setLoading(false);
      setRefreshBusy(false);
    }
  }

  useEffect(() => {
    if (!projectId || !user) return;
    void loadReleaseData();
  }, [projectId, user]);

  const filteredCandidateUsers = useMemo(() => {
    const query = candidateFilter.trim().toLowerCase();
    if (!query) return candidateUsers;
    return candidateUsers.filter((candidate) => {
      const haystack = [candidate.username, candidate.email, candidate.full_name || ""].join(" ").toLowerCase();
      return haystack.includes(query);
    });
  }, [candidateFilter, candidateUsers]);

  const latestActiveReleaseId = useMemo(
    () => releases.find((release) => release.status === "published" && !release.archived_at)?.id ?? null,
    [releases],
  );

  async function handlePublish() {
    if (!selectedGraphId) return;
    try {
      setPublishBusy(true);
      setError(null);
      await publishProjectRelease(projectId, {
        graph_id: selectedGraphId,
        notes: notes.trim() || null,
      });
      setNotes("");
      await loadReleaseData(false);
    } catch (err) {
      const message = (err as { message?: string })?.message || "Не удалось опубликовать релиз.";
      setError(message);
    } finally {
      setPublishBusy(false);
    }
  }

  async function handleArchive(release: ProjectRelease) {
    if (!window.confirm(`Архивировать релиз v${release.version}?`)) return;
    try {
      setArchiveBusyId(release.id);
      setError(null);
      await archiveProjectRelease(projectId, release.id);
      await loadReleaseData(false);
    } catch (err) {
      const message = (err as { message?: string })?.message || "Не удалось архивировать релиз.";
      setError(message);
    } finally {
      setArchiveBusyId(null);
    }
  }

  async function handleSaveAccess(release: ProjectRelease) {
    const selectedUserIds = accessDrafts[release.id] ?? [];
    const selectedCohorts = normalizeCohortCodes(cohortDrafts[release.id] ?? "");
    try {
      setSaveBusyId(release.id);
      setError(null);
      await replaceProjectReleaseAccess(projectId, release.id, {
        user_ids: selectedUserIds,
        cohort_codes: selectedCohorts,
      });
      await loadReleaseData(false);
    } catch (err) {
      const message = (err as { message?: string })?.message || "Не удалось обновить доступ игроков.";
      setError(message);
    } finally {
      setSaveBusyId(null);
    }
  }

  function toggleAssignedUser(releaseId: string, userId: string) {
    setAccessDrafts((current) => {
      const currentIds = current[releaseId] ?? [];
      const nextIds = currentIds.includes(userId)
        ? currentIds.filter((item) => item !== userId)
        : [...currentIds, userId];
      return {
        ...current,
        [releaseId]: nextIds,
      };
    });
  }

  if (!user) {
    return null;
  }

  return (
    <section className="card project-release-panel">
      <div className="card-header">
        <div>
          <h2>Публикация для плеера</h2>
          <p className="muted project-release-subtitle">
            Плеер видит только опубликованные релизы. Новый релиз фиксирует снимок текущего графа и копирует доступы с
            предыдущей активной версии.
          </p>
        </div>
        <button className="secondary" type="button" onClick={() => void loadReleaseData(false)} disabled={refreshBusy}>
          {refreshBusy ? "Обновление..." : "Обновить"}
        </button>
      </div>

      {error && <div className="wizard-alert warn">{error}</div>}

      <div className="project-release-publish">
        <label className="field">
          <span>Граф для публикации</span>
          <select
            className="input"
            value={selectedGraphId}
            onChange={(event) => setSelectedGraphId(event.target.value)}
            disabled={publishBusy || graphs.length === 0}
          >
            {graphs.length === 0 && <option value="">Сначала создайте граф</option>}
            {graphs.map((graph) => (
              <option key={graph.id} value={graph.id}>
                {graph.title}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Комментарий к релизу</span>
          <textarea
            className="input"
            rows={2}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Что изменилось в этой публикации"
            disabled={publishBusy || graphs.length === 0}
          />
        </label>
        <div className="actions">
          <button className="primary" type="button" onClick={() => void handlePublish()} disabled={publishBusy || !selectedGraphId}>
            {publishBusy ? "Публикация..." : "Опубликовать релиз"}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="muted">Загрузка публикаций...</div>
      ) : releases.length === 0 ? (
        <div className="project-release-empty muted">
          Релизов пока нет. Опубликуйте первый граф, чтобы он появился в мобильном каталоге.
        </div>
      ) : (
        <div className="project-release-list">
          {releases.map((release) => {
            const currentDraft = accessDrafts[release.id] ?? [];
            const currentCohortDraft = cohortDrafts[release.id] ?? "";
            const assignedUserIds = release.assigned_users.map((item) => item.id);
            const assignedCohorts = release.assigned_cohorts ?? [];
            const hasAccessChanges =
              !isSameSelection(currentDraft, assignedUserIds) ||
              !isSameSelection(normalizeCohortCodes(currentCohortDraft), assignedCohorts);

            return (
              <article key={release.id} className="project-release-card">
                <div className="project-release-card-header">
                  <div>
                    <div className="project-release-title-row">
                      <h3>Релиз v{release.version}</h3>
                      <span className={`pill ${release.id === latestActiveReleaseId ? "strong" : ""}`}>
                        {release.status === "archived" ? "Архив" : "Опубликован"}
                      </span>
                    </div>
                    <div className="project-release-meta">
                      <span>{release.manifest.graph_title}</span>
                      <span>{release.manifest.scene_count} сцен</span>
                      <span>{release.manifest.choice_count} переходов</span>
                      <span>{formatDateTime(release.published_at)}</span>
                    </div>
                  </div>
                  {release.status !== "archived" && (
                    <button
                      type="button"
                      className="ghost danger"
                      onClick={() => void handleArchive(release)}
                      disabled={archiveBusyId === release.id}
                    >
                      {archiveBusyId === release.id ? "Архивация..." : "Архивировать"}
                    </button>
                  )}
                </div>

                <div className="project-release-package">
                  <span className="muted">Пакет:</span>
                  <code>{release.package_version}</code>
                </div>

                {release.notes && <p className="project-release-notes">{release.notes}</p>}

                <div className="project-release-assigned">
                  <span className="muted">Назначены:</span>
                  <div className="project-release-assigned-list">
                    {release.assigned_users.length > 0 ? (
                      release.assigned_users.map((assigned) => (
                        <span key={assigned.id} className="pill">
                          {assigned.full_name || assigned.username}
                        </span>
                      ))
                    ) : (
                      <span className="muted">никто</span>
                    )}
                  </div>
                </div>

                <div className="project-release-assigned">
                  <span className="muted">Когорты:</span>
                  <div className="project-release-assigned-list">
                    {assignedCohorts.length > 0 ? (
                      assignedCohorts.map((cohortCode) => (
                        <span key={cohortCode} className="pill">
                          {cohortCode}
                        </span>
                      ))
                    ) : (
                      <span className="muted">не заданы</span>
                    )}
                  </div>
                </div>

                {release.status !== "archived" && (
                  <div className="project-release-access">
                    <div className="project-release-access-header">
                      <strong>Доступ игроков</strong>
                      <input
                        className="input"
                        value={candidateFilter}
                        onChange={(event) => setCandidateFilter(event.target.value)}
                        placeholder="Фильтр игроков"
                      />
                    </div>
                    <label className="field project-release-cohorts-field">
                      <span>Когорты доступа</span>
                      <input
                        className="input"
                        value={currentCohortDraft}
                        onChange={(event) =>
                          setCohortDrafts((current) => ({
                            ...current,
                            [release.id]: event.target.value,
                          }))
                        }
                        placeholder="Например: GROUP-A, SCHOOL-7B"
                      />
                    </label>
                    <div className="project-release-candidates">
                      {filteredCandidateUsers.length > 0 ? (
                        filteredCandidateUsers.map((candidate) => {
                          const checked = currentDraft.includes(candidate.id);
                          return (
                            <label key={candidate.id} className="project-release-candidate">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleAssignedUser(release.id, candidate.id)}
                              />
                              <span>
                                <strong>{candidate.full_name || candidate.username}</strong>
                                <small>{candidate.email}</small>
                              </span>
                            </label>
                          );
                        })
                      ) : (
                        <div className="muted">Игроки не найдены.</div>
                      )}
                    </div>
                    <div className="actions">
                      <button
                        className="secondary"
                        type="button"
                        onClick={() => void handleSaveAccess(release)}
                        disabled={saveBusyId === release.id || !hasAccessChanges}
                      >
                        {saveBusyId === release.id ? "Сохранение..." : "Сохранить доступ"}
                      </button>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
