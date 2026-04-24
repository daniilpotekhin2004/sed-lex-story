import { useQuery } from "@tanstack/react-query";
import { getTaskStatus } from "../api/generation";
import { useTaskStore } from "./useTaskStore";

const REFRESH_MS = 1200;

export function useTaskStatus(taskId: string | null) {
  const updateTask = useTaskStore((s) => s.updateTask);

  return useQuery({
    queryKey: ["task-status", taskId],
    queryFn: async () => {
      if (!taskId) {
        throw new Error("taskId is required");
      }
      return getTaskStatus(taskId);
    },
    enabled: Boolean(taskId),
    refetchInterval: (data) => {
      if (!data || !data.ready) return REFRESH_MS;
      return false;
    },
    onSuccess: (data) => {
      const paths =
        data.image_urls ??
        data.result?.image_urls ??
        data.result?.paths ??
        (data.result?.image_url ? [data.result.image_url] : undefined);
      updateTask(data.task_id, {
        lastState: data.state,
        success: data.success,
        error: data.error ?? undefined,
        outputs: paths,
      });
    },
    suspense: false,
  });
}
