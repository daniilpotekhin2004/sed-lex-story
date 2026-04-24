import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchPlayerPackage, listPlayableProjects } from "../api/player";
import type { PlayableProject } from "../shared/player";
import {
  cachePlayerPackage,
  listCachedPlayerPackages,
  type CachedPlayerPackageEntry,
} from "../stores/playerPackageStore";
import { getRuntimePlatform, isNativeShell } from "../utils/runtimePlatform";

type RecentProject = { id: string; name?: string };

const RECENT_KEY = "recent_player_projects";

function readRecent(): RecentProject[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.filter((project) => typeof project?.id === "string");
    }
    return [];
  } catch {
    return [];
  }
}

function parseProjectId(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  const match = trimmed.match(/(?:player|projects)\/([^/#?]+)/i);
  if (match?.[1]) return match[1];
  return trimmed.replace(/[#?].*$/, "");
}

function formatTimestamp(value?: string | null) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function PlayerLandingPage() {
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [recent, setRecent] = useState<RecentProject[]>([]);
  const [cached, setCached] = useState<CachedPlayerPackageEntry[]>([]);
  const [catalog, setCatalog] = useState<PlayableProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const runtimeLabel = useMemo(() => {
    return isNativeShell() ? `native/${getRuntimePlatform()}` : "web";
  }, []);

  useEffect(() => {
    setRecent(readRecent());
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      const cachedItems = await listCachedPlayerPackages();
      if (!cancelled) {
        setCached(cachedItems);
      }

      try {
        const items = await listPlayableProjects();
        if (!cancelled) {
          setCatalog(items);
          setCatalogError(null);
        }
      } catch (loadError: any) {
        if (!cancelled) {
          setCatalogError(loadError?.message || "Не удалось получить каталог сценариев.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const canSubmit = useMemo(() => Boolean(parseProjectId(input)), [input]);
  const cachedByProjectId = useMemo(() => {
    return new Map(cached.map((entry) => [entry.projectId, entry]));
  }, [cached]);

  function openProject(id: string) {
    navigate(`/player/${id}`);
  }

  function handleSubmit(event?: React.FormEvent) {
    event?.preventDefault();
    const id = parseProjectId(input);
    if (!id) {
      setError("Укажите ID проекта или ссылку /player/<id>.");
      return;
    }
    setError(null);
    openProject(id);
  }

  async function refreshCached() {
    setCached(await listCachedPlayerPackages());
  }

  async function handleDownload(projectId: string) {
    try {
      setDownloadingId(projectId);
      const pkg = await fetchPlayerPackage(projectId);
      await cachePlayerPackage(pkg);
      await refreshCached();
    } catch (downloadError: any) {
      setCatalogError(downloadError?.message || "Не удалось скачать пакет сценария.");
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4">
      <div className="card">
        <div className="card-header">
          <div>
            <h2>Игровой режим</h2>
            <p className="muted">Откройте сценарий, сохраните его на устройство и запускайте даже без сети.</p>
          </div>
          <span className="pill strong">{runtimeLabel}</span>
        </div>

        <form className="space-y-3" onSubmit={handleSubmit}>
          <label className="flex flex-col gap-2">
            <span>ID проекта или ссылка на плеер</span>
            <input
              className="input"
              placeholder="Например: 3f2c8d... или /player/3f2c8d..."
              value={input}
              onChange={(event) => setInput(event.target.value)}
            />
          </label>
          {error && <div className="error">{error}</div>}
          <div className="flex gap-2">
            <button className="primary" type="submit" disabled={!canSubmit}>
              Открыть
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setInput("");
                setError(null);
              }}
            >
              Сбросить
            </button>
          </div>
        </form>
      </div>

      <div className="section space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold">Доступные сценарии</h3>
            <p className="muted">Каталог приходит с сервера и показывает актуальные версии пакетов.</p>
          </div>
          <button className="secondary" onClick={() => window.location.reload()}>
            Обновить
          </button>
        </div>
        {catalogError ? <div className="error">{catalogError}</div> : null}
        {loading && catalog.length === 0 ? (
          <p className="muted">Загрузка каталога...</p>
        ) : catalog.length === 0 ? (
          <p className="muted">Пока нет опубликованных сценариев.</p>
        ) : (
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
            {catalog.map((item) => {
              const cachedEntry = cachedByProjectId.get(item.project_id);
              const isCached = cachedEntry?.packageVersion === item.package_version;
              const isUpdating = Boolean(cachedEntry && cachedEntry.packageVersion !== item.package_version);
              return (
                <div key={item.project_id} className="p-4 border rounded space-y-3 bg-white/70">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold">{item.project_name}</div>
                      <div className="text-sm text-gray-500">{item.graph_title}</div>
                    </div>
                    <span className="pill">{isCached ? "Кеш OK" : isUpdating ? "Есть обновление" : "Онлайн"}</span>
                  </div>
                  {item.project_description ? <p className="text-sm text-gray-700">{item.project_description}</p> : null}
                  <div className="text-sm text-gray-600 space-y-1">
                    <div>Сцены: {item.scene_count}</div>
                    <div>Выборы: {item.choice_count}</div>
                    <div>Версия: {item.package_version}</div>
                    <div>Обновлено: {formatTimestamp(item.updated_at)}</div>
                  </div>
                  <div className="flex gap-2">
                    <button className="primary" onClick={() => openProject(item.project_id)}>
                      Открыть
                    </button>
                    <button
                      className="secondary"
                      disabled={downloadingId === item.project_id}
                      onClick={() => void handleDownload(item.project_id)}
                    >
                      {downloadingId === item.project_id
                        ? "Скачивание..."
                        : isCached
                          ? "Обновить кеш"
                          : isUpdating
                            ? "Скачать обновление"
                            : "Скачать"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="section space-y-3">
        <div>
          <h3 className="text-lg font-semibold">Кеш для офлайна</h3>
          <p className="muted">Эти пакеты уже лежат на устройстве и доступны без сети.</p>
        </div>
        {cached.length === 0 ? (
          <p className="muted">Офлайн-пакетов ещё нет. Скачайте сценарий из каталога.</p>
        ) : (
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
            {cached.map((entry) => (
              <div key={entry.projectId} className="p-4 border rounded space-y-2 bg-white/70">
                <div className="font-semibold">{entry.projectName}</div>
                <div className="text-sm text-gray-500">{entry.graphTitle}</div>
                <div className="text-sm text-gray-600">
                  <div>Версия: {entry.packageVersion}</div>
                  <div>Открыт: {formatTimestamp(entry.lastOpenedAt)}</div>
                  <div>Сохранён: {formatTimestamp(entry.cachedAt)}</div>
                </div>
                <button className="primary" onClick={() => openProject(entry.projectId)}>
                  Открыть офлайн
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="section">
        <h3 className="text-lg font-semibold">Недавно открытые</h3>
        {recent.length === 0 ? (
          <p className="muted">Нет сохранённых проектов. После открытия сценария он появится здесь.</p>
        ) : (
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
            {recent.map((item) => (
              <div key={item.id} className="p-4 border rounded">
                <div className="font-semibold">{item.name || "Без названия"}</div>
                <button className="primary mt-2" onClick={() => openProject(item.id)}>
                  Открыть
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
