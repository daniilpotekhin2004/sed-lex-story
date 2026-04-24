export type GenerationEnvironment = "local" | "comfy_api" | "poe_api";

const ENV_KEY = "lwq_generation_env";
const COMFY_KEY = "lwq_comfy_api_key";
const COMFY_URL = "lwq_comfy_api_url";
const POE_KEY = "lwq_poe_api_key";
const POE_URL = "lwq_poe_api_url";
const POE_MODEL = "lwq_poe_model";

export function getGenerationEnvironment(): GenerationEnvironment {
  if (typeof localStorage === "undefined") return "local";
  const raw = localStorage.getItem(ENV_KEY);
  if (raw === "comfy_api" || raw === "poe_api") return raw;
  return "local";
}

export function setGenerationEnvironment(env: GenerationEnvironment) {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(ENV_KEY, env);
}

export function getComfyApiKey(): string {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem(COMFY_KEY) ?? "";
}

export function setComfyApiKey(value: string) {
  if (typeof localStorage === "undefined") return;
  const cleaned = value.trim();
  if (!cleaned) {
    localStorage.removeItem(COMFY_KEY);
    return;
  }
  localStorage.setItem(COMFY_KEY, cleaned);
}

export function getComfyApiUrl(): string {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem(COMFY_URL) ?? "";
}

export function setComfyApiUrl(value: string) {
  if (typeof localStorage === "undefined") return;
  const cleaned = value.trim();
  if (!cleaned) {
    localStorage.removeItem(COMFY_URL);
    return;
  }
  localStorage.setItem(COMFY_URL, cleaned);
}

export function getPoeApiKey(): string {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem(POE_KEY) ?? "";
}

export function setPoeApiKey(value: string) {
  if (typeof localStorage === "undefined") return;
  const cleaned = value.trim();
  if (!cleaned) {
    localStorage.removeItem(POE_KEY);
    return;
  }
  localStorage.setItem(POE_KEY, cleaned);
}

export function getPoeApiUrl(): string {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem(POE_URL) ?? "";
}

export function setPoeApiUrl(value: string) {
  if (typeof localStorage === "undefined") return;
  const cleaned = value.trim();
  if (!cleaned) {
    localStorage.removeItem(POE_URL);
    return;
  }
  localStorage.setItem(POE_URL, cleaned);
}

export function getPoeModel(): string {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem(POE_MODEL) ?? "";
}

export function setPoeModel(value: string) {
  if (typeof localStorage === "undefined") return;
  const cleaned = value.trim();
  if (!cleaned) {
    localStorage.removeItem(POE_MODEL);
    return;
  }
  localStorage.setItem(POE_MODEL, cleaned);
}
