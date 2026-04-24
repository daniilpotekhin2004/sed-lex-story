import type { ProjectExport } from "./types";

export type PlayableProject = {
  project_id: string;
  project_name: string;
  project_description?: string | null;
  graph_id: string;
  graph_title: string;
  graph_description?: string | null;
  root_scene_id?: string | null;
  scene_count: number;
  choice_count: number;
  package_version: string;
  updated_at: string;
};

export type PlayerPackage = {
  manifest: PlayableProject;
  export: ProjectExport;
};

export type PlayerCatalogResponse = {
  items: PlayableProject[];
};

export type PlayerRunStatus = "active" | "completed";

export type PlayerRunEventMap = {
  session_started: {
    source: "remote" | "cache";
    package_version?: string | null;
    root_node_id?: string | null;
  };
  node_entered: {
    node_id: string;
    reason: "initial" | "choice" | "reset" | "resume";
    via_choice_id?: string;
  };
  choice_selected: {
    choice_id: string;
    from_node_id: string;
    to_node_id: string;
    value: string;
  };
  session_reset: {
    root_node_id?: string | null;
  };
  session_completed: {
    node_id: string;
  };
};

export type PlayerRunEventType = keyof PlayerRunEventMap;

export type PlayerRunEvent<TType extends PlayerRunEventType = PlayerRunEventType> = {
  id: string;
  type: TType;
  timestamp: string;
  payload: PlayerRunEventMap[TType];
};

export type PlayerRunSyncRequest = {
  run_id: string;
  graph_id: string;
  package_version?: string | null;
  current_node_id?: string | null;
  status: PlayerRunStatus;
  events: PlayerRunEvent[];
};

export type PlayerRunSyncResponse = {
  run_id: string;
  accepted_count: number;
  duplicate_count: number;
  status: PlayerRunStatus;
  last_synced_at: string;
};

export type PlayerChoiceAggregate = {
  choice_id: string;
  label: string;
  selection_count: number;
};

export type PlayerOwnStats = {
  total_runs: number;
  completed_runs: number;
  last_run_id?: string | null;
  last_completed_at?: string | null;
  last_synced_at?: string | null;
  current_node_id?: string | null;
};

export type PlayerProjectStats = {
  project_id: string;
  graph_id: string;
  package_version: string;
  updated_at: string;
  total_runs: number;
  completed_runs: number;
  unique_players: number;
  completion_rate: number;
  choices: PlayerChoiceAggregate[];
  mine: PlayerOwnStats;
};

export type PlayerResume = {
  available: boolean;
  run_id?: string | null;
  graph_id?: string | null;
  package_version?: string | null;
  current_node_id?: string | null;
  status?: PlayerRunStatus | null;
  started_at?: string | null;
  last_synced_at?: string | null;
  scene_history: string[];
  session_values: Record<string, string>;
};

function makeEventId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `player_evt_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function createPlayerRunEvent<TType extends PlayerRunEventType>(
  type: TType,
  payload: PlayerRunEventMap[TType],
): PlayerRunEvent<TType> {
  return {
    id: makeEventId(),
    type,
    timestamp: new Date().toISOString(),
    payload,
  };
}
