import { create } from "zustand";
import type { TaskSummary } from "../shared/types";

type TaskStore = {
  tasks: TaskSummary[];
  addTask: (task: TaskSummary) => void;
  updateTask: (taskId: string, partial: Partial<TaskSummary>) => void;
  setTasks: (tasks: TaskSummary[]) => void;
  clear: () => void;
};

export const useTaskStore = create<TaskStore>((set) => ({
  tasks: [],
  addTask: (task) =>
    set((state) => ({
      tasks: [task, ...state.tasks.filter((t) => t.taskId !== task.taskId)],
    })),
  updateTask: (taskId, partial) =>
    set((state) => ({
      tasks: state.tasks.map((t) => (t.taskId === taskId ? { ...t, ...partial } : t)),
    })),
  setTasks: (tasks) => set({ tasks }),
  clear: () => set({ tasks: [] }),
}));
