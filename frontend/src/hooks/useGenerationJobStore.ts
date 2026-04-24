import { create } from "zustand";

import type { GenerationJob } from "../shared/types";

type GenerationJobStoreState = {
  jobs: Record<string, GenerationJob>;
  upsert: (job: GenerationJob) => void;
  bulkUpsert: (jobs: GenerationJob[]) => void;
  clear: () => void;
};

export const useGenerationJobStore = create<GenerationJobStoreState>((set) => ({
  jobs: {},
  upsert: (job) =>
    set((state) => ({
      jobs: {
        ...state.jobs,
        [job.id]: job,
      },
    })),
  bulkUpsert: (jobs) =>
    set((state) => {
      const next = { ...state.jobs };
      for (const job of jobs) {
        next[job.id] = job;
      }
      return { jobs: next };
    }),
  clear: () => set({ jobs: {} }),
}));
