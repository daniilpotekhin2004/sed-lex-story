export type ProjectDevelopmentMode = "creative" | "standard";

const MODE_KEY_PREFIX = "lwq_project_development_mode";

export const DEFAULT_PROJECT_DEVELOPMENT_MODE: ProjectDevelopmentMode = "creative";

const isProjectMode = (value: unknown): value is ProjectDevelopmentMode =>
  value === "creative" || value === "standard";

const buildKey = (projectId: string) => `${MODE_KEY_PREFIX}_${projectId}`;

export function getProjectDevelopmentMode(projectId?: string | null): ProjectDevelopmentMode {
  if (!projectId || typeof localStorage === "undefined") {
    return DEFAULT_PROJECT_DEVELOPMENT_MODE;
  }
  const raw = localStorage.getItem(buildKey(projectId));
  return isProjectMode(raw) ? raw : DEFAULT_PROJECT_DEVELOPMENT_MODE;
}

export function setProjectDevelopmentMode(projectId: string, mode: ProjectDevelopmentMode): void {
  if (!projectId || typeof localStorage === "undefined") return;
  localStorage.setItem(buildKey(projectId), mode);
}
