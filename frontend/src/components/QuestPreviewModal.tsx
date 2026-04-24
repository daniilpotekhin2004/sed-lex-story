import { useEffect, useMemo, useState } from "react";
import { getSceneImages } from "../api/generation";
import type { Edge, SceneNode, ScenarioGraph } from "../shared/types";
import SequencePlayer from "./SequencePlayer";

type PreviewEdge = Pick<
  Edge,
  "id" | "from_scene_id" | "to_scene_id" | "choice_label" | "condition" | "edge_metadata"
>;

type Choice = {
  id: string;
  label: string;
  value: string;
  targetSceneId: string;
};

type Props = {
  graph: ScenarioGraph;
  startSceneId?: string | null;
  onClose: () => void;
  onOpenScene?: (sceneId: string) => void;
};

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

function getChoiceValue(edge: PreviewEdge) {
  const raw = edge.edge_metadata?.choice_value;
  if (typeof raw === "string") return raw;
  if (raw === null || raw === undefined) return edge.choice_label || edge.id;
  return String(raw);
}

function edgeLabel(edge: PreviewEdge) {
  const explicit = (edge.choice_label || "").trim();
  if (explicit) return explicit;
  const value = getChoiceValue(edge).trim();
  if (value) return value;
  const condition = (edge.condition || "").trim();
  if (condition) return `if ${condition}`;
  return "Продолжить";
}

function sortScenes(scenes: SceneNode[]) {
  return [...scenes].sort((a, b) => {
    const orderDiff =
      (a.order_index ?? Number.MAX_SAFE_INTEGER) - (b.order_index ?? Number.MAX_SAFE_INTEGER);
    if (orderDiff !== 0) return orderDiff;
    return a.title.localeCompare(b.title);
  });
}

function buildAutoEdges(scenes: SceneNode[], edges: Edge[]): PreviewEdge[] {
  if (scenes.length < 2) return [];
  const sortedScenes = sortScenes(scenes);
  const outgoingCount = new Map<string, number>();
  const existingPairs = new Set<string>();
  edges.forEach((edge) => {
    outgoingCount.set(edge.from_scene_id, (outgoingCount.get(edge.from_scene_id) || 0) + 1);
    existingPairs.add(`${edge.from_scene_id}->${edge.to_scene_id}`);
  });

  const derived: PreviewEdge[] = [];
  for (let idx = 0; idx < sortedScenes.length - 1; idx += 1) {
    const fromScene = sortedScenes[idx];
    const toScene = sortedScenes[idx + 1];
    if (!fromScene?.id || !toScene?.id) continue;
    if ((outgoingCount.get(fromScene.id) || 0) > 0) continue;
    const pairKey = `${fromScene.id}->${toScene.id}`;
    if (existingPairs.has(pairKey)) continue;
    derived.push({
      id: `__preview_auto__${fromScene.id}__${toScene.id}`,
      from_scene_id: fromScene.id,
      to_scene_id: toScene.id,
      choice_label: "Далее",
      condition: null,
      edge_metadata: { auto_source: "order", auto_generated: true },
    });
  }
  return derived;
}

function sceneHasSlideImage(scene: SceneNode | null) {
  const slides = scene?.context?.sequence?.slides || [];
  return slides.some((slide) => typeof slide.image_url === "string" && slide.image_url.trim().length > 0);
}

