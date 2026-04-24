import { Capacitor } from "@capacitor/core";

type CapacitorLike = {
  isNativePlatform?: () => boolean;
  getPlatform?: () => string;
};

function getCapacitorCandidates(): CapacitorLike[] {
  const runtime = globalThis as typeof globalThis & { Capacitor?: CapacitorLike };
  return [runtime.Capacitor, Capacitor].filter(Boolean) as CapacitorLike[];
}

export function isNativeShell(): boolean {
  return getCapacitorCandidates().some((candidate) => {
    if (typeof candidate.isNativePlatform === "function") {
      try {
        if (candidate.isNativePlatform()) {
          return true;
        }
      } catch {
        // Ignore runtime bridge issues and continue with other probes.
      }
    }

    if (typeof candidate.getPlatform === "function") {
      try {
        return candidate.getPlatform() !== "web";
      } catch {
        return false;
      }
    }

    return false;
  });
}

export function getRuntimePlatform(): string {
  for (const candidate of getCapacitorCandidates()) {
    if (typeof candidate.getPlatform !== "function") continue;
    try {
      const platform = candidate.getPlatform();
      if (platform && platform !== "web") {
        return platform;
      }
    } catch {
      // Ignore runtime bridge issues and continue with other probes.
    }
  }

  try {
    return Capacitor.getPlatform();
  } catch {
    return "web";
  }
}
