import type { GenerationJob } from "../shared/types";
import { getUnifiedGenerationJob } from "../api/generation";
import { useGenerationJobStore } from "../hooks/useGenerationJobStore";

const TERMINAL_STATUSES = new Set(["done", "failed", "canceled"]);

export async function waitForGenerationJob(
  jobId: string,
  opts?: {
    intervalMs?: number;
    maxAttempts?: number;
    maxTransientErrors?: number;
    onUpdate?: (job: GenerationJob) => void;
  },
): Promise<GenerationJob> {
  const intervalMs = opts?.intervalMs ?? 2000;
  const maxAttempts = opts?.maxAttempts ?? 600;
  const maxTransientErrors = opts?.maxTransientErrors ?? 8;
  let transientErrors = 0;
  let lastKnownJob: GenerationJob | null = null;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const job = await getUnifiedGenerationJob(jobId);
      transientErrors = 0;
      lastKnownJob = job;
      useGenerationJobStore.getState().upsert(job);
      if (opts?.onUpdate) {
        opts.onUpdate(job);
      }

      if (TERMINAL_STATUSES.has(job.status)) {
        return job;
      }
    } catch (error: any) {
      const code = String(error?.code || "");
      const isTransient = code === "ERR_NETWORK" || code === "ECONNABORTED" || !error?.response;
      if (!isTransient) {
        throw error;
      }
      transientErrors += 1;
      if (transientErrors > maxTransientErrors) {
        throw new Error(error?.message || "Generation status polling failed");
      }
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  try {
    const last = await getUnifiedGenerationJob(jobId);
    useGenerationJobStore.getState().upsert(last);
    if (opts?.onUpdate) {
      opts.onUpdate(last);
    }
    return last;
  } catch {
    if (lastKnownJob) {
      return lastKnownJob;
    }
    throw new Error("Generation status polling exceeded attempts");
  }
}
