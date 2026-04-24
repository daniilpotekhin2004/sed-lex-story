import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  approveProjectVoiceoverLine,
  generateProjectVoiceoverLine,
  getProject,
  getProjectVoiceover,
  updateProjectVoiceoverSettings,
} from "../api/projects";
import type {
  ProjectVoiceoverLine,
  ProjectVoiceoverRead,
  ProjectVoiceoverRolePrompts,
  ProjectVoiceoverSettings,
} from "../shared/types";

type GroupMode = "timeline" | "character";

type GroupBucket = {
  id: string;
  title: string;
  lines: ProjectVoiceoverLine[];
};

type RolePromptState = {
  narrator: string;
  inner_voice: string;
  interlocutor: string;
};

type CharacterPromptTarget = {
  id: string;
  label: string;
  kind: "character" | "speaker";
};

type BatchQueueItem = {
  line: ProjectVoiceoverLine;
  sortPrompt: string;
  explicitVoiceProfile: string | null;
};

type BatchProgress = {
  total: number;
  completed: number;
  remaining: number;
  errors: number;
  skipped: number;
  currentLabel: string | null;
};

const lineKindLabel: Record<ProjectVoiceoverLine["kind"], string> = {
  scene_narration: "Сцена",
  exposition: "Экспозиция",
  thought: "Мысли",
  dialogue: "Реплика",
};

function normalizeSpeaker(line: ProjectVoiceoverLine) {
  const speaker = (line.speaker || "").trim();
  if (speaker) return speaker;
  return line.kind === "scene_narration" || line.kind === "exposition" ? "Narrator" : "Без спикера";
}

function lineMeta(line: ProjectVoiceoverLine) {
  if (line.slide_index === null || line.slide_index === undefined) {
    return `Сцена: ${line.scene_title}`;
  }
  const slideNum = line.slide_index + 1;
  return line.slide_title ? `Сцена: ${line.scene_title} · Слайд ${slideNum} (${line.slide_title})` : `Сцена: ${line.scene_title} · Слайд ${slideNum}`;
}

function formatDuration(seconds?: number): string {
  if (!seconds || !Number.isFinite(seconds) || seconds <= 0) return "--:--";
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function normalizeSpeakerKey(value: string | null | undefined): string {
  return (value || "").trim().toLowerCase();
}

function normalizeRolePrompts(source?: ProjectVoiceoverRolePrompts | null): RolePromptState {
  return {
    narrator: source?.narrator?.trim() || "",
    inner_voice: source?.inner_voice?.trim() || "",
    interlocutor: source?.interlocutor?.trim() || "",
  };
}

function normalizeMap(source?: Record<string, string> | null): Record<string, string> {
  if (!source) return {};
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(source)) {
    const cleanKey = key.trim();
    const cleanValue = (value || "").trim();
    if (cleanKey && cleanValue) {
      out[cleanKey] = cleanValue;
    }
  }
  return out;
}

