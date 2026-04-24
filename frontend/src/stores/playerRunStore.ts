import { syncPlayerRun } from "../api/player";
import type {
  PlayerRunEvent,
  PlayerRunStatus,
  PlayerRunSyncResponse,
} from "../shared/player";

const SESSION_PREFIX = "lwq_player_run_session_";
const QUEUE_PREFIX = "lwq_player_run_queue_";

export type PlayerRunSession = {
  runId: string;
  graphId: string;
  packageVersion: string | null;
  startedAt: string;
  status: PlayerRunStatus;
};

type EnsurePlayerRunSessionInput = {
  projectId: string;
  graphId: string;
  packageVersion?: string | null;
  preferredRunId?: string | null;
  preferredStatus?: PlayerRunStatus | null;
};

type FlushPlayerRunInput = {
  projectId: string;
  graphId: string;
  packageVersion?: string | null;
  currentNodeId?: string | null;
  status: PlayerRunStatus;
};

function buildSessionKey(projectId: string) {
  return `${SESSION_PREFIX}${projectId}`;
}

function buildQueueKey(projectId: string) {
  return `${QUEUE_PREFIX}${projectId}`;
}

function makeRunId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `player_run_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function readSession(projectId: string): PlayerRunSession | null {
  try {
    const raw = localStorage.getItem(buildSessionKey(projectId));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as PlayerRunSession;
  } catch {
    return null;
  }
}

function writeSession(projectId: string, session: PlayerRunSession) {
  try {
    localStorage.setItem(buildSessionKey(projectId), JSON.stringify(session));
  } catch {
    // Ignore storage failures and keep runtime working.
  }
}

function readQueue(projectId: string): PlayerRunEvent[] {
  try {
    const raw = localStorage.getItem(buildQueueKey(projectId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as PlayerRunEvent[]) : [];
  } catch {
    return [];
  }
}

function writeQueue(projectId: string, events: PlayerRunEvent[]) {
  try {
    localStorage.setItem(buildQueueKey(projectId), JSON.stringify(events));
  } catch {
    // Ignore storage failures and keep runtime working.
  }
}

export async function ensurePlayerRunSession(input: EnsurePlayerRunSessionInput) {
  const expectedVersion = input.packageVersion ?? null;
  const existing = readSession(input.projectId);
  if (
    existing &&
    existing.graphId === input.graphId &&
    existing.packageVersion === expectedVersion &&
    existing.status !== "completed"
  ) {
    return { session: existing, isNew: false };
  }

  if (input.preferredRunId) {
    const resumed: PlayerRunSession = {
      runId: input.preferredRunId,
      graphId: input.graphId,
      packageVersion: expectedVersion,
      startedAt: existing?.startedAt || new Date().toISOString(),
      status: input.preferredStatus ?? "active",
    };
    writeSession(input.projectId, resumed);
    writeQueue(input.projectId, []);
    return { session: resumed, isNew: false };
  }

  const next: PlayerRunSession = {
    runId: makeRunId(),
    graphId: input.graphId,
    packageVersion: expectedVersion,
    startedAt: new Date().toISOString(),
    status: "active",
  };
  writeSession(input.projectId, next);
  writeQueue(input.projectId, []);
  return { session: next, isNew: true };
}

export async function appendQueuedPlayerRunEvents(projectId: string, events: PlayerRunEvent[]) {
  if (events.length === 0) return;
  const queue = readQueue(projectId);
  const knownIds = new Set(queue.map((event) => event.id));
  const merged = [...queue];
  events.forEach((event) => {
    if (!knownIds.has(event.id)) {
      merged.push(event);
      knownIds.add(event.id);
    }
  });
  writeQueue(projectId, merged);
}

export async function flushQueuedPlayerRunEvents(input: FlushPlayerRunInput): Promise<PlayerRunSyncResponse | null> {
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    return null;
  }

  const session = readSession(input.projectId);
  if (!session) return null;

  const events = readQueue(input.projectId);
  if (events.length === 0 && session.status === input.status) {
    return null;
  }

  try {
    const response = await syncPlayerRun(input.projectId, {
      run_id: session.runId,
      graph_id: input.graphId,
      package_version: input.packageVersion ?? null,
      current_node_id: input.currentNodeId ?? null,
      status: input.status,
      events,
    });
    writeQueue(input.projectId, []);
    writeSession(input.projectId, {
      ...session,
      graphId: input.graphId,
      packageVersion: input.packageVersion ?? null,
      status: response.status,
    });
    return response;
  } catch {
    return null;
  }
}

export async function markPlayerRunCompleted(projectId: string) {
  const session = readSession(projectId);
  if (!session) return;
  writeSession(projectId, { ...session, status: "completed" });
}

export async function clearQueuedPlayerRunEvents(projectId: string) {
  writeQueue(projectId, []);
}

export async function getQueuedPlayerRunCount(projectId: string) {
  return readQueue(projectId).length;
}

export async function getPlayerRunSession(projectId: string) {
  return readSession(projectId);
}
