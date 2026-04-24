import { SecureStorage } from "@aparajita/capacitor-secure-storage";

export const AUTH_SESSION_STORAGE_KEY = "lwq_auth_session";
export const LEGACY_ACCESS_TOKEN_KEY = "access_token";
export const LEGACY_REFRESH_TOKEN_KEY = "refresh_token";

export type AuthSessionTokens = {
  accessToken: string;
  refreshToken?: string | null;
};

export type StoredAuthSession = {
  accessToken: string;
  refreshToken: string | null;
  updatedAt: string;
};

export type AuthStorageBackend = "native_secure_storage" | "local_storage" | "memory";

type NativeStoragePlugin = {
  get: (
    options: { key: string },
  ) => Promise<{ value?: string | null; data?: string | null } | string | null | undefined>;
  set: (options: { key: string; value: string }) => Promise<void>;
  remove?: (options: { key: string }) => Promise<void>;
};

type SessionListener = (session: StoredAuthSession | null) => void;

const memoryStorage = new Map<string, string>();
const listeners = new Set<SessionListener>();

const hasLegacySessionSeed = Boolean(readLegacyLocalStorageSession());
let sessionCache: StoredAuthSession | null = getInitialSessionSeed();
let hasLoadedFromPersistentStorage = sessionCache !== null && !hasLegacySessionSeed;
let needsLegacyMigration = hasLegacySessionSeed;

function canUseLocalStorage(): boolean {
  try {
    return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
  } catch {
    return false;
  }
}

function getNativeStoragePlugin(): NativeStoragePlugin | null {
  const runtime = globalThis as typeof globalThis & {
    Capacitor?: {
      isNativePlatform?: () => boolean;
      getPlatform?: () => string;
    };
  };
  const capacitor = runtime.Capacitor;
  if (!capacitor) return null;

  const isNative =
    typeof capacitor.isNativePlatform === "function"
      ? capacitor.isNativePlatform()
      : typeof capacitor.getPlatform === "function"
        ? capacitor.getPlatform() !== "web"
        : false;

  if (!isNative) return null;

  if (
    typeof SecureStorage.getItem !== "function"
    || typeof SecureStorage.setItem !== "function"
    || typeof SecureStorage.removeItem !== "function"
  ) {
    return null;
  }

  return {
    get: async ({ key }) => SecureStorage.getItem(key),
    set: async ({ key, value }) => {
      await SecureStorage.setItem(key, value);
    },
    remove: async ({ key }) => {
      await SecureStorage.removeItem(key);
    },
  };
}

function safeLocalStorageGet(key: string): string | null {
  if (!canUseLocalStorage()) return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeLocalStorageSet(key: string, value: string): void {
  if (!canUseLocalStorage()) return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Ignore storage availability issues and rely on in-memory cache.
  }
}

function safeLocalStorageRemove(key: string): void {
  if (!canUseLocalStorage()) return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Ignore cleanup issues on locked-down browsers.
  }
}

function parseStoredAuthSession(raw: string | null): StoredAuthSession | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredAuthSession>;
    if (typeof parsed.accessToken !== "string" || !parsed.accessToken.trim()) {
      return null;
    }
    return {
      accessToken: parsed.accessToken,
      refreshToken: typeof parsed.refreshToken === "string" && parsed.refreshToken.trim()
        ? parsed.refreshToken
        : null,
      updatedAt: typeof parsed.updatedAt === "string" && parsed.updatedAt.trim()
        ? parsed.updatedAt
        : new Date(0).toISOString(),
    };
  } catch {
    return null;
  }
}

function readLegacyLocalStorageSession(): StoredAuthSession | null {
  const accessToken = safeLocalStorageGet(LEGACY_ACCESS_TOKEN_KEY);
  if (!accessToken) return null;

  const refreshToken = safeLocalStorageGet(LEGACY_REFRESH_TOKEN_KEY);
  return {
    accessToken,
    refreshToken: refreshToken && refreshToken.trim() ? refreshToken : null,
    updatedAt: new Date(0).toISOString(),
  };
}

function cleanupLegacyLocalStorageKeys(): void {
  safeLocalStorageRemove(LEGACY_ACCESS_TOKEN_KEY);
  safeLocalStorageRemove(LEGACY_REFRESH_TOKEN_KEY);
}

function getInitialSessionSeed(): StoredAuthSession | null {
  if (!canUseLocalStorage() || getNativeStoragePlugin()) {
    return null;
  }
  return parseStoredAuthSession(safeLocalStorageGet(AUTH_SESSION_STORAGE_KEY))
    ?? readLegacyLocalStorageSession();
}

