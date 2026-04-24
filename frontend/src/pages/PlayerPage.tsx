import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchPlayerPackage, fetchPlayerProjectStats, fetchPlayerResume } from "../api/player";
import { getAssetUrl } from "../api/client";
import type { Edge, LegalConcept, Project, ProjectExport, SceneNode } from "../shared/types";
import type { PlayerPackage, PlayerProjectStats, PlayerResume } from "../shared/player";
import { createPlayerRunEvent } from "../shared/player";
import { trackEvent } from "../utils/tracker";
import { ImageLightbox } from "../components/ImageLightbox";
import SequencePlayer from "../components/SequencePlayer";
import { selectApprovedSceneNarrationAudio } from "../shared/voiceover";
import { cachePlayerPackage, loadCachedPlayerPackage } from "../stores/playerPackageStore";
import {
  appendQueuedPlayerRunEvents,
  ensurePlayerRunSession,
  flushQueuedPlayerRunEvents,
  getPlayerRunSession,
  markPlayerRunCompleted,
} from "../stores/playerRunStore";

type Choice = {
  id: string;
  text: string;
  targetSceneId: string;
  value: string;
};

const RECENT_KEY = "recent_player_projects";
const SESSION_KEY_PREFIX = "lwq_player_session";
const AUDIO_MODE_KEY_PREFIX = "lwq_player_audio_mode";
const RUNTIME_STATE_KEY_PREFIX = "lwq_player_runtime_state";

type StoredRuntimeState = {
  graphId: string;
  packageVersion: string | null;
  currentSceneId: string | null;
  history: string[];
  sessionValues: Record<string, string>;
};

function readSession(projectId?: string | null) {
  if (!projectId) return {};
  try {
    const raw = localStorage.getItem(`${SESSION_KEY_PREFIX}_${projectId}`);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? (parsed as Record<string, string>) : {};
  } catch {
    return {};
  }
}

function writeSession(projectId: string, values: Record<string, string>) {
  try {
    localStorage.setItem(`${SESSION_KEY_PREFIX}_${projectId}`, JSON.stringify(values));
  } catch {
    // ignore storage issues
  }
}

