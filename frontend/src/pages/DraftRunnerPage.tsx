import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getGraph } from "../api/scenario";
import "./DraftRunnerPage.css";
import {
  DRAFT_RUNNER_EXCHANGE_RULES,
  buildDraftRunnerSnapshot,
  createDraftRunnerEvent,
  getOutgoingChoices,
  type DraftRunnerEvent,
  type DraftRunnerSnapshot,
} from "../shared/draftRunner";

export default function DraftRunnerPage() {
  const { projectId, graphId } = useParams<{ projectId: string; graphId: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<DraftRunnerSnapshot | null>(null);
  const [currentNodeId, setCurrentNodeId] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [events, setEvents] = useState<DraftRunnerEvent[]>([]);

  useEffect(() => {
    if (!graphId) return;
    let cancelled = false;

    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const graph = await getGraph(graphId);
        if (cancelled) return;

        const runnerSnapshot = buildDraftRunnerSnapshot(graph);
        const rootId = runnerSnapshot.root_node_id;
        const initialEvents: DraftRunnerEvent[] = [
          createDraftRunnerEvent("snapshot_loaded", {
            graph_id: runnerSnapshot.graph_id,
            root_node_id: rootId,
            node_count: runnerSnapshot.node_order.length,
            choice_count: runnerSnapshot.choices.length,
          }),
        ];
        if (rootId) {
          initialEvents.push(
            createDraftRunnerEvent("node_entered", {
              node_id: rootId,
              reason: "initial",
            }),
          );
        }

        setSnapshot(runnerSnapshot);
        setCurrentNodeId(rootId);
        setHistory(rootId ? [rootId] : []);
        setEvents(initialEvents);
      } catch (loadError: any) {
        if (cancelled) return;
        setError(loadError?.message || "Не удалось загрузить граф для прогона.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [graphId]);

  const currentNode = useMemo(() => {
    if (!snapshot || !currentNodeId) return null;
    return snapshot.nodes[currentNodeId] || null;
  }, [snapshot, currentNodeId]);

  const choices = useMemo(() => {
    if (!snapshot || !currentNodeId) return [];
    return getOutgoingChoices(snapshot, currentNodeId);
  }, [snapshot, currentNodeId]);

  const rootNodeId = snapshot?.root_node_id ?? null;

  const handleChoice = (choiceId: string) => {
    if (!snapshot || !currentNodeId) return;
    const choice = choices.find((item) => item.id === choiceId);
    if (!choice) return;

    setCurrentNodeId(choice.to_node_id);
    setHistory((prev) => [...prev, choice.to_node_id]);
    setEvents((prev) => [
      ...prev,
      createDraftRunnerEvent("choice_selected", {
        choice_id: choice.id,
        from_node_id: choice.from_node_id,
        to_node_id: choice.to_node_id,
        value: choice.value,
      }),
      createDraftRunnerEvent("node_entered", {
        node_id: choice.to_node_id,
        reason: "choice",
        via_choice_id: choice.id,
      }),
    ]);
  };

  const handleReset = () => {
    if (!snapshot) return;
    setCurrentNodeId(rootNodeId);
    setHistory(rootNodeId ? [rootNodeId] : []);
    setEvents((prev) => [
      ...prev,
      createDraftRunnerEvent("session_reset", { root_node_id: rootNodeId }),
      ...(rootNodeId
        ? [
            createDraftRunnerEvent("node_entered", {
              node_id: rootNodeId,
              reason: "reset",
            }),
          ]
        : []),
    ]);
  };

  if (loading) {
    return <div className="graph-loading">Загрузка чернового прогона...</div>;
  }

  if (error || !snapshot || !currentNode) {
    return (
      <div className="draft-runner-shell">
        <div className="draft-runner-error">
          <p>Не удалось запустить черновой прогон.</p>
          {error ? <p className="muted">{error}</p> : null}
          <div className="draft-runner-actions">
            <button className="secondary" onClick={() => navigate(`/projects/${projectId}/graphs/${graphId}`)}>
              Вернуться в редактор
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="draft-runner-shell">
      <section className="draft-runner-hero">
        <div>
          <button className="graph-back" onClick={() => navigate(`/projects/${projectId}/graphs/${graphId}`)}>
            ← Назад в граф
          </button>
          <h1>Черновой прогон: {snapshot.title}</h1>
          <p>{snapshot.description || "Preview-режим. Без сохранения прогресса и без игровой логики."}</p>
        </div>
        <div className="draft-runner-actions">
          <button className="secondary" onClick={handleReset}>
            Сбросить прогон
          </button>
          <button className="primary" onClick={() => navigate(`/projects/${projectId}`)}>
            К проекту
          </button>
        </div>
      </section>

      <section className="draft-runner-layout">
        <div className="draft-runner-main">
          <div className="draft-runner-card">
            <div className="draft-runner-card-header">
              <span className="writer-pill">{currentNode.scene_type === "decision" ? "Выбор" : "Сцена"}</span>
              <span className="muted">{currentNode.id}</span>
            </div>
            <h2>{currentNode.title}</h2>
            {currentNode.synopsis ? <p className="muted">{currentNode.synopsis}</p> : null}
            <div className="draft-runner-content">
              {currentNode.content || "Содержимое сцены отсутствует."}
            </div>
          </div>

          <div className="draft-runner-card">
            <h3>Переходы</h3>
            {choices.length === 0 ? (
              <p className="muted">Из этой сцены нет исходящих выборов.</p>
            ) : (
              <div className="draft-runner-choice-list">
                {choices.map((choice) => (
                  <button
                    key={choice.id}
                    type="button"
                    className="draft-runner-choice"
                    onClick={() => handleChoice(choice.id)}
                  >
                    <strong>{choice.label}</strong>
                    <span>→ {snapshot.nodes[choice.to_node_id]?.title || choice.to_node_id}</span>
                    {choice.condition ? (
                      <small>condition: {choice.condition} (preview не интерпретирует)</small>
                    ) : null}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <aside className="draft-runner-side">
          <div className="draft-runner-card">
            <h3>Data Exchange Rules</h3>
            <pre>{JSON.stringify(DRAFT_RUNNER_EXCHANGE_RULES, null, 2)}</pre>
          </div>

          <div className="draft-runner-card">
            <h3>Текущий state</h3>
            <ul>
              <li>graph_id: {snapshot.graph_id}</li>
              <li>current_node_id: {currentNodeId}</li>
              <li>history_length: {history.length}</li>
              <li>nodes: {snapshot.node_order.length}</li>
              <li>choices: {snapshot.choices.length}</li>
            </ul>
          </div>

          <div className="draft-runner-card">
            <h3>События</h3>
            <pre>{JSON.stringify(events, null, 2)}</pre>
          </div>
        </aside>
      </section>
    </div>
  );
}
