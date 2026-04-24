import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

async function loadSessionStore() {
  return import("./sessionStore");
}

function createLocalStorageMock() {
  const values = new Map<string, string>();
  return {
    getItem(key: string) {
      return values.has(key) ? values.get(key)! : null;
    },
    setItem(key: string, value: string) {
      values.set(key, String(value));
    },
    removeItem(key: string) {
      values.delete(key);
    },
    clear() {
      values.clear();
    },
  };
}

describe("sessionStore", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal("window", globalThis);
    vi.stubGlobal("localStorage", createLocalStorageMock());
    delete (globalThis as typeof globalThis & { Capacitor?: unknown }).Capacitor;
  });

  afterEach(() => {
    delete (globalThis as typeof globalThis & { Capacitor?: unknown }).Capacitor;
    vi.doUnmock("@aparajita/capacitor-secure-storage");
    vi.unstubAllGlobals();
  });

  it("persists and clears auth session with localStorage fallback", async () => {
    const store = await loadSessionStore();

    await store.persistAuthSession({
      accessToken: "access-1",
      refreshToken: "refresh-1",
    });

    expect(store.getAccessTokenSnapshot()).toBe("access-1");
    expect(store.getAuthStorageBackend()).toBe("local_storage");

    const persisted = localStorage.getItem(store.AUTH_SESSION_STORAGE_KEY);
    expect(persisted).toContain("access-1");
    expect(persisted).toContain("refresh-1");

    const session = await store.getAuthSession();
    expect(session).toMatchObject({
      accessToken: "access-1",
      refreshToken: "refresh-1",
    });

    await store.clearAuthSession();
    expect(store.getAccessTokenSnapshot()).toBeNull();
    expect(localStorage.getItem(store.AUTH_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("migrates legacy access and refresh tokens into the new session blob", async () => {
    localStorage.setItem("access_token", "legacy-access");
    localStorage.setItem("refresh_token", "legacy-refresh");

    const store = await loadSessionStore();
    const session = await store.getAuthSession();

    expect(session).toMatchObject({
      accessToken: "legacy-access",
      refreshToken: "legacy-refresh",
    });
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();
    expect(localStorage.getItem(store.AUTH_SESSION_STORAGE_KEY)).toContain("legacy-access");
  });

  it("uses native secure storage when a Capacitor secure storage plugin is available", async () => {
    const nativeValues = new Map<string, string>();
    const secureStorageMock = {
      getItem: vi.fn(async (key: string) => nativeValues.get(key) ?? null),
      setItem: vi.fn(async (key: string, value: string) => {
        nativeValues.set(key, value);
      }),
      removeItem: vi.fn(async (key: string) => {
        nativeValues.delete(key);
      }),
    };

    vi.doMock("@aparajita/capacitor-secure-storage", () => ({
      SecureStorage: secureStorageMock,
    }));

    (globalThis as typeof globalThis & { Capacitor?: unknown }).Capacitor = {
      isNativePlatform: () => true,
    };

    const store = await loadSessionStore();
    await store.persistAuthSession({
      accessToken: "native-access",
      refreshToken: "native-refresh",
    });

    expect(store.getAuthStorageBackend()).toBe("native_secure_storage");
    expect(secureStorageMock.setItem).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(store.AUTH_SESSION_STORAGE_KEY)).toBeNull();

    await store.clearAuthSession();
    expect(secureStorageMock.removeItem).toHaveBeenCalledTimes(1);
  });

  it("reads native secure storage payloads that expose the value as data", async () => {
    const storedSession = JSON.stringify({
      accessToken: "native-data-access",
      refreshToken: "native-data-refresh",
      updatedAt: "2026-03-23T08:00:00.000Z",
    });
    const secureStorageMock = {
      getItem: vi.fn(async () => ({ data: storedSession })),
      setItem: vi.fn(async () => {}),
      removeItem: vi.fn(async () => {}),
    };

    vi.doMock("@aparajita/capacitor-secure-storage", () => ({
      SecureStorage: secureStorageMock,
    }));

    (globalThis as typeof globalThis & { Capacitor?: unknown }).Capacitor = {
      isNativePlatform: () => true,
    };

    const store = await loadSessionStore();
    const session = await store.getAuthSession();

    expect(session).toMatchObject({
      accessToken: "native-data-access",
      refreshToken: "native-data-refresh",
    });
  });
});