function readRuntimeState(projectId?: string | null) {
  if (!projectId) return null;
  try {
    const raw = localStorage.getItem(`${RUNTIME_STATE_KEY_PREFIX}_${projectId}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as StoredRuntimeState;
  } catch {
    return null;
  }
}

function writeRuntimeState(projectId: string, value: StoredRuntimeState) {
  try {
    localStorage.setItem(`${RUNTIME_STATE_KEY_PREFIX}_${projectId}`, JSON.stringify(value));
  } catch {
    // ignore storage issues
  }
}

function readAudioMode(projectId?: string | null) {
  if (!projectId) return false;
  try {
    const raw = localStorage.getItem(`${AUDIO_MODE_KEY_PREFIX}_${projectId}`);
    return raw === "true";
  } catch {
    return false;
  }
}

function writeAudioMode(projectId: string, value: boolean) {
  try {
    localStorage.setItem(`${AUDIO_MODE_KEY_PREFIX}_${projectId}`, value ? "true" : "false");
  } catch {
    // ignore storage issues
  }
}

function stripQuotes(value: string) {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith("\"") && trimmed.endsWith("\"")) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function resolveSessionValue(values: Record<string, string>, rawKey: string) {
  let key = rawKey.trim();
  if (key.startsWith("choice:")) key = key.slice(7);
  if (key.startsWith("session:")) key = key.slice(8);
  return values[key];
}

function evaluateCondition(condition: string | null | undefined, values: Record<string, string>) {
  if (!condition) return true;
  const trimmed = condition.trim();
  if (!trimmed) return true;
  if (trimmed.includes("!=")) {
    const [left, right] = trimmed.split("!=");
    const key = left.trim();
    const expected = stripQuotes(right ?? "");
    return resolveSessionValue(values, key) !== expected;
  }
  if (trimmed.includes("=")) {
    const [left, right] = trimmed.split("=");
    const key = left.trim();
    const expected = stripQuotes(right ?? "");
    return resolveSessionValue(values, key) === expected;
  }
  if (trimmed.startsWith("!")) {
    const key = trimmed.slice(1).trim();
    return !resolveSessionValue(values, key);
  }
  return Boolean(resolveSessionValue(values, trimmed));
}

function getChoiceValue(edge: Edge) {
  const raw = edge.edge_metadata?.choice_value;
  if (typeof raw === "string") return raw;
  if (raw === null || raw === undefined) return edge.choice_label || edge.id;
  return String(raw);
}

function rememberProject(project: Project) {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    const items: { id: string; name?: string }[] = Array.isArray(parsed) ? parsed : [];
    const next = [{ id: project.id, name: project.name }, ...items.filter((entry) => entry.id !== project.id)].slice(0, 6);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // ignore storage issues
  }
}

function formatTimestamp(value?: string | null) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function renderSyncState(state: "idle" | "syncing" | "synced" | "offline" | "error") {
  switch (state) {
    case "syncing":
      return "Синхронизация...";
    case "synced":
      return "Синхронизировано";
    case "offline":
      return "Оффлайн: очередь ждёт сеть";
    case "error":
      return "Ошибка синхронизации";
    default:
      return "Без обмена";
  }
}

function toStoredRuntimeState(
  graphId: string,
  packageVersion: string | null,
  currentSceneId: string | null,
  history: string[],
  sessionValues: Record<string, string>,
): StoredRuntimeState {
  return {
    graphId,
    packageVersion,
    currentSceneId,
    history,
    sessionValues,
  };
}

export default function PlayerPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [data, setData] = useState<ProjectExport | null>(null);
  const [manifest, setManifest] = useState<PlayerPackage["manifest"] | null>(null);
  const [packageSource, setPackageSource] = useState<"remote" | "cache" | null>(null);
  const [packageNotice, setPackageNotice] = useState<string | null>(null);
  const [currentSceneId, setCurrentSceneId] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [sessionVars, setSessionVars] = useState<Record<string, string>>({});
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [audioMode, setAudioMode] = useState(false);
  const [narrationStatus, setNarrationStatus] = useState<"idle" | "loading" | "playing" | "error">("idle");
  const [narrationError, setNarrationError] = useState<string | null>(null);
  const [stats, setStats] = useState<PlayerProjectStats | null>(null);
  const [resumeState, setResumeState] = useState<PlayerResume | null>(null);
  const [syncState, setSyncState] = useState<"idle" | "syncing" | "synced" | "offline" | "error">("idle");
  const narrationAudioRef = useRef<HTMLAudioElement | null>(null);
  const narrationTokenRef = useRef(0);
  const completionLoggedRef = useRef(false);
  const trackedLoadProjectRef = useRef<string | null>(null);
  const runtimeInitKeyRef = useRef<string | null>(null);

  const rootSceneId = useMemo(() => {
    return data?.graph.root_scene_id || data?.graph.scenes[0]?.id || null;
  }, [data]);

  const commitPackage = useCallback(
    (
      pkg: PlayerPackage,
      source: "remote" | "cache",
      preserveProgress: boolean,
      runtimeState?: StoredRuntimeState | null,
    ) => {
      const sceneIds = new Set(pkg.export.graph.scenes.map((scene) => scene.id));
      const rootId = pkg.export.graph.root_scene_id || pkg.export.graph.scenes[0]?.id || null;
      const runtimeSceneId =
        runtimeState?.currentSceneId && sceneIds.has(runtimeState.currentSceneId) ? runtimeState.currentSceneId : null;
      const runtimeHistory =
        runtimeState?.history?.filter((sceneId) => sceneIds.has(sceneId)) ??
        [];
      setData(pkg.export);
      setManifest(pkg.manifest);
      setPackageSource(source);
      setCurrentSceneId((previous) => {
        if (runtimeSceneId) {
          return runtimeSceneId;
        }
        if (preserveProgress && previous && sceneIds.has(previous)) {
          return previous;
        }
        return rootId;
      });
      setHistory((previous) => {
        if (runtimeHistory.length > 0) {
          return runtimeHistory;
        }
        if (!preserveProgress) {
          return rootId ? [rootId] : [];
        }
        const filtered = previous.filter((sceneId) => sceneIds.has(sceneId));
        return filtered.length > 0 ? filtered : rootId ? [rootId] : [];
      });
    },
    [],
  );

  const refreshStats = useCallback(async () => {
    if (!projectId) return;
    try {
      const next = await fetchPlayerProjectStats(projectId);
      setStats(next);
    } catch {
      // Stats are optional for offline and first-run flows.
    }
  }, [projectId]);

  const pushPlayerEvents = useCallback(
    async (events: ReturnType<typeof createPlayerRunEvent>[], currentNodeId: string | null, status: "active" | "completed") => {
      if (!projectId || !manifest) return null;
      if (events.length > 0) {
        await appendQueuedPlayerRunEvents(projectId, events);
      }
      if (typeof navigator !== "undefined" && !navigator.onLine) {
        setSyncState("offline");
        return null;
      }
      setSyncState("syncing");
      const result = await flushQueuedPlayerRunEvents({
        projectId,
        graphId: manifest.graph_id,
        packageVersion: manifest.package_version,
        currentNodeId,
        status,
      });
      if (result) {
        setSyncState("synced");
        void refreshStats();
        return result;
      }
      setSyncState(typeof navigator !== "undefined" && !navigator.onLine ? "offline" : "error");
      return null;
    },
    [manifest, projectId, refreshStats],
  );

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;

    setLoading(true);
    setError(null);
    setPackageNotice(null);
    setStats(null);
    setResumeState(null);
    setSyncState("idle");
    setData(null);
    setManifest(null);
    setCurrentSceneId(null);
    setHistory([]);
    setLightboxUrl(null);
    completionLoggedRef.current = false;
    trackedLoadProjectRef.current = null;
    runtimeInitKeyRef.current = null;

    const load = async () => {
      const localRuntimeState = readRuntimeState(projectId);
      const localRunSession = await getPlayerRunSession(projectId);
      const localSessionValues = localRuntimeState?.sessionValues ?? readSession(projectId);
      if (!cancelled) {
        setSessionVars(localSessionValues);
      }

      const cachedPackage = await loadCachedPlayerPackage(projectId);
      let hasSeedData = false;

      if (cachedPackage && !cancelled) {
        const cachedRuntimeState =
          localRunSession?.status !== "completed" &&
          localRuntimeState?.packageVersion === cachedPackage.manifest.package_version
            ? localRuntimeState
            : null;
        commitPackage(cachedPackage, "cache", false, cachedRuntimeState);
        setPackageNotice("Открыта сохранённая копия. Проверяю обновления с сервера...");
        setLoading(false);
        hasSeedData = true;
      }

      try {
        const remoteResume = await fetchPlayerResume(projectId).catch(() => null);
        if (cancelled) return;

        const activeRemoteResume = remoteResume?.available ? remoteResume : null;
        setResumeState(activeRemoteResume);

        const desiredPackageVersion =
          (localRunSession && localRunSession.status !== "completed" ? localRunSession.packageVersion : null) ||
          activeRemoteResume?.package_version ||
          null;

        let remotePackage: PlayerPackage;
        try {
          remotePackage = await fetchPlayerPackage(projectId, desiredPackageVersion);
        } catch (packageError) {
          if (!desiredPackageVersion) {
            throw packageError;
          }
          remotePackage = await fetchPlayerPackage(projectId);
        }
        if (cancelled) return;
        await cachePlayerPackage(remotePackage);

        const shouldUseLocalRuntime =
          Boolean(localRunSession && localRunSession.status !== "completed") &&
          localRuntimeState?.packageVersion === remotePackage.manifest.package_version &&
          localRuntimeState?.graphId === remotePackage.manifest.graph_id;
        const remoteRuntimeState =
          activeRemoteResume &&
          activeRemoteResume.package_version === remotePackage.manifest.package_version &&
          activeRemoteResume.graph_id === remotePackage.manifest.graph_id
            ? toStoredRuntimeState(
                activeRemoteResume.graph_id || remotePackage.manifest.graph_id,
                activeRemoteResume.package_version ?? remotePackage.manifest.package_version,
                activeRemoteResume.current_node_id ?? null,
                activeRemoteResume.scene_history ?? [],
                activeRemoteResume.session_values ?? {},
              )
            : null;
        const preferredRuntimeState = shouldUseLocalRuntime ? localRuntimeState : remoteRuntimeState;

        commitPackage(remotePackage, "remote", hasSeedData && !preferredRuntimeState, preferredRuntimeState);

        if (preferredRuntimeState) {
          writeSession(projectId, preferredRuntimeState.sessionValues);
          setSessionVars(preferredRuntimeState.sessionValues);
        }

        if (!hasSeedData) {
          setPackageNotice(activeRemoteResume ? "Восстановлен незавершённый сеанс с сервера." : null);
        } else if (cachedPackage?.manifest.package_version !== remotePackage.manifest.package_version) {
          if (activeRemoteResume?.package_version === remotePackage.manifest.package_version) {
            setPackageNotice("Найден незавершённый сеанс. Загружена подходящая версия пакета для продолжения.");
          } else {
            setPackageNotice("На устройстве была старая версия. Пакет обновлён из сети.");
          }
        } else {
          setPackageNotice(activeRemoteResume ? "Незавершённый сеанс восстановлен." : null);
        }
      } catch (loadError: any) {
        if (cancelled) return;
        if (!hasSeedData) {
          setError(loadError?.message || "Не удалось загрузить историю");
        } else {
          setPackageNotice("Сеть недоступна. Используется кешированная версия сценария.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [commitPackage, projectId]);

  useEffect(() => {
    if (!projectId) return;
    setSessionVars(readSession(projectId));
    setAudioMode(readAudioMode(projectId));
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !manifest) return;
    writeRuntimeState(
      projectId,
      toStoredRuntimeState(
        manifest.graph_id,
        manifest.package_version,
        currentSceneId,
        history,
        sessionVars,
      ),
    );
  }, [currentSceneId, history, manifest, projectId, sessionVars]);

  useEffect(() => {
    if (!projectId || !manifest || !data) return;
    const initKey = `${projectId}:${manifest.package_version}:${resumeState?.run_id || "fresh"}`;
    if (runtimeInitKeyRef.current === initKey) {
      return;
    }
    runtimeInitKeyRef.current = initKey;
    let cancelled = false;

    const initRuntime = async () => {
      const initialNodeId = currentSceneId || rootSceneId;
      const sessionResult = await ensurePlayerRunSession({
        projectId,
        graphId: manifest.graph_id,
        packageVersion: manifest.package_version,
        preferredRunId: resumeState?.available ? resumeState.run_id : null,
        preferredStatus: resumeState?.available ? resumeState.status : null,
      });
      if (cancelled) return;

      if (sessionResult.isNew) {
        completionLoggedRef.current = false;
        const initialEvents = [
          createPlayerRunEvent("session_started", {
            source: packageSource || "remote",
            package_version: manifest.package_version,
            root_node_id: rootSceneId,
          }),
          ...(initialNodeId
            ? [
                createPlayerRunEvent("node_entered", {
                  node_id: initialNodeId,
                  reason: "initial",
                }),
              ]
            : []),
        ];
        await pushPlayerEvents(initialEvents, initialNodeId, "active");
      } else {
        await pushPlayerEvents([], initialNodeId, "active");
      }

      await refreshStats();
    };

    void initRuntime();
    return () => {
      cancelled = true;
    };
  }, [currentSceneId, data, manifest, packageSource, projectId, pushPlayerEvents, refreshStats, resumeState, rootSceneId]);

  useEffect(() => {
    if (data?.project) {
      rememberProject(data.project);
    }
  }, [data?.project]);

  useEffect(() => {
    if (!data || !projectId || trackedLoadProjectRef.current === projectId) return;
    trackedLoadProjectRef.current = projectId;
    trackEvent("player_loaded", {
      projectId,
      rootScene: rootSceneId,
      source: packageSource || "remote",
      packageVersion: manifest?.package_version || null,
    });
  }, [data, manifest?.package_version, packageSource, projectId, rootSceneId]);

  const sceneMap = useMemo(() => {
    const map: Record<string, SceneNode> = {};
    data?.graph.scenes.forEach((scene) => {
      map[scene.id] = scene;
    });
    return map;
  }, [data]);

  const approvedImageMap = useMemo(() => {
    const map: Record<string, string> = {};
    data?.scenes.forEach((sceneExport) => {
      if (sceneExport.approved_image?.url) {
        const imageUrl = getAssetUrl(sceneExport.approved_image.url);
        if (imageUrl) {
          map[sceneExport.scene.id] = imageUrl;
        }
      }
    });
    return map;
  }, [data]);

  const sceneExportMap = useMemo(() => {
    const map: Record<string, ProjectExport["scenes"][number]> = {};
    data?.scenes.forEach((entry) => {
      map[entry.scene.id] = entry;
    });
    return map;
  }, [data]);

  const legalMap = useMemo(() => {
    const map: Record<string, LegalConcept> = {};
    data?.legal_concepts.forEach((concept) => {
      map[concept.id] = concept;
    });
    return map;
  }, [data]);

  const currentScene = currentSceneId ? sceneMap[currentSceneId] : null;
  const currentExport = currentSceneId ? sceneExportMap[currentSceneId] : null;

  const choices: Choice[] = useMemo(() => {
    if (!data || !currentSceneId) return [];
    return data.graph.edges
      .filter((edge) => edge.from_scene_id === currentSceneId)
      .filter((edge) => evaluateCondition(edge.condition, sessionVars))
      .map((edge) => ({
        id: edge.id,
        text: edge.choice_label || "Продолжить",
        targetSceneId: edge.to_scene_id,
        value: getChoiceValue(edge),
      }));
  }, [currentSceneId, data, sessionVars]);

  const legalConcepts = currentScene?.legal_concepts || [];
  const location = currentExport?.location || currentScene?.location || null;
  const artifacts = currentExport?.artifacts || currentScene?.artifacts || [];
  const sequence = currentScene?.context?.sequence;
  const voiceoverLines = currentScene?.context?.voiceover?.lines || [];
  const sequenceSlides = sequence?.slides || [];
  const showSequence = sequenceSlides.length > 0;
  const narrationAudioUrl = useMemo(() => {
    return getAssetUrl(selectApprovedSceneNarrationAudio(voiceoverLines)) ?? null;
  }, [voiceoverLines]);

  const cleanupNarration = useCallback(() => {
    narrationTokenRef.current += 1;
    if (narrationAudioRef.current) {
      narrationAudioRef.current.pause();
      narrationAudioRef.current = null;
    }
  }, []);

  const stopNarration = useCallback(() => {
    cleanupNarration();
    setNarrationStatus("idle");
    setNarrationError(null);
  }, [cleanupNarration]);

  const playNarration = useCallback(async () => {
    if (!narrationAudioUrl) {
      setNarrationError("Для этой сцены нет утверждённой озвучки. Подтвердите реплику в разделе озвучки проекта.");
      setNarrationStatus("error");
      return;
    }

    setNarrationError(null);
    setNarrationStatus("loading");
    cleanupNarration();
    const token = narrationTokenRef.current;
    const audio = new Audio(narrationAudioUrl);
    narrationAudioRef.current = audio;
    audio.onended = () => setNarrationStatus("idle");
    audio.onerror = () => {
      if (token !== narrationTokenRef.current) return;
      setNarrationStatus("error");
      setNarrationError("Не удалось воспроизвести утверждённый аудиофайл.");
    };
    try {
      await audio.play();
      if (token === narrationTokenRef.current) {
        setNarrationStatus("playing");
      }
    } catch {
      if (token !== narrationTokenRef.current) return;
      setNarrationStatus("error");
      setNarrationError("Браузер заблокировал воспроизведение. Нажмите кнопку ещё раз.");
    }
  }, [cleanupNarration, narrationAudioUrl]);

  useEffect(() => {
    if (!audioMode) {
      stopNarration();
    } else {
      setNarrationStatus("idle");
      setNarrationError(null);
    }
  }, [audioMode, currentSceneId, stopNarration]);

  useEffect(() => {
    return () => cleanupNarration();
  }, [cleanupNarration]);

  useEffect(() => {
    if (!projectId || !manifest) return;
    const handleOnline = () => {
      void pushPlayerEvents([], currentSceneId || rootSceneId, completionLoggedRef.current ? "completed" : "active");
      void refreshStats();
    };
    window.addEventListener("online", handleOnline);
    return () => {
      window.removeEventListener("online", handleOnline);
    };
  }, [currentSceneId, manifest, projectId, pushPlayerEvents, refreshStats, rootSceneId]);

  useEffect(() => {
    if (!projectId || !currentScene || choices.length > 0) return;
    if (completionLoggedRef.current) return;
    completionLoggedRef.current = true;
    void markPlayerRunCompleted(projectId);
    void pushPlayerEvents(
      [
        createPlayerRunEvent("session_completed", {
          node_id: currentScene.id,
        }),
      ],
      currentScene.id,
      "completed",
    );
  }, [choices.length, currentScene, projectId, pushPlayerEvents]);

  function goToScene(sceneId: string) {
    setCurrentSceneId(sceneId);
    setHistory((previous) => [...previous, sceneId]);
    trackEvent("player_choice", { from: currentSceneId, to: sceneId, projectId });
  }

  function handleChoice(choice: Choice) {
    if (!currentScene || !projectId) return;
    const choiceKey = currentScene.context?.sequence?.choice_key?.trim() || "";
    const next = { ...sessionVars, last_choice: choice.value };
    if (choiceKey) {
      next[choiceKey] = choice.value;
    }
    writeSession(projectId, next);
    setSessionVars(next);
    goToScene(choice.targetSceneId);
    void pushPlayerEvents(
      [
        createPlayerRunEvent("choice_selected", {
          choice_id: choice.id,
          from_node_id: currentScene.id,
          to_node_id: choice.targetSceneId,
          value: choice.value,
        }),
        createPlayerRunEvent("node_entered", {
          node_id: choice.targetSceneId,
          reason: "choice",
          via_choice_id: choice.id,
        }),
      ],
      choice.targetSceneId,
      "active",
    );
  }

  function handleAudioToggle(enabled: boolean) {
    setAudioMode(enabled);
    if (projectId) {
      writeAudioMode(projectId, enabled);
    }
  }

  if (loading) {
    return <div className="p-8">Загрузка истории...</div>;
  }

  if (error || !data || !currentScene) {
    return (
      <div className="p-8">
        <p className="text-red-600">Не удалось загрузить историю.</p>
        <p className="text-sm text-gray-600">{error}</p>
        <button className="mt-4 px-4 py-2 bg-blue-600 text-white rounded" onClick={() => navigate(-1)}>
          Назад
        </button>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-4">
      <div className="flex justify-between items-center gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold">{data.project.name || "История"}</h1>
          <p className="text-sm text-gray-500">Интерактивный просмотр с офлайн-кешем и синхронизацией результатов</p>
          <div className="flex flex-wrap gap-2 mt-2 text-xs">
            <span className="pill strong">{packageSource === "cache" ? "Кеш" : "Сеть"}</span>
            <span className="pill">Версия: {manifest?.package_version || "-"}</span>
            <span className="pill">Синхронизация: {renderSyncState(syncState)}</span>
            {resumeState?.available ? <span className="pill">Возобновление: доступно</span> : null}
          </div>
          {packageNotice ? <div className="mt-2 text-sm text-amber-700">{packageNotice}</div> : null}
        </div>
        <div className="flex items-center gap-4">
          <label className="sequence-audio-toggle">
            <input
              type="checkbox"
              checked={audioMode}
              onChange={(event) => handleAudioToggle(event.target.checked)}
            />
            <span>Аудиорежим</span>
          </label>
          <button className="text-blue-600 hover:underline" onClick={() => navigate(-1)}>
            ← Назад
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 p-4 border rounded section">
          {showSequence ? (
            <div className="mb-3">
              <SequencePlayer
                slides={sequenceSlides}
                fallbackImageUrl={approvedImageMap[currentScene.id]}
                choices={choices.map((choice) => ({ id: choice.id, label: choice.text }))}
                choicePrompt={sequence?.choice_prompt || (choices.length > 0 ? "Что вы сделаете дальше?" : undefined)}
                onChoice={(choiceId) => {
                  const selected = choices.find((choice) => choice.id === choiceId);
                  if (selected) handleChoice(selected);
                }}
                resetKey={`${currentScene.id}:${sequenceSlides.length}`}
                showAudioControls={audioMode}
                voiceoverLines={voiceoverLines}
              />
            </div>
          ) : approvedImageMap[currentScene.id] ? (
            <img
              src={approvedImageMap[currentScene.id]}
              alt={currentScene.title}
              className="w-full h-72 object-cover rounded mb-3"
              style={{ cursor: "zoom-in" }}
              onClick={() => setLightboxUrl(approvedImageMap[currentScene.id])}
            />
          ) : (
            <div className="w-full h-72 bg-gray-100 rounded mb-3 flex items-center justify-center text-gray-500">
              Для этой сцены нет изображения
            </div>
          )}
          <h2 className="text-2xl font-semibold mb-2">{currentScene.title}</h2>
          <p className="whitespace-pre-line text-gray-800 dark:text-gray-200">{currentScene.content}</p>
          {audioMode && !showSequence && (
            <div className="sequence-audio" style={{ marginTop: 12 }}>
              <button
                className="ghost"
                type="button"
                disabled={narrationStatus === "loading" || !narrationAudioUrl}
                onClick={() => (narrationStatus === "playing" ? stopNarration() : playNarration())}
              >
                {narrationStatus === "loading"
                  ? "Загрузка..."
                  : narrationStatus === "playing"
                    ? "Остановить звук"
                    : "Воспроизвести озвучку"}
              </button>
              {!narrationAudioUrl && !narrationError && <div className="sequence-audio-error">Нет утверждённой озвучки для этой сцены.</div>}
              {narrationError && <div className="sequence-audio-error">{narrationError}</div>}
            </div>
          )}
          {location && (
            <div className="mt-4 text-sm text-gray-600">
              <div className="font-semibold">Локация</div>
              <div>{location.name}</div>
              {location.description && <div className="mt-1">{location.description}</div>}
            </div>
          )}
        </div>

        <div className="p-4 border rounded section">
          <h3 className="text-lg font-semibold">Выборы</h3>
          {showSequence ? (
            choices.length === 0 ? (
              <div className="text-sm text-gray-500">Выборов нет.</div>
            ) : (
              <div className="text-sm text-gray-500">Выборы появятся после последнего слайда.</div>
            )
          ) : choices.length === 0 ? (
            <div className="text-sm text-gray-500">Это финальная сцена. Результат будет синхронизирован при наличии сети.</div>
          ) : (
            <div className="space-y-2">
              {choices.map((choice) => (
                <button
                  key={choice.id}
                  className="w-full text-left px-3 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
                  onClick={() => handleChoice(choice)}
                >
                  {choice.text}
                </button>
              ))}
            </div>
          )}
          <div className="mt-4">
            <h4 className="text-sm font-semibold">Правовые сведения</h4>
            <div className="flex flex-wrap gap-2 mt-2">
              {legalConcepts.length === 0 && <span className="text-xs text-gray-500">Нет привязанных</span>}
              {legalConcepts.map((concept) => (
                <span key={concept.id} className="px-2 py-1 text-xs rounded bg-gray-200 text-gray-800">
                  {legalMap[concept.id]?.title || concept.code || concept.id}
                </span>
              ))}
            </div>
          </div>
          <div className="mt-4">
            <h4 className="text-sm font-semibold">Артефакты</h4>
            <div className="flex flex-wrap gap-2 mt-2">
              {artifacts.length === 0 && <span className="text-xs text-gray-500">Нет привязанных</span>}
              {artifacts.map((item) => (
                <span key={item.id} className="px-2 py-1 text-xs rounded bg-gray-200 text-gray-800">
                  {item.artifact?.name || item.artifact_id}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="p-4 border rounded section">
        <h3 className="text-lg font-semibold">Пройденный путь</h3>
        <div className="flex flex-wrap gap-2 text-sm">
          {history.map((sceneId, index) => (
            <span key={`${sceneId}-${index}`} className="px-2 py-1 rounded bg-gray-100 border border-gray-200">
              {sceneMap[sceneId]?.title || sceneId}
            </span>
          ))}
        </div>
      </div>

      <div className="p-4 border rounded section space-y-3">
        <div>
          <h3 className="text-lg font-semibold">Результаты и статистика</h3>
          <p className="text-sm text-gray-500">Сохраняются только выборы, состояние прохождения и обезличенная агрегированная статистика.</p>
        </div>
        {stats ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div className="p-3 rounded bg-gray-50 border">
                <div className="text-gray-500">Всего прохождений</div>
                <div className="text-xl font-semibold">{stats.total_runs}</div>
              </div>
              <div className="p-3 rounded bg-gray-50 border">
                <div className="text-gray-500">Завершено</div>
                <div className="text-xl font-semibold">{stats.completed_runs}</div>
              </div>
              <div className="p-3 rounded bg-gray-50 border">
                <div className="text-gray-500">Игроков</div>
                <div className="text-xl font-semibold">{stats.unique_players}</div>
              </div>
              <div className="p-3 rounded bg-gray-50 border">
                <div className="text-gray-500">Мои прохождения</div>
                <div className="text-xl font-semibold">{stats.mine.total_runs}</div>
              </div>
            </div>
            <div className="text-sm text-gray-600">
              <div>Моя последняя синхронизация: {formatTimestamp(stats.mine.last_synced_at)}</div>
              <div>Последняя завершённая попытка: {formatTimestamp(stats.mine.last_completed_at)}</div>
              {resumeState?.available ? (
                <div>Активный сеанс можно продолжить с узла: {resumeState.current_node_id || "-"}</div>
              ) : null}
            </div>
            <div>
              <h4 className="text-sm font-semibold mb-2">Популярные выборы</h4>
              {stats.choices.length === 0 ? (
                <div className="text-sm text-gray-500">Пока нет агрегированных выборов.</div>
              ) : (
                <div className="space-y-2">
                  {stats.choices.slice(0, 5).map((choice) => (
                    <div key={choice.choice_id} className="flex items-center justify-between gap-3 text-sm">
                      <div className="truncate">{choice.label}</div>
                      <div className="font-semibold">{choice.selection_count}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="text-sm text-gray-500">Статистика появится после первой успешной синхронизации.</div>
        )}
      </div>

      {lightboxUrl ? (
        <ImageLightbox
          url={lightboxUrl}
          title={currentScene.title}
          subtitle="Изображение сцены"
          onClose={() => setLightboxUrl(null)}
        />
      ) : null}
    </div>
  );
}



