import { apiClient } from "./client";

export type TelemetryEventPayload = {
  event_name: string;
  payload?: Record<string, unknown>;
};

export async function sendTelemetry(events: TelemetryEventPayload[]): Promise<void> {
  // fire-and-forget, sequential to preserve order
  for (const ev of events) {
    try {
      await apiClient.post("/telemetry/events", ev);
    } catch (error) {
      // do not throw: telemetry must be best-effort
      console.warn("[telemetry] failed to send event", ev.event_name, error);
    }
  }
}
