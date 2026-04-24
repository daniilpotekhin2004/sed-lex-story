import { useQuery } from "@tanstack/react-query";
import { listTasks } from "../api/generation";
import type { TaskListResponse } from "../shared/types";

type Params = {
  page?: number;
  page_size?: number;
};

export function useTasks(params: Params) {
  return useQuery<TaskListResponse>({
    queryKey: ["tasks", params],
    queryFn: () => listTasks(params),
    keepPreviousData: true,
  });
}
