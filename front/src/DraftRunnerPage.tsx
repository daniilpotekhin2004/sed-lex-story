import { useMutation } from "@tanstack/react-query";
import { generateImage } from "../api/generation";
import type { GenerationParams } from "../shared/types";
import { useTaskStore } from "./useTaskStore";

export function useGenerateImage() {
  const addTask = useTaskStore((s) => s.addTask);

  return useMutation({
    mutationFn: async (payload: GenerationParams) => generateImage(payload),
    onSuccess: (data, variables) => {
      addTask({
        taskId: data.task_id,
        prompt: variables.prompt,
        createdAt: Date.now(),
      });
    },
  });
}
