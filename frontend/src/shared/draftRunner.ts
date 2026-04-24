import type { Edge, ScenarioGraph } from "./types";

export type DraftRunnerNodePayload = {
  id: string;
  title: string;
  content: string;
  synopsis: string | null;
  scene_type: "story" | "decision";
  order_index: number | null;
};

export type DraftRunnerChoicePayload = {
  id: string;
  from_node_id: string;
  to_node_id: string;
  label: string;
  value: string;
  condition: string | null;
  metadata: Record<string, unknown> | null;
};

export type DraftRunnerSnapshot = {
  version: "draft_runner/v1";
  graph_id: string;
  project_id: string;
  title: string;
  description: string | null;
  root_node_id: string | null;
  node_order: string[];
  nodes: Record<string, DraftRunnerNodePayload>;
  choices: DraftRunnerChoicePayload[];
};

export type DraftRunnerEventMap = {
  snapshot_loaded: {
    graph_id: string;
    root_node_id: string | null;
    node_count: number;
    choice_count: number;
  };
  node_entered: {
    node_id: string;
    reason: "initial" | "choice" | "reset";
    via_choice_id?: string;
  };
  choice_selected: {
    choice_id: string;
    from_node_id: string;
    to_node_id: string;
    value: string;
  };
  session_reset: {
    root_node_id: string | null;
  };
};

export type DraftRunnerEventType = keyof DraftRunnerEventMap;

export type DraftRunnerEvent<TType extends DraftRunnerEventType = DraftRunnerEventType> = {
  id: string;
  type: TType;
  timestamp: string;
  payload: DraftRunnerEventMap[TType];
};

export type DraftRunnerExchangeRules = {
  protocol: "draft_runner/v1";
  state_storage: "client_memory_only";
  condition_evaluation: "opaque_string";
  navigation: "direct_edge_by_choice";
  persistence: "disabled";
};

export const DRAFT_RUNNER_EXCHANGE_RULES: DraftRunnerExchangeRules = {
  protocol: "draft_runner/v1",
  state_storage: "client_memory_only",
  condition_evaluation: "opaque_string",
  navigation: "direct_edge_by_choice",
  persistence: "disabled",
};

const makeEventId = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `evt_${Date.now()}_${Math.random().toString(16).slice(2)}`;
};

const readChoiceValue = (edge: Edge) => {
  const raw = edge.edge_metadata?.choice_value;
  if (typeof raw === "string" && raw.trim()) return raw;
  if (raw === null || raw === undefined) return edge.choice_label || edge.id;
  return String(raw);
};

const normalizeNodeOrder = (graph: ScenarioGraph) => {
  return [...graph.scenes]
    .map((scene, index) => ({
      id: scene.id,
      order: typeof scene.order_index === "number" ? scene.order_index : Number.MAX_SAFE_INTEGER,
      index,
    }))
    .sort((a, b) => (a.order === b.order ? a.index - b.index : a.order - b.order))
    .map((item) => item.id);
};

export function buildDraftRunnerSnapshot(graph: ScenarioGraph): DraftRunnerSnapshot {
  const nodeOrder = normalizeNodeOrder(graph);
  const nodes: Record<string, DraftRunnerNodePayload> = {};
  graph.scenes.forEach((scene) => {
    nodes[scene.id] = {
      id: scene.id,
      title: scene.title,
      content: scene.content || "",
      synopsis: scene.synopsis ?? null,
      scene_type: scene.scene_type,
      order_index: scene.order_index ?? null,
    };
  });

  const choices: DraftRunnerChoicePayload[] = graph.edges.map((edge) => ({
    id: edge.id,
    from_node_id: edge.from_scene_id,
    to_node_id: edge.to_scene_id,
    label: edge.choice_label || "Продолжить",
    value: readChoiceValue(edge),
    condition: edge.condition ?? null,
    metadata: edge.edge_metadata ?? null,
  }));

  return {
    version: "draft_runner/v1",
    graph_id: graph.id,
    project_id: graph.project_id,
    title: graph.title,
    description: graph.description ?? null,
    root_node_id: graph.root_scene_id ?? nodeOrder[0] ?? null,
    node_order: nodeOrder,
    nodes,
    choices,
  };
}

export function getOutgoingChoices(snapshot: DraftRunnerSnapshot, nodeId: string): DraftRunnerChoicePayload[] {
  return snapshot.choices.filter((choice) => choice.from_node_id === nodeId);
}

export function createDraftRunnerEvent<TType extends DraftRunnerEventType>(
  type: TType,
  payload: DraftRunnerEventMap[TType],
): DraftRunnerEvent<TType> {
  return {
    id: makeEventId(),
    type,
    timestamp: new Date().toISOString(),
    payload,
  };
}
