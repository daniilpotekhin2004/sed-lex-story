import axios, { type InternalAxiosRequestConfig } from "axios";
import {
  getComfyApiKey,
  getComfyApiUrl,
  getGenerationEnvironment,
  getPoeApiKey,
  getPoeApiUrl,
  getPoeModel,
} from "../utils/generationEnvironment";
import {
  getAccessTokenSnapshot,
  getAuthSession,
  persistAuthSession,
  subscribeToAuthSession,
} from "../auth/sessionStore";
import { getRuntimePlatform, isNativeShell } from "../utils/runtimePlatform";

function isBundledNativeOrigin(): boolean {
  if (typeof window === "undefined") return false;
  return window.location.origin === "http://localhost" || window.location.origin === "https://localhost";
}

function resolveApiBaseUrl() {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8888/api";
  const nativeBaseUrl = import.meta.env.VITE_NATIVE_API_BASE_URL;

  if (!isNativeShell() && !isBundledNativeOrigin()) {
    return configuredBaseUrl;
  }

  if (nativeBaseUrl) {
    return nativeBaseUrl;
  }

  try {
    const isRelativeBaseUrl = configuredBaseUrl.startsWith("/");
    const parsed = isRelativeBaseUrl
      ? new URL(configuredBaseUrl, "http://localhost:8888")
      : new URL(configuredBaseUrl);
    const isLoopbackHost =
      isRelativeBaseUrl || parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
    if (!isLoopbackHost) {
      return parsed.toString().replace(/\/$/, "");
    }

    const runtimePlatform = getRuntimePlatform();
    if (runtimePlatform === "android") {
      parsed.protocol = "http:";
      parsed.hostname = "10.0.2.2";
      parsed.port = parsed.port || "8888";
      return parsed.toString().replace(/\/$/, "");
    }

    if (runtimePlatform === "ios") {
      parsed.protocol = "http:";
      parsed.hostname = "127.0.0.1";
      parsed.port = parsed.port || "8888";
      return parsed.toString().replace(/\/$/, "");
    }

    return parsed.toString().replace(/\/$/, "");
  } catch {
    return configuredBaseUrl;
  }
}

const API_BASE_URL = resolveApiBaseUrl();
const AUTH_EXPIRED_EVENT = "lwq:auth-expired";
let lastAuthExpiredEventAt = 0;
let refreshPromise: Promise<string | null> | null = null;
let refreshBlocked = false;

// Extract base URL without /api suffix for assets
const BACKEND_BASE_URL = API_BASE_URL.replace(/\/api\/?$/, "");

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 2 minutes for image generation
});

const authClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
});

type RetryableRequestConfig = InternalAxiosRequestConfig & {
  _retry?: boolean;
};

function emitAuthExpired(payload: { status: number; url?: string }) {
  const now = Date.now();
  if (now - lastAuthExpiredEventAt < 1500) return;
  lastAuthExpiredEventAt = now;
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail: payload }));
}

/**
 * Convert relative asset URL to absolute URL pointing to backend
 * e.g. "/api/assets/generated/..." -> "http://localhost:8888/api/assets/generated/..."
 */
export function getAssetUrl(relativeUrl: string | null | undefined): string | undefined {
  if (!relativeUrl) return undefined;
  if (relativeUrl.startsWith("http")) return relativeUrl;
  return `${BACKEND_BASE_URL}${relativeUrl}`;
}

function ensureHeaders(config: InternalAxiosRequestConfig): InternalAxiosRequestConfig["headers"] {
  config.headers = config.headers ?? {};
  return config.headers;
}

function applyGenerationHeaders(config: InternalAxiosRequestConfig) {
  const headers = ensureHeaders(config);
  const env = getGenerationEnvironment();
  if (env === "comfy_api") {
    headers["X-SD-Provider"] = "comfy_api";
    const apiKey = getComfyApiKey();
    if (apiKey) {
      headers["X-Comfy-Api-Key"] = apiKey;
    }
    const apiUrl = getComfyApiUrl();
    if (apiUrl) {
      headers["X-Comfy-Api-Url"] = apiUrl;
    }
    return;
  }
  if (env === "poe_api") {
    headers["X-SD-Provider"] = "poe_api";
    const apiKey = getPoeApiKey();
    if (apiKey) {
      headers["X-Poe-Api-Key"] = apiKey;
    }
    const apiUrl = getPoeApiUrl();
    if (apiUrl) {
      headers["X-Poe-Api-Url"] = apiUrl;
    }
    const model = getPoeModel();
    if (model) {
      headers["X-Poe-Model"] = model;
    }
  }
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshBlocked) return null;
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const session = await getAuthSession();
    const refreshToken = session?.refreshToken;
    if (!refreshToken) {
      return null;
    }

    try {
      const response = await authClient.post<{
        access_token: string;
        refresh_token: string;
        token_type: string;
      }>("/auth/refresh", {
        refresh_token: refreshToken,
      });

      await persistAuthSession({
        accessToken: response.data.access_token,
        refreshToken: response.data.refresh_token,
      });
      refreshBlocked = false;
      return response.data.access_token;
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 401 || status === 403) {
        refreshBlocked = true;
      }
      throw error;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

subscribeToAuthSession((session) => {
  refreshPromise = null;
  if (session?.refreshToken) {
    refreshBlocked = false;
  }
});

apiClient.interceptors.request.use(async (config) => {
  const headers = ensureHeaders(config);
  const token = getAccessTokenSnapshot() ?? (await getAuthSession())?.accessToken ?? null;
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  applyGenerationHeaders(config);
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response) {
      const message =
        error.response.data?.detail || error.response.data?.message || error.response.data?.error;
      error.message = message || `Request failed with status ${error.response.status}`;

      const status = error.response.status;
      const request = error.config as RetryableRequestConfig | undefined;
      const url = String(request?.url || "");
      const isAuthEndpoint =
        url.includes("/auth/login") || url.includes("/auth/register") || url.includes("/auth/refresh");

      if ((status === 401 || status === 403) && request && !request._retry && !isAuthEndpoint) {
        request._retry = true;
        try {
          const refreshedAccessToken = await refreshAccessToken();
          if (refreshedAccessToken) {
            const headers = ensureHeaders(request);
            headers.Authorization = `Bearer ${refreshedAccessToken}`;
            return apiClient(request);
          }
        } catch {
          // Re-auth flow is handled below via AUTH_EXPIRED_EVENT.
        }
      }

      const hasToken = Boolean(getAccessTokenSnapshot() ?? (await getAuthSession())?.accessToken);
      if ((status === 401 || status === 403) && hasToken && !isAuthEndpoint) {
        emitAuthExpired({ status, url });
      }
    } else if (error.code === "ECONNABORTED") {
      error.message = "Request timeout: backend response took too long";
    } else if (error.code === "ERR_NETWORK") {
      error.message = "Network error: backend is unreachable";
    } else if (error.request) {
      error.message = "Request failed: no response from backend";
    }
    return Promise.reject(error);
  },
);

export { AUTH_EXPIRED_EVENT };
export { API_BASE_URL };