export default function ProjectVoiceoverPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [projectName, setProjectName] = useState<string>("Проект");
  const [voiceover, setVoiceover] = useState<ProjectVoiceoverRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [groupMode, setGroupMode] = useState<GroupMode>("timeline");
  const [language, setLanguage] = useState("ru");
  const [defaultVoiceProfile, setDefaultVoiceProfile] = useState("");
  const [replaceExisting, setReplaceExisting] = useState(false);
  const [skipApproved, setSkipApproved] = useState(true);
  const [lineVoiceProfiles, setLineVoiceProfiles] = useState<Record<string, string>>({});
  const [generatingAll, setGeneratingAll] = useState(false);
  const [batchProgress, setBatchProgress] = useState<BatchProgress | null>(null);
  const [lineGeneratingId, setLineGeneratingId] = useState<string | null>(null);
  const [lineApprovingKey, setLineApprovingKey] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [variantPlaybackKey, setVariantPlaybackKey] = useState<string | null>(null);
  const [variantPlaybackStatus, setVariantPlaybackStatus] = useState<"idle" | "loading" | "playing" | "paused">("idle");
  const [variantProgress, setVariantProgress] = useState<Record<string, number>>({});
  const [variantDurations, setVariantDurations] = useState<Record<string, number>>({});
  const variantAudioRef = useRef<HTMLAudioElement | null>(null);
  const variantAudioKeyRef = useRef<string | null>(null);
  const [rolePrompts, setRolePrompts] = useState<RolePromptState>({
    narrator: "",
    inner_voice: "",
    interlocutor: "",
  });
  const [suggestedRolePrompts, setSuggestedRolePrompts] = useState<RolePromptState>({
    narrator: "",
    inner_voice: "",
    interlocutor: "",
  });
  const [characterPrompts, setCharacterPrompts] = useState<Record<string, string>>({});
  const [speakerPrompts, setSpeakerPrompts] = useState<Record<string, string>>({});

  const hydrateLineProfiles = useCallback((lines: ProjectVoiceoverLine[]) => {
    setLineVoiceProfiles((prev) => {
      const next = { ...prev };
      for (const line of lines) {
        if (next[line.id] === undefined) {
          next[line.id] = line.voice_profile || "";
        }
      }
      return next;
    });
  }, []);

  const hydrateSettings = useCallback((payload: ProjectVoiceoverRead) => {
    const settings: ProjectVoiceoverSettings = payload.settings || {};
    const normalizedRoles = normalizeRolePrompts(settings.role_prompts);
    const normalizedSuggested = normalizeRolePrompts(payload.suggested_role_prompts);
    setRolePrompts(normalizedRoles);
    setSuggestedRolePrompts(normalizedSuggested);
    setCharacterPrompts(normalizeMap(settings.character_prompts || {}));
    setSpeakerPrompts(normalizeMap(settings.speaker_prompts || {}));
    if (settings.language?.trim()) {
      setLanguage(settings.language.trim());
    }
    if (settings.voice_profile?.trim()) {
      setDefaultVoiceProfile(settings.voice_profile.trim());
    }
  }, []);

  const hydrateSettingsParts = useCallback(
    (settings?: ProjectVoiceoverSettings, suggested?: ProjectVoiceoverRolePrompts) => {
      if (settings) {
        setRolePrompts(normalizeRolePrompts(settings.role_prompts));
        setCharacterPrompts(normalizeMap(settings.character_prompts || {}));
        setSpeakerPrompts(normalizeMap(settings.speaker_prompts || {}));
        if (settings.language?.trim()) {
          setLanguage(settings.language.trim());
        }
      }
      if (suggested) {
        setSuggestedRolePrompts(normalizeRolePrompts(suggested));
      }
    },
    [],
  );

  const loadVoiceover = useCallback(async () => {
    if (!projectId) return;
    const response = await getProjectVoiceover(projectId);
    setVoiceover(response);
    hydrateLineProfiles(response.lines || []);
    hydrateSettings(response);
  }, [hydrateLineProfiles, hydrateSettings, projectId]);

  useEffect(() => {
    if (!projectId) {
      setError("Не выбран проект");
      setLoading(false);
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        setLoading(true);
        setError(null);
        const [project, voiceoverData] = await Promise.all([getProject(projectId), getProjectVoiceover(projectId)]);
        if (cancelled) return;
        setProjectName(project.name || "Проект");
        setVoiceover(voiceoverData);
        hydrateLineProfiles(voiceoverData.lines || []);
        hydrateSettings(voiceoverData);
      } catch (err: any) {
        if (cancelled) return;
        setError(err?.message || "Не удалось загрузить интерфейс озвучки");
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [hydrateLineProfiles, hydrateSettings, projectId]);

  const groupedLines = useMemo<GroupBucket[]>(() => {
    const lines = [...(voiceover?.lines || [])].sort((a, b) => a.order - b.order);
    if (groupMode === "timeline") {
      const buckets = new Map<string, GroupBucket>();
      for (const line of lines) {
        const key = `${line.scene_id}`;
        const title = `Сцена ${line.scene_order}: ${line.scene_title}`;
        const existing = buckets.get(key);
        if (existing) {
          existing.lines.push(line);
        } else {
          buckets.set(key, { id: key, title, lines: [line] });
        }
      }
      return Array.from(buckets.values());
    }

    const buckets = new Map<string, GroupBucket>();
    for (const line of lines) {
      const speaker = normalizeSpeaker(line);
      const key = speaker.toLowerCase();
      const existing = buckets.get(key);
      if (existing) {
        existing.lines.push(line);
      } else {
        buckets.set(key, { id: key, title: speaker, lines: [line] });
      }
    }
    return Array.from(buckets.values()).sort((a, b) => a.title.localeCompare(b.title));
  }, [groupMode, voiceover?.lines]);

  const characterPromptTargets = useMemo<CharacterPromptTarget[]>(() => {
    const byId = new Map<string, CharacterPromptTarget>();
    const bySpeaker = new Map<string, CharacterPromptTarget>();
    for (const line of voiceover?.lines || []) {
      if (line.kind !== "dialogue") continue;
      const speaker = normalizeSpeaker(line);
      if (line.character_id) {
        if (!byId.has(line.character_id)) {
          byId.set(line.character_id, {
            id: line.character_id,
            label: `${speaker} (${line.character_id.slice(0, 8)})`,
            kind: "character",
          });
        }
        continue;
      }
      const speakerKey = normalizeSpeakerKey(speaker);
      if (!speakerKey || bySpeaker.has(speakerKey)) continue;
      bySpeaker.set(speakerKey, { id: speakerKey, label: speaker, kind: "speaker" });
    }
    return [...Array.from(byId.values()), ...Array.from(bySpeaker.values())].sort((a, b) =>
      a.label.localeCompare(b.label),
    );
  }, [voiceover?.lines]);

  const summary = voiceover?.summary;

  useEffect(() => {
    const lines = voiceover?.lines || [];
    if (lines.length === 0) return;

    setCharacterPrompts((prev) => {
      const next = { ...prev };
      for (const target of characterPromptTargets) {
        if (target.kind !== "character") continue;
        if (next[target.id] !== undefined) continue;
        const seed = lines.find((line) => line.character_id === target.id && (line.voice_profile || "").trim());
        if (seed?.voice_profile) {
          next[target.id] = seed.voice_profile.trim();
        }
      }
      return next;
    });

    setSpeakerPrompts((prev) => {
      const next = { ...prev };
      for (const target of characterPromptTargets) {
        if (target.kind !== "speaker") continue;
        if (next[target.id] !== undefined) continue;
        const seed = lines.find(
          (line) =>
            line.kind === "dialogue" &&
            normalizeSpeakerKey(normalizeSpeaker(line)) === target.id &&
            (line.voice_profile || "").trim(),
        );
        if (seed?.voice_profile) {
          next[target.id] = seed.voice_profile.trim();
        }
      }
      return next;
    });
  }, [characterPromptTargets, voiceover?.lines]);

  const applyLineUpdate = useCallback((
    line: ProjectVoiceoverLine,
    summaryData: ProjectVoiceoverRead["summary"],
    settings?: ProjectVoiceoverSettings,
    suggested?: ProjectVoiceoverRolePrompts,
  ) => {
    setVoiceover((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        lines: prev.lines.map((item) => (item.id === line.id ? line : item)),
        summary: summaryData,
        settings: settings ?? prev.settings,
        suggested_role_prompts: suggested ?? prev.suggested_role_prompts,
      };
    });
  }, []);

  const resolveFallbackProfileForLine = useCallback(
    (line: ProjectVoiceoverLine): string => {
      if (line.kind === "scene_narration" || line.kind === "exposition") {
        return rolePrompts.narrator;
      }
      if (line.kind === "thought") {
        return rolePrompts.inner_voice;
      }
      if (line.kind !== "dialogue") {
        return "";
      }
      if (line.character_id && characterPrompts[line.character_id]) {
        return characterPrompts[line.character_id];
      }
      const speakerKey = normalizeSpeakerKey(normalizeSpeaker(line));
      if (speakerKey && speakerPrompts[speakerKey]) {
        return speakerPrompts[speakerKey];
      }
      return rolePrompts.interlocutor;
    },
    [characterPrompts, rolePrompts.inner_voice, rolePrompts.interlocutor, rolePrompts.narrator, speakerPrompts],
  );

  const makeVariantKey = useCallback((lineId: string, variantId: string) => `${lineId}:${variantId}`, []);

  const stopVariantAudio = useCallback(
    (resetProgress = false) => {
      const audio = variantAudioRef.current;
      const activeKey = variantAudioKeyRef.current;
      if (audio) {
        audio.pause();
        audio.onended = null;
        audio.onpause = null;
        audio.onplay = null;
        audio.ontimeupdate = null;
        audio.onloadedmetadata = null;
        audio.onerror = null;
      }
      if (resetProgress && activeKey) {
        setVariantProgress((prev) => ({ ...prev, [activeKey]: 0 }));
      }
      variantAudioRef.current = null;
      variantAudioKeyRef.current = null;
      setVariantPlaybackKey(null);
      setVariantPlaybackStatus("idle");
    },
    [],
  );

  const handleToggleVariantPlayback = useCallback(
    async (lineId: string, variantId: string, audioUrl: string) => {
      const key = makeVariantKey(lineId, variantId);
      const currentAudio = variantAudioRef.current;
      const currentKey = variantAudioKeyRef.current;

      if (currentAudio && currentKey === key) {
        if (!currentAudio.paused) {
          currentAudio.pause();
          setVariantPlaybackStatus("paused");
          return;
        }
        setVariantPlaybackStatus("loading");
        try {
          await currentAudio.play();
          setVariantPlaybackStatus("playing");
        } catch {
          setVariantPlaybackStatus("idle");
          setVariantPlaybackKey(null);
          variantAudioRef.current = null;
          variantAudioKeyRef.current = null;
          setError("Не удалось воспроизвести вариант озвучки.");
        }
        return;
      }

      stopVariantAudio();
      setVariantPlaybackKey(key);
      setVariantPlaybackStatus("loading");
      setVariantProgress((prev) => ({ ...prev, [key]: 0 }));

      const audio = new Audio(audioUrl);
      variantAudioRef.current = audio;
      variantAudioKeyRef.current = key;

      audio.ontimeupdate = () => {
        if (!Number.isFinite(audio.duration) || audio.duration <= 0) return;
        const progress = Math.max(0, Math.min(1, audio.currentTime / audio.duration));
        setVariantProgress((prev) => {
          if (Math.abs((prev[key] || 0) - progress) < 0.01) return prev;
          return { ...prev, [key]: progress };
        });
      };
      audio.onloadedmetadata = () => {
        if (!Number.isFinite(audio.duration) || audio.duration <= 0) return;
        const progress = Math.max(0, Math.min(1, audio.currentTime / audio.duration));
        setVariantProgress((prev) => ({ ...prev, [key]: progress }));
      };
      audio.onplay = () => setVariantPlaybackStatus("playing");
      audio.onpause = () => {
        if (audio.ended) return;
        setVariantPlaybackStatus("paused");
      };
      audio.onended = () => {
        setVariantProgress((prev) => ({ ...prev, [key]: 1 }));
        variantAudioRef.current = null;
        variantAudioKeyRef.current = null;
        setVariantPlaybackKey(null);
        setVariantPlaybackStatus("idle");
      };
      audio.onerror = () => {
        variantAudioRef.current = null;
        variantAudioKeyRef.current = null;
        setVariantPlaybackKey(null);
        setVariantPlaybackStatus("idle");
        setError("Не удалось воспроизвести вариант озвучки.");
      };

      try {
        await audio.play();
      } catch {
        variantAudioRef.current = null;
        variantAudioKeyRef.current = null;
        setVariantPlaybackKey(null);
        setVariantPlaybackStatus("idle");
        setError("Браузер заблокировал воспроизведение. Кликните ещё раз.");
      }
    },
    [makeVariantKey, stopVariantAudio],
  );

  useEffect(() => {
    return () => {
      stopVariantAudio();
    };
  }, [stopVariantAudio]);

  useEffect(() => {
    const lines = voiceover?.lines || [];
    if (!lines.length) return;
    const cleanups: Array<() => void> = [];
    let cancelled = false;

    for (const line of lines) {
      for (const variant of line.variants || []) {
        const key = makeVariantKey(line.id, variant.id);
        if (variantDurations[key] !== undefined) continue;
        const audio = new Audio();
        audio.preload = "metadata";
        const cleanup = () => {
          audio.onloadedmetadata = null;
          audio.onerror = null;
          audio.src = "";
        };
        cleanups.push(cleanup);
        audio.onloadedmetadata = () => {
          if (cancelled) {
            cleanup();
            return;
          }
          const seconds = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 0;
          setVariantDurations((prev) => (prev[key] !== undefined ? prev : { ...prev, [key]: seconds }));
          cleanup();
        };
        audio.onerror = () => {
          if (cancelled) {
            cleanup();
            return;
          }
          setVariantDurations((prev) => (prev[key] !== undefined ? prev : { ...prev, [key]: 0 }));
          cleanup();
        };
        audio.src = variant.audio_url;
      }
    }

    return () => {
      cancelled = true;
      cleanups.forEach((fn) => fn());
    };
  }, [makeVariantKey, variantDurations, voiceover?.lines]);

  async function handleGenerateAll() {
    if (!projectId) return;
    const lines = voiceover?.lines || [];
    if (!lines.length) {
      setInfo("Нет реплик для пакетной генерации.");
      return;
    }

    const defaultVoice = defaultVoiceProfile.trim();
    const prepared: Array<BatchQueueItem & { skip: boolean }> = lines.map((line) => {
      const lineVoice = (lineVoiceProfiles[line.id] || "").trim();
      const explicitVoiceProfile = lineVoice || defaultVoice || null;
      const fallback = resolveFallbackProfileForLine(line).trim();
      const sortPrompt = (
        explicitVoiceProfile ||
        (line.voice_profile || "").trim() ||
        fallback ||
        "~default"
      ).toLowerCase();
      const hasApproved = Boolean((line.approved_audio_url || "").trim());
      const skip = skipApproved && hasApproved && !replaceExisting;
      return {
        line,
        sortPrompt,
        explicitVoiceProfile,
        skip,
      };
    });

    const skipped = prepared.filter((item) => item.skip).length;
    const queue = prepared
      .filter((item) => !item.skip)
      .sort((a, b) => {
        const promptCmp = a.sortPrompt.localeCompare(b.sortPrompt);
        if (promptCmp !== 0) return promptCmp;
        return a.line.order - b.line.order;
      });

    try {
      setGeneratingAll(true);
      setError(null);
      setInfo(null);
      setBatchProgress({
        total: queue.length,
        completed: 0,
        remaining: queue.length,
        errors: 0,
        skipped,
        currentLabel: null,
      });

      if (!queue.length) {
        setInfo(`Нечего генерировать: все реплики уже подтверждены. Пропущено: ${skipped}.`);
        return;
      }

      let completed = 0;
      let errors = 0;
      const failedLines: string[] = [];

      for (const item of queue) {
        setBatchProgress((prev) =>
          prev
            ? {
                ...prev,
                currentLabel: `${lineKindLabel[item.line.kind]} · ${item.line.scene_title}`,
              }
            : prev,
        );
        try {
          const response = await generateProjectVoiceoverLine(projectId, {
            line_id: item.line.id,
            language,
            voice_profile: item.explicitVoiceProfile,
            replace_existing: replaceExisting,
          });
          applyLineUpdate(response.line, response.summary, response.settings, response.suggested_role_prompts);
          hydrateSettingsParts(response.settings, response.suggested_role_prompts);
        } catch (err: any) {
          errors += 1;
          const message = err?.message || "Ошибка генерации";
          failedLines.push(`${lineMeta(item.line)} — ${message}`);
        } finally {
          completed += 1;
          setBatchProgress((prev) =>
            prev
              ? {
                  ...prev,
                  completed,
                  remaining: Math.max(prev.total - completed, 0),
                  errors,
                }
              : prev,
          );
        }
      }

      await loadVoiceover();

      if (failedLines.length > 0) {
        const preview = failedLines.slice(0, 3).join("; ");
        const suffix = failedLines.length > 3 ? " ..." : "";
        setError(`Ошибки батча (${failedLines.length}): ${preview}${suffix}`);
      }

      const successCount = queue.length - errors;
      setInfo(`Батч завершён: готово ${successCount}/${queue.length}, ошибок ${errors}, пропущено ${skipped}.`);
    } catch (err: any) {
      setError(err?.message || "Не удалось запустить пакетную генерацию");
    } finally {
      setBatchProgress((prev) => (prev ? { ...prev, currentLabel: null } : prev));
      setGeneratingAll(false);
    }
  }

  async function handleGenerateLine(line: ProjectVoiceoverLine) {
    if (!projectId) return;
    try {
      setLineGeneratingId(line.id);
      setInfo(null);
      const response = await generateProjectVoiceoverLine(projectId, {
        line_id: line.id,
        language,
        voice_profile: lineVoiceProfiles[line.id]?.trim() || null,
        replace_existing: replaceExisting,
      });
      applyLineUpdate(response.line, response.summary, response.settings, response.suggested_role_prompts);
      hydrateSettingsParts(response.settings, response.suggested_role_prompts);
      setInfo(`Вариант добавлен: ${line.scene_title}`);
    } catch (err: any) {
      setError(err?.message || "Не удалось сгенерировать реплику");
    } finally {
      setLineGeneratingId(null);
    }
  }

  async function handleApprove(lineId: string, variantId: string) {
    if (!projectId) return;
    try {
      const key = `${lineId}:${variantId}`;
      setLineApprovingKey(key);
      setInfo(null);
      const response = await approveProjectVoiceoverLine(projectId, {
        line_id: lineId,
        variant_id: variantId,
      });
      applyLineUpdate(response.line, response.summary, response.settings, response.suggested_role_prompts);
      hydrateSettingsParts(response.settings, response.suggested_role_prompts);
      setInfo("Вариант подтверждён");
    } catch (err: any) {
      setError(err?.message || "Не удалось подтвердить вариант");
    } finally {
      setLineApprovingKey(null);
    }
  }

  async function handleSaveRolePrompts() {
    if (!projectId) return;
    try {
      setSavingSettings(true);
      setInfo(null);
      setError(null);

      const response = await updateProjectVoiceoverSettings(projectId, {
        language: language.trim() || null,
        role_prompts: {
          narrator: rolePrompts.narrator.trim() || null,
          inner_voice: rolePrompts.inner_voice.trim() || null,
          interlocutor: rolePrompts.interlocutor.trim() || null,
        },
        character_prompts: normalizeMap(characterPrompts),
        speaker_prompts: normalizeMap(speakerPrompts),
      });

      setVoiceover((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          settings: response.settings,
          suggested_role_prompts: response.suggested_role_prompts || prev.suggested_role_prompts,
          updated_at: response.updated_at || prev.updated_at,
        };
      });
      hydrateSettingsParts(response.settings, response.suggested_role_prompts);
      setInfo("Ролевые промты сохранены и будут использоваться в генерации проекта.");
    } catch (err: any) {
      setError(err?.message || "Не удалось сохранить ролевые промты");
    } finally {
      setSavingSettings(false);
    }
  }

  if (loading) {
    return <div className="p-8">Загрузка озвучки проекта...</div>;
  }

  if (error && !voiceover) {
    return (
      <div className="p-8">
        <p className="text-red-600">Не удалось открыть озвучку проекта.</p>
        <p className="text-sm text-gray-600">{error}</p>
        <button className="mt-4 secondary" onClick={() => navigate(-1)}>
          Назад
        </button>
      </div>
    );
  }

  return (
    <div className="page project-voiceover-shell">
      <div className="project-voiceover-header">
        <div>
          <h1>Озвучка проекта: {projectName}</h1>
          <p className="muted">Генерация, сравнение и подтверждение реплик с сохранением файлов в проекте.</p>
        </div>
        <div className="project-voiceover-actions">
          <button className="secondary" onClick={() => navigate(`/projects/${projectId}`)}>
            ← К проекту
          </button>
          <button className="secondary" onClick={() => navigate(`/player/${projectId}`)}>
            Проверить в плеере
          </button>
        </div>
      </div>

      <div className="project-voiceover-summary">
        <span className="pill">Реплик: {summary?.total_lines ?? 0}</span>
        <span className="pill">С вариантами: {summary?.generated_lines ?? 0}</span>
        <span className="pill">Подтверждено: {summary?.approved_lines ?? 0}</span>
        <span className="pill">Вариантов: {summary?.total_variants ?? 0}</span>
      </div>

      <div className="card project-voiceover-controls">
        <div className="field two-cols">
          <label className="field">
            <span>Группировка</span>
            <select
              className="input"
              value={groupMode}
              onChange={(event) => setGroupMode(event.target.value as GroupMode)}
            >
              <option value="timeline">По хронологии</option>
              <option value="character">По персонажам</option>
            </select>
          </label>
          <label className="field">
            <span>Язык TTS</span>
            <input
              className="input"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              placeholder="ru"
            />
          </label>
        </div>

        <div className="field two-cols">
          <label className="field">
            <span>Профиль голоса по умолчанию</span>
            <input
              className="input"
              value={defaultVoiceProfile}
              onChange={(event) => setDefaultVoiceProfile(event.target.value)}
              placeholder="Если пусто, берём профиль персонажа"
            />
          </label>
          <div className="stack" style={{ justifyContent: "flex-end" }}>
            <label className="wizard-checkbox">
              <input
                type="checkbox"
                checked={replaceExisting}
                onChange={(event) => setReplaceExisting(event.target.checked)}
              />
              <span>Перезаписывать варианты для строки</span>
            </label>
            <label className="wizard-checkbox">
              <input
                type="checkbox"
                checked={skipApproved}
                onChange={(event) => setSkipApproved(event.target.checked)}
              />
              <span>Пропускать уже подтверждённые</span>
            </label>
          </div>
        </div>

        <div className="field">
          <span>Ролевые промты проекта (используются, если у реплики не задан свой профиль)</span>
          <div className="field two-cols">
            <label className="field">
              <span>Нарратор</span>
              <textarea
                className="input"
                rows={2}
                value={rolePrompts.narrator}
                onChange={(event) =>
                  setRolePrompts((prev) => ({
                    ...prev,
                    narrator: event.target.value,
                  }))
                }
                placeholder="Голос нарратора"
              />
              {suggestedRolePrompts.narrator && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() =>
                    setRolePrompts((prev) => ({
                      ...prev,
                      narrator: suggestedRolePrompts.narrator,
                    }))
                  }
                >
                  Подставить рекомендуемый
                </button>
              )}
            </label>

            <label className="field">
              <span>Внутренний голос</span>
              <textarea
                className="input"
                rows={2}
                value={rolePrompts.inner_voice}
                onChange={(event) =>
                  setRolePrompts((prev) => ({
                    ...prev,
                    inner_voice: event.target.value,
                  }))
                }
                placeholder="Голос мыслей героя"
              />
              {suggestedRolePrompts.inner_voice && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() =>
                    setRolePrompts((prev) => ({
                      ...prev,
                      inner_voice: suggestedRolePrompts.inner_voice,
                    }))
                  }
                >
                  Подставить рекомендуемый
                </button>
              )}
            </label>
          </div>

          <label className="field">
            <span>Собеседники (общий fallback для диалогов)</span>
            <textarea
              className="input"
              rows={2}
              value={rolePrompts.interlocutor}
              onChange={(event) =>
                setRolePrompts((prev) => ({
                  ...prev,
                  interlocutor: event.target.value,
                }))
              }
              placeholder="Общий голос диалогов"
            />
            {suggestedRolePrompts.interlocutor && (
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  setRolePrompts((prev) => ({
                    ...prev,
                    interlocutor: suggestedRolePrompts.interlocutor,
                  }))
                }
              >
                Подставить рекомендуемый
              </button>
            )}
          </label>

          {characterPromptTargets.length > 0 && (
            <div className="field">
              <span>Точечные промты по персонажам и спикерам</span>
              <div className="project-voiceover-characters">
                {characterPromptTargets.map((target) => {
                  const value =
                    target.kind === "character"
                      ? characterPrompts[target.id] || ""
                      : speakerPrompts[target.id] || "";
                  return (
                    <label key={`${target.kind}:${target.id}`} className="field">
                      <span>{target.label}</span>
                      <input
                        className="input"
                        value={value}
                        onChange={(event) => {
                          const nextValue = event.target.value;
                          if (target.kind === "character") {
                            setCharacterPrompts((prev) => ({ ...prev, [target.id]: nextValue }));
                          } else {
                            setSpeakerPrompts((prev) => ({ ...prev, [target.id]: nextValue }));
                          }
                        }}
                        placeholder="Пусто = использовать общий fallback"
                      />
                    </label>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="actions" style={{ gap: 10 }}>
          <button className="secondary" onClick={handleSaveRolePrompts} disabled={savingSettings}>
            {savingSettings ? "Сохраняем роли..." : "Сохранить ролевые промты"}
          </button>
          <button className="primary" onClick={handleGenerateAll} disabled={generatingAll}>
            {generatingAll ? "Генерируем..." : "Сгенерировать всё"}
          </button>
          <button className="secondary" onClick={() => void loadVoiceover()}>
            Обновить список
          </button>
        </div>

        {batchProgress && (
          <div className="project-voiceover-batch-progress">
            <div className="project-voiceover-batch-counters">
              <span className="pill">Готово: {batchProgress.completed}</span>
              <span className="pill">Осталось: {batchProgress.remaining}</span>
              <span className="pill">Ошибки: {batchProgress.errors}</span>
              <span className="pill">Пропущено: {batchProgress.skipped}</span>
            </div>
            <div className="project-voiceover-batch-bar">
              <div
                className="project-voiceover-batch-bar-fill"
                style={{
                  width: `${batchProgress.total > 0 ? Math.round((batchProgress.completed / batchProgress.total) * 100) : 100}%`,
                }}
              />
            </div>
            <small className="muted">
              {batchProgress.total > 0
                ? `В батче ${batchProgress.total} реплик`
                : "В батче нет реплик"}
              {batchProgress.currentLabel ? ` · Сейчас: ${batchProgress.currentLabel}` : ""}
            </small>
          </div>
        )}

        {error && <div className="wizard-alert error">{error}</div>}
        {info && <div className="wizard-alert warn">{info}</div>}
      </div>

      {groupedLines.length === 0 ? (
        <div className="card">Для проекта не найдено озвучиваемых материалов.</div>
      ) : (
        groupedLines.map((group) => (
          <section key={group.id} className="card project-voiceover-group">
            <div className="card-header">
              <h2>{group.title}</h2>
              <span className="pill">{group.lines.length} реплик</span>
            </div>

            <div className="project-voiceover-lines">
              {group.lines.map((line) => {
                const variants = line.variants || [];
                const approveTarget = (variantId: string) => `${line.id}:${variantId}`;
                const fallbackProfile = resolveFallbackProfileForLine(line);
                const hasApprovedVariant = Boolean(line.approved_variant_id);
                const lineStatus = hasApprovedVariant ? "approved" : variants.length > 0 ? "pending" : "missing";
                const lineStatusIcon = hasApprovedVariant ? "✓" : variants.length > 0 ? "?" : "✕";
                const lineStatusTitle = hasApprovedVariant
                  ? "Есть подтверждённая озвучка"
                  : variants.length > 0
                    ? "Есть варианты, но ни один не подтверждён"
                    : "Нет записей";
                return (
                  <article key={line.id} className="project-voiceover-line">
                    <div className="project-voiceover-line-head">
                      <div className="project-voiceover-line-head-main">
                        <span
                          className={`project-voiceover-line-status ${lineStatus}`}
                          title={lineStatusTitle}
                          aria-label={lineStatusTitle}
                        >
                          {lineStatusIcon}
                        </span>
                        <div className="project-voiceover-line-head-text">
                          <strong>{lineKindLabel[line.kind]}</strong>
                          <div className="muted">{lineMeta(line)}</div>
                        </div>
                      </div>
                      <div className="project-voiceover-line-speaker">{normalizeSpeaker(line)}</div>
                    </div>

                    <p className="project-voiceover-line-text">{line.text}</p>

                    <div className="field" style={{ marginBottom: 10 }}>
                      <span>Профиль голоса для этой реплики</span>
                      <input
                        className="input"
                        value={lineVoiceProfiles[line.id] ?? ""}
                        onChange={(event) =>
                          setLineVoiceProfiles((prev) => ({
                            ...prev,
                            [line.id]: event.target.value,
                          }))
                        }
                        placeholder={fallbackProfile ? "Пусто = ролевой профиль" : "Можно оставить пустым"}
                      />
                      {!lineVoiceProfiles[line.id]?.trim() && fallbackProfile && (
                        <small className="muted">Будет использован fallback: {fallbackProfile}</small>
                      )}
                    </div>

                    <div className="actions" style={{ gap: 10, marginBottom: 10 }}>
                      <button
                        className="primary"
                        onClick={() => void handleGenerateLine(line)}
                        disabled={lineGeneratingId === line.id}
                      >
                        {lineGeneratingId === line.id ? "Генерируем..." : "Сгенерировать вариант"}
                      </button>
                      {line.approved_audio_url && (
                        <span className="pill strong">Подтверждено</span>
                      )}
                    </div>

                    {variants.length === 0 ? (
                      <div className="muted">Варианты озвучки пока не созданы.</div>
                    ) : (
                      <div className="project-voiceover-variants">
                        {variants.map((variant) => {
                          const isApproved = line.approved_variant_id === variant.id;
                          const approveKey = approveTarget(variant.id);
                          const variantKey = makeVariantKey(line.id, variant.id);
                          const progress = Math.max(0, Math.min(1, variantProgress[variantKey] || 0));
                          const progressAngle = `${Math.round(progress * 360)}deg`;
                          const isActive = variantPlaybackKey === variantKey;
                          const isPlaying = isActive && variantPlaybackStatus === "playing";
                          const isLoading = isActive && variantPlaybackStatus === "loading";
                          const shouldDim = Boolean(line.approved_variant_id) && !isApproved;
                          return (
                            <div
                              key={variant.id}
                              className={`project-voiceover-variant ${isApproved ? "approved" : ""} ${
                                shouldDim ? "dimmed" : ""
                              }`}
                            >
                              <div className="project-voiceover-variant-player">
                                <button
                                  type="button"
                                  className={`project-voiceover-variant-ring ${isPlaying ? "playing" : ""}`}
                                  style={{ ["--progress-angle" as any]: progressAngle }}
                                  onClick={() => void handleToggleVariantPlayback(line.id, variant.id, variant.audio_url)}
                                  title={isPlaying ? "Пауза" : "Воспроизвести"}
                                  aria-label={isPlaying ? "Пауза" : "Воспроизвести"}
                                >
                                  <span>{isLoading ? "…" : isPlaying ? "⏸" : "▶"}</span>
                                </button>
                                <span className="muted">{formatDuration(variantDurations[variantKey])}</span>
                              </div>
                              <div className="project-voiceover-variant-meta">
                                <button
                                  className={isApproved ? "secondary" : "primary"}
                                  disabled={lineApprovingKey === approveKey}
                                  onClick={() => void handleApprove(line.id, variant.id)}
                                >
                                  {isApproved
                                    ? "Подтверждено"
                                    : lineApprovingKey === approveKey
                                      ? "Подтверждаем..."
                                      : "Подтвердить"}
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
