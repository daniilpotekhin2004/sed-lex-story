import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { createAssetGenerationJob, getUnifiedGenerationJob } from "../api/generation";
import type { GenerationJob, GenerationJobStartRequest } from "../shared/types";
import { useGenerationJobStore } from "./useGenerationJobStore";

type StartArgs = {
  entityId: string;
  overrides?: Record<string, any>;
  payload?: Record<string, any>;
  numVariants?: number;
  projectId?: string | null;
  styleProfileId?: string | null;
  kind?: string | null;
};

export type UseAssetGenerationArgs = {
  taskType: GenerationJobStartRequest["task_type"];
  entityType: GenerationJobStartRequest["entity_type"];
  projectId?: string | null;
  styleProfileId?: string | null;
  refetchIntervalMs?: number;
  /**
   * Called on every successful job poll (including intermediate progress updates).
   * Useful to refresh the affected entity (character/location/etc.) progressively.
   */
  onEntityRefresh?: (entityId: string, job: GenerationJob) => void | Promise<void>;
};

const isTerminalStatus = (status?: string) =>
  status === "done" || status === "failed" || status === "canceled";

export function useAssetGeneration(args: UseAssetGenerationArgs) {
  const {
    taskType,
    entityType,
    projectId,
    styleProfileId,
    refetchIntervalMs = 2000,
    onEntityRefresh,
  } = args;

  const upsertJob = useGenerationJobStore((s) => s.upsert);
  const [jobId, setJobId] = useState<string | null>(null);

  // When the generation context changes, stop tracking the previous job.
  useEffect(() => {
    setJobId(null);
  }, [taskType, entityType]);

  const startMutation = useMutation({
    mutationFn: async (startArgs: StartArgs) => {
      const req: GenerationJobStartRequest = {
        task_type: taskType,
        entity_type: entityType,
        entity_id: startArgs.entityId,
        project_id: startArgs.projectId ?? projectId ?? undefined,
        style_profile_id: startArgs.styleProfileId ?? styleProfileId ?? undefined,
        overrides: startArgs.overrides,
        payload: startArgs.payload,
        num_variants: startArgs.numVariants,
        kind: startArgs.kind ?? undefined,
      };
      return await createAssetGenerationJob(req);
    },
    onSuccess: (job) => {
      setJobId(job.id);
      upsertJob(job);
    },
  });

  const jobQuery = useQuery({
    queryKey: ["generationJob", jobId],
    queryFn: () => getUnifiedGenerationJob(jobId as string),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const job = query.state.data as GenerationJob | undefined;
      if (!job) return refetchIntervalMs;
      return isTerminalStatus(job.status) ? false : refetchIntervalMs;
    },
  });

  // Push job updates into the global store for the overlay.
  useEffect(() => {
    if (!jobQuery.data) return;
    upsertJob(jobQuery.data);
  }, [jobQuery.data, upsertJob]);

  // Progressive entity refresh.
  useEffect(() => {
    if (!jobQuery.data || !onEntityRefresh) return;
    // Do not block UI on refresh failures.
    Promise.resolve(onEntityRefresh(jobQuery.data.entity_id, jobQuery.data)).catch(() => undefined);
  }, [jobQuery.data?.status, jobQuery.data?.progress, jobQuery.data?.stage]);

  const isGenerating = useMemo(() => {
    const status = jobQuery.data?.status;
    return status === "queued" || status === "running";
  }, [jobQuery.data?.status]);

  return {
    start: startMutation.mutateAsync,
    startError: startMutation.error,
    startPending: startMutation.isPending,
    jobId,
    job: jobQuery.data,
    jobError: jobQuery.error,
    isGenerating,
    progress: jobQuery.data?.progress ?? 0,
    stage: jobQuery.data?.stage,
    status: jobQuery.data?.status,
    // For UI convenience
    isDone: jobQuery.data?.status === "done",
    isFailed: jobQuery.data?.status === "failed",
  };
}