function notifyListeners(nextSession: StoredAuthSession | null): void {
  listeners.forEach((listener) => listener(nextSession));
}

async function readPersistedRawValue(): Promise<string | null> {
  const nativePlugin = getNativeStoragePlugin();
  if (nativePlugin) {
    const result = await nativePlugin.get({ key: AUTH_SESSION_STORAGE_KEY });
    if (typeof result === "string") return result;
    return result?.value ?? result?.data ?? null;
  }

  if (canUseLocalStorage()) {
    return safeLocalStorageGet(AUTH_SESSION_STORAGE_KEY);
  }

  return memoryStorage.get(AUTH_SESSION_STORAGE_KEY) ?? null;
}

async function writePersistedRawValue(value: string): Promise<void> {
  const nativePlugin = getNativeStoragePlugin();
  if (nativePlugin) {
    await nativePlugin.set({ key: AUTH_SESSION_STORAGE_KEY, value });
    cleanupLegacyLocalStorageKeys();
    return;
  }

  if (canUseLocalStorage()) {
    safeLocalStorageSet(AUTH_SESSION_STORAGE_KEY, value);
    cleanupLegacyLocalStorageKeys();
    return;
  }

  memoryStorage.set(AUTH_SESSION_STORAGE_KEY, value);
}

async function removePersistedRawValue(): Promise<void> {
  const nativePlugin = getNativeStoragePlugin();
  if (nativePlugin) {
    if (typeof nativePlugin.remove === "function") {
      await nativePlugin.remove({ key: AUTH_SESSION_STORAGE_KEY });
    }
    cleanupLegacyLocalStorageKeys();
    return;
  }

  if (canUseLocalStorage()) {
    safeLocalStorageRemove(AUTH_SESSION_STORAGE_KEY);
    cleanupLegacyLocalStorageKeys();
    return;
  }

  memoryStorage.delete(AUTH_SESSION_STORAGE_KEY);
}

function buildStoredSession(tokens: AuthSessionTokens): StoredAuthSession {
  return {
    accessToken: tokens.accessToken,
    refreshToken: typeof tokens.refreshToken === "string" && tokens.refreshToken.trim()
      ? tokens.refreshToken
      : null,
    updatedAt: new Date().toISOString(),
  };
}

async function hydrateLegacySessionIfNeeded(): Promise<StoredAuthSession | null> {
  if (!canUseLocalStorage()) return null;
  const legacySession = readLegacyLocalStorageSession();
  if (!legacySession) return null;

  await writePersistedRawValue(JSON.stringify(legacySession));
  cleanupLegacyLocalStorageKeys();
  return legacySession;
}

export function getAuthStorageBackend(): AuthStorageBackend {
  if (getNativeStoragePlugin()) return "native_secure_storage";
  if (canUseLocalStorage()) return "local_storage";
  return "memory";
}

export function getAccessTokenSnapshot(): string | null {
  return sessionCache?.accessToken ?? null;
}

export function subscribeToAuthSession(listener: SessionListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export async function getAuthSession(): Promise<StoredAuthSession | null> {
  if (sessionCache && !needsLegacyMigration) {
    return sessionCache;
  }

  if (sessionCache && needsLegacyMigration) {
    await writePersistedRawValue(JSON.stringify(sessionCache));
    cleanupLegacyLocalStorageKeys();
    needsLegacyMigration = false;
    hasLoadedFromPersistentStorage = true;
    return sessionCache;
  }

  if (hasLoadedFromPersistentStorage) {
    return null;
  }

  const stored = parseStoredAuthSession(await readPersistedRawValue());
  const nextSession = stored ?? await hydrateLegacySessionIfNeeded();

  sessionCache = nextSession;
  hasLoadedFromPersistentStorage = true;
  needsLegacyMigration = false;
  notifyListeners(nextSession);
  return nextSession;
}

export async function persistAuthSession(tokens: AuthSessionTokens): Promise<StoredAuthSession> {
  const nextSession = buildStoredSession(tokens);
  sessionCache = nextSession;
  hasLoadedFromPersistentStorage = true;
  needsLegacyMigration = false;
  notifyListeners(nextSession);
  await writePersistedRawValue(JSON.stringify(nextSession));
  return nextSession;
}

export async function clearAuthSession(): Promise<void> {
  sessionCache = null;
  hasLoadedFromPersistentStorage = true;
  needsLegacyMigration = false;
  notifyListeners(null);
  await removePersistedRawValue();
}
