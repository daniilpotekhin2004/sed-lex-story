import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

async function loadStore() {
  return import("./playerPackageStore");
}

describe("playerPackageStore", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal("window", globalThis);
    vi.stubGlobal("localStorage", createLocalStorageMock());
    vi.doMock("@capacitor/core", () => ({
      Capacitor: {
        isNativePlatform: () => false,
        getPlatform: () => "web",
      },
    }));
    vi.doMock("@capacitor/filesystem", () => ({
      Directory: { Data: "DATA" },
      Encoding: { UTF8: "utf8" },
      Filesystem: {},
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.doUnmock("@capacitor/core");
    vi.doUnmock("@capacitor/filesystem");
  });

  it("caches and loads a player package with the web fallback", async () => {
    const store = await loadStore();
    const pkg = {
      manifest: {
        project_id: "project-1",
        project_name: "Project One",
        graph_id: "graph-1",
        graph_title: "Main Graph",
        scene_count: 2,
        choice_count: 1,
        package_version: "version-1",
        updated_at: "2026-03-12T10:00:00Z",
      },
      export: {
        project: { id: "project-1", name: "Project One" },
        graph: { id: "graph-1", scenes: [], edges: [], root_scene_id: null },
        legal_concepts: [],
        scenes: [],
      },
    } as any;

    const entry = await store.cachePlayerPackage(pkg);
    expect(entry.projectId).toBe("project-1");

    const loaded = await store.loadCachedPlayerPackage("project-1");
    expect(loaded?.manifest.package_version).toBe("version-1");

    const items = await store.listCachedPlayerPackages();
    expect(items).toHaveLength(1);
    expect(items[0]?.projectName).toBe("Project One");
  });
});