export default function QuestPreviewModal({
  graph,
  startSceneId,
  onClose,
  onOpenScene,
}: Props) {
  const orderedScenes = useMemo(() => sortScenes(graph.scenes || []), [graph.scenes]);
  const sceneMap = useMemo(() => {
    const map = new Map<string, SceneNode>();
    (graph.scenes || []).forEach((scene) => {
      map.set(scene.id, scene);
    });
    return map;
  }, [graph.scenes]);
  const allEdges = useMemo<PreviewEdge[]>(
    () => [...(graph.edges || []), ...buildAutoEdges(graph.scenes || [], graph.edges || [])],
    [graph.edges, graph.scenes],
  );
  const fallbackStartSceneId = useMemo(
    () => startSceneId || graph.root_scene_id || orderedScenes[0]?.id || null,
    [graph.root_scene_id, orderedScenes, startSceneId],
  );

  const [currentSceneId, setCurrentSceneId] = useState<string | null>(fallbackStartSceneId);
  const [history, setHistory] = useState<string[]>(fallbackStartSceneId ? [fallbackStartSceneId] : []);
  const [sessionVars, setSessionVars] = useState<Record<string, string>>({});
  const [sceneImageMap, setSceneImageMap] = useState<Record<string, string>>({});
  const [imageLoadingSceneId, setImageLoadingSceneId] = useState<string | null>(null);

  useEffect(() => {
    setCurrentSceneId(fallbackStartSceneId);
    setHistory(fallbackStartSceneId ? [fallbackStartSceneId] : []);
    setSessionVars({});
  }, [fallbackStartSceneId, graph.id]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  const currentScene = currentSceneId ? sceneMap.get(currentSceneId) || null : null;

  const choices = useMemo<Choice[]>(() => {
    if (!currentSceneId) return [];
    return allEdges
      .filter((edge) => edge.from_scene_id === currentSceneId)
      .filter((edge) => evaluateCondition(edge.condition, sessionVars))
      .map((edge) => ({
        id: edge.id,
        label: edgeLabel(edge),
        value: getChoiceValue(edge),
        targetSceneId: edge.to_scene_id,
      }));
  }, [allEdges, currentSceneId, sessionVars]);

  useEffect(() => {
    if (!currentSceneId) return;
    if (Object.prototype.hasOwnProperty.call(sceneImageMap, currentSceneId)) return;
    if (sceneHasSlideImage(currentScene)) return;

    let cancelled = false;
    setImageLoadingSceneId(currentSceneId);
    getSceneImages(currentSceneId)
      .then((variants) => {
        if (cancelled) return;
        const approved = variants.find((variant) => variant.is_approved)?.url;
        const fallback = approved || variants[0]?.url || "";
        setSceneImageMap((prev) => ({ ...prev, [currentSceneId]: fallback }));
      })
      .catch(() => {
        // Optional image prefetch for preview mode only.
      })
      .finally(() => {
        if (!cancelled) {
          setImageLoadingSceneId((prev) => (prev === currentSceneId ? null : prev));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [currentScene, currentSceneId, sceneImageMap]);

  const goToScene = (sceneId: string) => {
    setCurrentSceneId(sceneId);
    setHistory((prev) => [...prev, sceneId]);
    onOpenScene?.(sceneId);
  };

  const handleChoice = (choiceId: string) => {
    const choice = choices.find((item) => item.id === choiceId);
    if (!choice || !currentScene) return;
    const choiceKey = currentScene.context?.sequence?.choice_key?.trim() || "";
    const next = { ...sessionVars, last_choice: choice.value };
    if (choiceKey) next[choiceKey] = choice.value;
    setSessionVars(next);
    goToScene(choice.targetSceneId);
  };

  const restart = () => {
    if (!fallbackStartSceneId) return;
    setCurrentSceneId(fallbackStartSceneId);
    setHistory([fallbackStartSceneId]);
    setSessionVars({});
    onOpenScene?.(fallbackStartSceneId);
  };

  if (!currentScene || !fallbackStartSceneId) {
    return (
      <div className="quest-preview-overlay" onClick={onClose}>
        <div className="quest-preview-modal" onClick={(event) => event.stopPropagation()}>
          <div className="quest-preview-header">
            <div>
              <div className="quest-preview-kicker">Play Preview</div>
              <h2>Нет сцен для проигрывания</h2>
            </div>
            <button className="asset-edit-close" onClick={onClose}>
              x
            </button>
          </div>
        </div>
      </div>
    );
  }

  const sequence = currentScene.context?.sequence;
  const slides = sequence?.slides || [];
  const showSequence = slides.length > 0;
  const fallbackImageUrl = sceneImageMap[currentScene.id] || "";
  const sessionEntries = Object.entries(sessionVars);

  return (
    <div className="quest-preview-overlay" onClick={onClose}>
      <div className="quest-preview-modal" onClick={(event) => event.stopPropagation()}>
        <div className="quest-preview-header">
          <div>
            <div className="quest-preview-kicker">Play Preview</div>
            <h2>{graph.title || "Просмотр истории"}</h2>
            <p className="muted">Сцена: {currentScene.title}</p>
          </div>
          <div className="quest-preview-header-actions">
            <button className="secondary" onClick={restart} disabled={!fallbackStartSceneId}>
              С начала
            </button>
            <button className="secondary" onClick={() => onOpenScene?.(currentScene.id)}>
              Открыть в редакторе
            </button>
            <button className="asset-edit-close" onClick={onClose}>
              x
            </button>
          </div>
        </div>

        <div className="quest-preview-body">
          <section className="quest-preview-stage">
            {showSequence ? (
              <SequencePlayer
                slides={slides}
                fallbackImageUrl={fallbackImageUrl}
                choices={choices.map((choice) => ({ id: choice.id, label: choice.label }))}
                choicePrompt={
                  sequence?.choice_prompt || (choices.length > 0 ? "Что вы сделаете дальше?" : undefined)
                }
                onChoice={handleChoice}
                voiceoverLines={currentScene.context?.voiceover?.lines || []}
                resetKey={`${currentScene.id}:${history.length}`}
              />
            ) : (
              <div className="quest-preview-scene-card">
                {fallbackImageUrl ? (
                  <img
                    src={fallbackImageUrl}
                    alt={currentScene.title}
                    className="quest-preview-scene-image"
                  />
                ) : (
                  <div className="quest-preview-scene-placeholder">
                    {imageLoadingSceneId === currentScene.id
                      ? "Загружаем изображение..."
                      : "Для сцены нет утверждённого изображения"}
                  </div>
                )}
                <div className="quest-preview-scene-text">
                  <h3>{currentScene.title}</h3>
                  {currentScene.synopsis?.trim() ? <p className="muted">{currentScene.synopsis}</p> : null}
                  <p>{currentScene.content}</p>
                </div>
                <div className="quest-preview-scene-choices">
                  {choices.length > 0 ? (
                    choices.map((choice) => (
                      <button key={choice.id} className="primary" onClick={() => handleChoice(choice.id)}>
                        {choice.label}
                      </button>
                    ))
                  ) : (
                    <div className="muted">Финал ветки: переходов нет.</div>
                  )}
                </div>
              </div>
            )}
          </section>

          <aside className="quest-preview-sidebar">
            <div className="quest-preview-panel">
              <h3>Выборы</h3>
              {choices.length > 0 ? (
                <div className="quest-preview-choice-list">
                  {choices.map((choice) => (
                    <button key={choice.id} className="ghost" onClick={() => handleChoice(choice.id)}>
                      {choice.label}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="muted">Нет доступных выборов.</div>
              )}
            </div>

            <div className="quest-preview-panel">
              <h3>Переменные сессии</h3>
              {sessionEntries.length > 0 ? (
                <div className="quest-preview-session-list">
                  {sessionEntries.map(([key, value]) => (
                    <div key={key} className="quest-preview-session-item">
                      <span>{key}</span>
                      <code>{value}</code>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="muted">Пока пусто.</div>
              )}
            </div>

            <div className="quest-preview-panel">
              <h3>История переходов</h3>
              <ol className="quest-preview-history-list">
                {history.slice(-10).map((sceneId, idx) => {
                  const scene = sceneMap.get(sceneId);
                  return <li key={`${sceneId}-${idx}`}>{scene?.title || sceneId}</li>;
                })}
              </ol>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
