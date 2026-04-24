import type { ProjectVoiceoverLine } from "./types";

export function selectApprovedAudioForSlide(
  lines: ProjectVoiceoverLine[] | undefined,
  slideIndex: number,
): string[] {
  if (!Array.isArray(lines) || lines.length === 0) return [];
  return lines
    .filter((line) => line.slide_index === slideIndex && Boolean(line.approved_audio_url))
    .sort((a, b) => a.order - b.order)
    .map((line) => line.approved_audio_url || "")
    .filter((url): url is string => Boolean(url));
}

export function selectApprovedSceneNarrationAudio(
  lines: ProjectVoiceoverLine[] | undefined,
): string | null {
  if (!Array.isArray(lines) || lines.length === 0) return null;
  const narration = lines
    .filter((line) => line.kind === "scene_narration" && Boolean(line.approved_audio_url))
    .sort((a, b) => a.order - b.order)[0];
  return narration?.approved_audio_url || null;
}
