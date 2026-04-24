import React, { useMemo } from "react";

import type { GenerationJob } from "../shared/types";
import { useGenerationJobStore } from "../hooks/useGenerationJobStore";

function isActiveJob(job: GenerationJob): boolean {
  return job.status === "queued" || job.status === "running";
}

function formatTaskLabel(taskType?: string): string {
  switch (taskType) {
    case "character_sheet":
      return "Генерация референсов персонажа";
    case "character_sketch":
      return "Скетч персонажа";
    case "character_reference":
      return "Перегенерация референса";
    case "character_render":
      return "Рендер персонажа";
    case "location_sheet":
      return "Генерация референсов локации";
    case "location_sketch":
      return "Скетч локации";
    case "artifact_sketch":
      return "Скетч артефакта";
    case "scene_generate":
      return "Генерация сцены";
    default:
      return "Генерация";
  }
}

function formatEntityLabel(job: GenerationJob): string {
  const entityType = job.entity_type;
  if (!entityType) return "";
  const base = entityType.replaceAll("_", " ");
  return job.entity_id ? `${base} #${job.entity_id}` : base;
}

export function GenerationProgressOverlay() {
  const jobsMap = useGenerationJobStore((s) => s.jobs);

  const activeJobs = useMemo(() => {
    const jobs = Object.values(jobsMap || {}).filter(isActiveJob);
    // Prefer newest first (best-effort ordering)
    jobs.sort((a, b) => {
      const at = a.updated_at ? Date.parse(a.updated_at) : 0;
      const bt = b.updated_at ? Date.parse(b.updated_at) : 0;
      return bt - at;
    });
    return jobs;
  }, [jobsMap]);

  if (!activeJobs.length) return null;
  const totalJobs = activeJobs.length;
  const taskNoun = (() => {
    const mod10 = totalJobs % 10;
    const mod100 = totalJobs % 100;
    if (mod10 === 1 && mod100 !== 11) return "задача";
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "задачи";
    return "задач";
  })();
  const runningLabel = totalJobs === 1 ? "Выполняется 1 задача" : `Выполняются ${totalJobs} ${taskNoun}`;

  return (
    <div className="gen-overlay" aria-live="polite" aria-label="Прогресс генерации">
      <div className="card gen-overlay-summary">
        <div className="gen-overlay-summary-row">
          <span className="gen-overlay-summary-pill">⏳</span>
          <span className="gen-overlay-summary-text">{runningLabel}</span>
        </div>
      </div>
      {activeJobs.map((job) => {
        const progress = Math.max(0, Math.min(100, job.progress ?? 0));
        return (
          <div key={job.id} className="card gen-overlay-card">
            <div className="gen-overlay-row">
              <div className="gen-overlay-main">
                <div className="gen-overlay-title">{formatTaskLabel(job.task_type)}</div>
                <div className="muted gen-overlay-subtitle">{formatEntityLabel(job)}</div>
              </div>
              <div className="gen-overlay-percent">{progress}%</div>
            </div>
            <div className="gen-overlay-bar" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
              <div className="gen-overlay-bar-fill" style={{ width: `${progress}%` }} />
            </div>
            {job.stage ? <div className="muted gen-overlay-stage">{job.stage}</div> : null}
          </div>
        );
      })}
    </div>
  );
}
