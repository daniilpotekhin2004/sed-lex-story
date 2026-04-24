type EventPayload = Record<string, unknown>;

const STORAGE_KEY = "lexquest_events";

export function trackEvent(name: string, payload: EventPayload = {}): void {
  const entry = { name, payload, ts: Date.now() };
  try {
    const existing = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    existing.push(entry);
    const trimmed = existing.slice(-200); // keep recent window
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch (error) {
    // swallow: telemetry should never break UX
    console.warn("[telemetry] failed to buffer event", error);
  }
  if (import.meta.env.DEV) {
    // eslint-disable-next-line no-console
    console.info(`[event] ${name}`, payload);
  }
}

export function getBufferedEvents(): Array<{ name: string; payload: EventPayload; ts: number }> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

export function clearBufferedEvents(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function toApiPayloads(): Array<{ event_name: string; payload?: EventPayload }> {
  return getBufferedEvents().map((e) => ({
    event_name: e.name,
    payload: { ...e.payload, ts: e.ts },
  }));
}
