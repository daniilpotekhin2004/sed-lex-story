import { Directory, Encoding, Filesystem } from "@capacitor/filesystem";
import type { PlayerPackage } from "../shared/player";
import { isNativeShell } from "../utils/runtimePlatform";

const MANIFEST_KEY = "lwq_player_package_manifest_v1";
const WEB_PACKAGE_PREFIX = "lwq_player_package_";
const ROOT_DIR = "player-packages";

export type CachedPlayerPackageEntry = {
  projectId: string;
  packageVersion: string;
  cachedAt: string;
  lastOpenedAt: string;
  projectName: string;
  graphTitle: string;
  sceneCount: number;
  choiceCount: number;
  updatedAt: string;
};

type CacheManifest = Record<string, CachedPlayerPackageEntry>;

function readManifest(): CacheManifest {
  try {
    const raw = localStorage.getItem(MANIFEST_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as CacheManifest) : {};
  } catch {
    return {};
  }
}

function writeManifest(manifest: CacheManifest) {
  try {
    localStorage.setItem(MANIFEST_KEY, JSON.stringify(manifest));
  } catch {
    // Ignore storage failures and keep runtime working.
  }
}

function toEntry(pkg: PlayerPackage, now: string): CachedPlayerPackageEntry {
  return {
    projectId: pkg.manifest.project_id,
    packageVersion: pkg.manifest.package_version,
    cachedAt: now,
    lastOpenedAt: now,
    projectName: pkg.manifest.project_name,
    graphTitle: pkg.manifest.graph_title,
    sceneCount: pkg.manifest.scene_count,
    choiceCount: pkg.manifest.choice_count,
    updatedAt: pkg.manifest.updated_at,
  };
}

function buildNativePath(entry: CachedPlayerPackageEntry) {
  return `${ROOT_DIR}/${entry.projectId}/${entry.packageVersion}.json`;
}

function buildWebKey(projectId: string) {
  return `${WEB_PACKAGE_PREFIX}${projectId}`;
}

async function writeNativePackage(entry: CachedPlayerPackageEntry, pkg: PlayerPackage) {
  await Filesystem.writeFile({
    path: buildNativePath(entry),
    directory: Directory.Data,
    data: JSON.stringify(pkg),
    encoding: Encoding.UTF8,
    recursive: true,
  });
}

async function readNativePackage(entry: CachedPlayerPackageEntry) {
  try {
    const result = await Filesystem.readFile({
      path: buildNativePath(entry),
      directory: Directory.Data,
      encoding: Encoding.UTF8,
    });
    const raw = typeof result.data === "string" ? result.data : "";
    return JSON.parse(raw) as PlayerPackage;
  } catch {
    return null;
  }
}

async function deleteNativePackage(entry: CachedPlayerPackageEntry) {
  try {
    await Filesystem.deleteFile({
      path: buildNativePath(entry),
      directory: Directory.Data,
    });
  } catch {
    // Ignore stale file cleanup errors.
  }
}

function readWebPackage(projectId: string) {
  try {
    const raw = localStorage.getItem(buildWebKey(projectId));
    return raw ? (JSON.parse(raw) as PlayerPackage) : null;
  } catch {
    return null;
  }
}

function writeWebPackage(projectId: string, pkg: PlayerPackage) {
  try {
    localStorage.setItem(buildWebKey(projectId), JSON.stringify(pkg));
  } catch {
    // Ignore storage failures and keep runtime working.
  }
}

function deleteWebPackage(projectId: string) {
  try {
    localStorage.removeItem(buildWebKey(projectId));
  } catch {
    // Ignore storage failures and keep runtime working.
  }
}

export async function cachePlayerPackage(pkg: PlayerPackage) {
  const now = new Date().toISOString();
  const entry = toEntry(pkg, now);
  const manifest = readManifest();
  const previous = manifest[entry.projectId];

  if (isNativeShell()) {
    await writeNativePackage(entry, pkg);
    if (previous && previous.packageVersion !== entry.packageVersion) {
      await deleteNativePackage(previous);
    }
  } else {
    writeWebPackage(entry.projectId, pkg);
  }

  manifest[entry.projectId] = entry;
  writeManifest(manifest);
  return entry;
}

export async function loadCachedPlayerPackage(projectId: string) {
  const manifest = readManifest();
  const entry = manifest[projectId];
  if (!entry) return null;

  const pkg = isNativeShell() ? await readNativePackage(entry) : readWebPackage(projectId);
  if (!pkg) {
    delete manifest[projectId];
    writeManifest(manifest);
    return null;
  }

  manifest[projectId] = {
    ...entry,
    lastOpenedAt: new Date().toISOString(),
  };
  writeManifest(manifest);
  return pkg;
}

export async function listCachedPlayerPackages() {
  const manifest = readManifest();
  return Object.values(manifest).sort((left, right) =>
    (right.lastOpenedAt || right.cachedAt).localeCompare(left.lastOpenedAt || left.cachedAt),
  );
}

export async function removeCachedPlayerPackage(projectId: string) {
  const manifest = readManifest();
  const entry = manifest[projectId];
  if (!entry) return;

  if (isNativeShell()) {
    await deleteNativePackage(entry);
  } else {
    deleteWebPackage(projectId);
  }

  delete manifest[projectId];
  writeManifest(manifest);
}
