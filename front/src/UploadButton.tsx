import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type {
  CharacterPreset,
  ImageVariant,
  PromptBundle,
  SceneNode,
  SceneNodeCharacter,
  SceneSequence,
  SceneSlide,
  SlideVariant,
} from "../shared/types";
import type { AIFieldSpec } from "../api/ai";
import { generateFormFill } from "../api/ai";
import { deleteSceneImage, generateSceneImage, previewScenePrompt } from "../api/generation";
import { generateCompositionPrompt } from "../api/sceneComposition";
import { listCharacterLibrary } from "../api/characterLib";
import { usePresets } from "../hooks/usePresets";
import { waitForGenerationJob } from "../utils/waitForGenerationJob";
import { useGenerationJobStore } from "../hooks/useGenerationJobStore";

type SlideProcessingParams = {
  workflow: string;
  prompt_mode: "composition" | "context";
  width?: number;
  height?: number;
  cfg_scale?: number;
  steps?: number;
  seed?: number;
  variants: number;
  pipeline_mode: "standard" | "controlnet";
  identity_mode?: "reference" | "ip_adapter";
  location_ref_mode?: "auto" | "none" | "selected";
  location_ref_url?: string;
  character_slot_ids?: string[];
};

type SlideJobState = {
  status: string;
  error?: string;
  stage?: string;
  progress?: number;
  params?: SlideProcessingParams;
};

const ACTIVE_JOB_STATUSES = new Set(["generating", "queued", "running", "processing"]);

type Props = {
  scene: SceneNode;
  projectId?: string;
  projectCharacters?: CharacterPreset[];
  creativeMode?: boolean;
  sideCollapsed?: boolean;
  orderedScenes?: SceneNode[];
  onNavigateScene?: (sceneId: string) => void;
  images: ImageVariant[];
  sceneCharacters: SceneNodeCharacter[];
  approvedImageUrl?: string | null;
  onSave: (sequence: SceneSequence | null) => Promise<void>;
  saving?: boolean;
  onPreviewImage?: (url: string) => void;
  generationDisabled?: boolean;
  generationDisabledReason?: string;
};

const AI_SEQUENCE_FIELDS: AIFieldSpec[] = [
    {
      key: "sequence",
      label: "Последовательность",
      type: "object",
      description:
        "JSON object with slides and optional choice metadata. Split long scenes into multiple slides (3-8). Each slide should include at least one of exposition (voiceover/off-screen narration), thought (inner voice), or dialogue. Keep them separated and chronological. Use animation from [fade, rise, float, none]. You may include cast_ids (character preset ids), framing (full|half|portrait), user_prompt (visual notes), composition_prompt (img2img composition instruction referencing image slots), pipeline {mode: standard|controlnet, identity_mode: ip_adapter|reference, pose_image_url?, location_ref_mode: auto|none|selected, location_ref_url?, character_slot_ids?}. Leave image_url empty unless a URL is provided. Example: {slides:[{title, image_url(optional), exposition, thought, dialogue:[{speaker,text}], animation, cast_ids, framing, user_prompt, composition_prompt, pipeline}], choice_key, choice_prompt}",
    },
  ];

const createId = () => `slide_${Date.now().toString(36)}_${Math.random().toString(16).slice(2, 8)}`;

const statusLabel = (status?: string) => {
  if (!status) return "";
  switch (status) {
    case "queued":
      return "В очереди";
    case "running":
      return "Рендеринг";
    case "generating":
      return "Подготовка";
    case "done":
      return "Готово";
    case "failed":
    case "error":
      return "Ошибка";
    default:
      return status;
  }
};

const isActiveJobStatus = (status?: string) => Boolean(status && ACTIVE_JOB_STATUSES.has(status));

const normalizeVariant = (value: unknown): SlideVariant | null => {
  if (typeof value === "string") {
    return { id: createId(), url: value, thumbnail_url: null };
  }
  const record = typeof value === "object" && value ? (value as Record<string, unknown>) : {};
  const id = typeof record.id === "string" ? record.id : "";
  const url = typeof record.url === "string" ? record.url : "";
  if (!id || !url) return null;
  return {
    id,
    url,
    thumbnail_url: typeof record.thumbnail_url === "string" ? record.thumbnail_url : null,
  };
};

  const normalizeSlide = (value: unknown): SceneSlide => {
    const slide = typeof value === "object" && value ? (value as Record<string, unknown>) : {};
    const dialogueRaw = Array.isArray(slide.dialogue) ? slide.dialogue : [];
    const variantsRaw = Array.isArray(slide.variants) ? slide.variants : [];
    const variants = variantsRaw.map(normalizeVariant).filter((item): item is SlideVariant => Boolean(item));
    const castRaw = Array.isArray(slide.cast_ids) ? slide.cast_ids : [];
    const cast_ids = castRaw.filter((id) => typeof id === "string") as string[];
    const composition_prompt =
      typeof slide.composition_prompt === "string" ? slide.composition_prompt : "";
    const framing =
      slide.framing === "full" || slide.framing === "half" || slide.framing === "portrait" ? slide.framing : undefined;
  const pipelineRaw = typeof slide.pipeline === "object" && slide.pipeline ? (slide.pipeline as Record<string, unknown>) : {};
  const pipelineMode =
    pipelineRaw.mode === "controlnet" || pipelineRaw.mode === "standard" ? pipelineRaw.mode : undefined;
  const pose_image_url = typeof pipelineRaw.pose_image_url === "string" ? pipelineRaw.pose_image_url : "";
  const identity_mode =
    pipelineRaw.identity_mode === "ip_adapter" || pipelineRaw.identity_mode === "reference"
      ? pipelineRaw.identity_mode
      : undefined;
  const location_ref_mode =
    pipelineRaw.location_ref_mode === "auto" ||
    pipelineRaw.location_ref_mode === "none" ||
    pipelineRaw.location_ref_mode === "selected"
      ? pipelineRaw.location_ref_mode
      : undefined;
  const location_ref_url = typeof pipelineRaw.location_ref_url === "string" ? pipelineRaw.location_ref_url : "";
  const character_slot_ids = Array.isArray(pipelineRaw.character_slot_ids)
    ? pipelineRaw.character_slot_ids.filter((value) => typeof value === "string").map((value) => String(value))
    : [];
  return {
    id: typeof slide.id === "string" ? slide.id : createId(),
    title: typeof slide.title === "string" ? slide.title : "",
    image_url: typeof slide.image_url === "string" ? slide.image_url : "",
      image_variant_id: typeof slide.image_variant_id === "string" ? slide.image_variant_id : "",
      variants,
      user_prompt: typeof slide.user_prompt === "string" ? slide.user_prompt : "",
      composition_prompt,
      cast_ids,
      framing,
    pipeline:
      pipelineMode ||
      pose_image_url ||
      identity_mode ||
      location_ref_mode ||
      location_ref_url ||
      character_slot_ids.length
        ? {
            mode: pipelineMode,
            pose_image_url,
            identity_mode,
            location_ref_mode,
            location_ref_url,
            character_slot_ids,
          }
        : undefined,
    exposition: typeof slide.exposition === "string" ? slide.exposition : "",
    thought: typeof slide.thought === "string" ? slide.thought : "",
    dialogue: dialogueRaw
      .map((line) => {
        const record = typeof line === "object" && line ? (line as Record<string, unknown>) : {};
        return {
          id: typeof record.id === "string" ? record.id : createId(),
          speaker: typeof record.speaker === "string" ? record.speaker : "",
          text: typeof record.text === "string" ? record.text : "",
        };
      })
      .filter((line) => line.text.trim()),
    animation: typeof slide.animation === "string" ? slide.animation : "fade",
  };
};

const normalizeSequence = (value: unknown): SceneSequence => {
  const seq = typeof value === "object" && value ? (value as Record<string, unknown>) : {};
  const slides = Array.isArray(seq.slides) ? seq.slides.map(normalizeSlide) : [];
  return {
    slides,
    choice_key: typeof seq.choice_key === "string" ? seq.choice_key : "",
    choice_prompt: typeof seq.choice_prompt === "string" ? seq.choice_prompt : "",
  };
};

const buildDialogueText = (slide: SceneSlide) => {
  const lines = slide.dialogue || [];
  if (lines.length === 0) return "";
  return lines
    .map((line) => {
      const speaker = line.speaker?.trim();
      const text = line.text?.trim();
      if (!text) return "";
      return speaker ? `${speaker}: ${text}` : text;
    })
    .filter(Boolean)
    .join("; ");
};

const buildSlideNarrative = (slide: SceneSlide) => {
  const parts: string[] = [];
  if (slide.title?.trim()) parts.push(`beat: ${slide.title.trim()}`);
  if (slide.exposition?.trim()) parts.push(`exposition: ${slide.exposition.trim()}`);
  if (slide.thought?.trim()) parts.push(`thought: ${slide.thought.trim()}`);
  const dialogue = buildDialogueText(slide);
  if (dialogue) parts.push(`dialogue: ${dialogue}`);
  return parts.join(", ");
};

const buildFramingHint = (framing?: SceneSlide["framing"]) => {
  if (framing === "full") return "full body, full figure";
  if (framing === "half") return "half body, waist-up";
  if (framing === "portrait") return "portrait, close-up";
  return "";
};

const buildFramingNegative = (framing?: SceneSlide["framing"]) => {
  if (framing === "full") return "portrait, close-up, cropped face";
  if (framing === "half") return "full body, full figure";
  if (framing === "portrait") return "full body, wide shot";
  return "";
};

const buildAutoPrompt = (bundle: PromptBundle | null, slide: SceneSlide) => {
  const narrative = buildSlideNarrative(slide);
  const framing = buildFramingHint(slide.framing);
  if (!bundle?.prompt) return [narrative, framing].filter(Boolean).join(", ");
  return [bundle.prompt, narrative, framing].filter(Boolean).join(", ");
};

const buildFinalPrompt = (bundle: PromptBundle | null, slide: SceneSlide) => {
  const auto = buildAutoPrompt(bundle, slide);
  const userPrompt = slide.user_prompt?.trim();
  return [auto, userPrompt].filter(Boolean).join(", ");
};

const toProgressPercent = (value: unknown): number | undefined => {
  if (typeof value !== "number" || Number.isNaN(value)) return undefined;
  if (value <= 0) return 0;
  if (value <= 1) return Math.round(value * 100);
  if (value >= 100) return 100;
  return Math.round(value);
};

export default function SceneSequenceEditor({
  scene,
  projectId,
  projectCharacters = [],
  creativeMode = false,
  sideCollapsed = false,
  orderedScenes = [],
  onNavigateScene,
  images,
  sceneCharacters,
  approvedImageUrl,
  onSave,
  saving = false,
  onPreviewImage,
  generationDisabled = false,
  generationDisabledReason,
}: Props) {
  const { data: presets } = usePresets(projectId);
  const [sequence, setSequence] = useState<SceneSequence>(() => normalizeSequence(scene.context?.sequence));
  const [activeIndex, setActiveIndex] = useState(0);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiDetail, setAiDetail] = useState<"narrow" | "standard" | "detailed">("standard");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [promptBundle, setPromptBundle] = useState<PromptBundle | null>(null);
  const [promptLoading, setPromptLoading] = useState(false);
  const [promptError, setPromptError] = useState<string | null>(null);
  const [compositionLoading, setCompositionLoading] = useState(false);
  const [compositionError, setCompositionError] = useState<string | null>(null);
  const [slideJobs, setSlideJobs] = useState<Record<string, SlideJobState>>({});
  const [slideDrawerOpen, setSlideDrawerOpen] = useState(false);
  const [variantCount, setVariantCount] = useState(1);
  const [showLibrary, setShowLibrary] = useState(false);
  const [openCharacterSlotPicker, setOpenCharacterSlotPicker] = useState<number | null>(null);
  const upsertJob = useGenerationJobStore((s) => s.upsert);
  const isMounted = useRef(true);
  const activeSlideIdRef = useRef<string | null>(null);
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingPersistRef = useRef<SceneSequence | null>(null);
  const linkIdToPresetId = useMemo(
    () => new Map(sceneCharacters.map((link) => [link.id, link.character_preset_id])),
    [sceneCharacters],
  );
  const defaultCastIds = useMemo(
    () => sceneCharacters.filter((link) => link.in_frame !== false).map((link) => link.character_preset_id),
    [sceneCharacters],
  );
  const activeCastIds = sequence.slides[activeIndex]?.cast_ids ?? defaultCastIds;
  const castKey = Array.isArray(activeCastIds) ? activeCastIds.join("|") : "default";
  const sceneCastIdSet = useMemo(
    () => new Set(sceneCharacters.map((link) => link.character_preset_id)),
    [sceneCharacters],
  );
  const hasLibrarySelection = useMemo(
    () => activeCastIds.some((id) => !sceneCastIdSet.has(id)),
    [activeCastIds, sceneCastIdSet],
  );
  const showLibraryList = showLibrary || hasLibrarySelection;

  const {
    data: libraryList,
    isLoading: libraryLoading,
    error: libraryError,
  } = useQuery({
    queryKey: ["characterLib"],
    queryFn: () => listCharacterLibrary({ page: 1, page_size: 50, include_public: true }),
    enabled: showLibraryList,
    staleTime: 60 * 1000,
  });

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
      if (persistTimerRef.current) {
        clearTimeout(persistTimerRef.current);
        persistTimerRef.current = null;
        const pending = pendingPersistRef.current;
        pendingPersistRef.current = null;
        if (pending) {
          const cleaned = {
            ...pending,
            slides: pending.slides.map((slide) => ({
              ...slide,
              exposition: slide.exposition?.trim() || "",
              thought: slide.thought?.trim() || "",
              title: slide.title?.trim() || "",
              dialogue: (slide.dialogue || []).filter((line) => line.text.trim()),
            })),
          };
          const isEmpty =
            cleaned.slides.length === 0 &&
            !(cleaned.choice_key || "").trim() &&
            !(cleaned.choice_prompt || "").trim();
          void onSave(isEmpty ? null : cleaned).catch((error) => {
            console.error("Failed to flush sequence on unmount", error);
          });
        }
      }
    };
  }, []);

  useEffect(() => {
    activeSlideIdRef.current = sequence.slides[activeIndex]?.id || null;
  }, [sequence.slides, activeIndex]);

  useEffect(() => {
    setOpenCharacterSlotPicker(null);
  }, [activeIndex, scene.id]);

  useEffect(() => {
    const nextSequence = normalizeSequence(scene.context?.sequence);
    const previousSlideId = activeSlideIdRef.current;
    setSequence(nextSequence);
    setActiveIndex(() => {
      if (!previousSlideId) return 0;
      const nextIndex = nextSequence.slides.findIndex((slide) => slide.id === previousSlideId);
      return nextIndex >= 0 ? nextIndex : 0;
    });
    setAiError(null);
    setSlideJobs({});
  }, [scene.id, scene.context?.sequence]);

  useEffect(() => {
    if (linkIdToPresetId.size === 0) return;
    setSequence((prev) => {
      let changed = false;
      const nextSlides = prev.slides.map((slide) => {
        if (!slide.cast_ids || slide.cast_ids.length === 0) return slide;
        const mapped = slide.cast_ids
          .map((id) => linkIdToPresetId.get(id) || id)
          .filter(Boolean);
        const unique = Array.from(new Set(mapped));
        const same =
          unique.length === slide.cast_ids.length &&
          unique.every((id, idx) => id === slide.cast_ids?.[idx]);
        if (!same) {
          changed = true;
          return { ...slide, cast_ids: unique };
        }
        return slide;
      });
      return changed ? { ...prev, slides: nextSlides } : prev;
    });
  }, [linkIdToPresetId]);

  useEffect(() => {
    let cancelled = false;
    const loadPrompt = async () => {
      setPromptLoading(true);
      setPromptError(null);
      setPromptBundle(null);
      console.log("[SceneSequenceEditor] Loading prompt for scene:", scene.id, "cast:", activeCastIds);
      try {
        const bundle = await previewScenePrompt(scene.id, { characterIds: activeCastIds });
        if (!cancelled && isMounted.current) {
          setPromptBundle(bundle);
          console.log("[SceneSequenceEditor] Prompt loaded:", { hasPrompt: !!bundle.prompt, promptLength: bundle.prompt?.length });
        }
      } catch (error: any) {
        console.error("[SceneSequenceEditor] Failed to load prompt:", error);
        if (!cancelled && isMounted.current) {
          setPromptError(error?.message || "Не удалось загрузить промпт.");
          setPromptBundle(null);
        }
      } finally {
        if (!cancelled) {
          setPromptLoading(false);
        }
      }
    };
    loadPrompt();
    return () => {
      cancelled = true;
    };
  }, [scene.id, scene.content, scene.synopsis, scene.location_id, castKey, sceneCharacters]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName;
      if (
        target &&
        (target.isContentEditable || tagName === "INPUT" || tagName === "TEXTAREA" || tagName === "SELECT")
      ) {
        return;
      }
      if (!event.altKey) return;
      if (event.key === "ArrowLeft" && sequence.slides.length > 0) {
        event.preventDefault();
        setActiveIndex((prev) => Math.max(0, prev - 1));
      } else if (event.key === "ArrowRight" && sequence.slides.length > 0) {
        event.preventDefault();
        setActiveIndex((prev) => Math.min(sequence.slides.length - 1, prev + 1));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [sequence.slides.length]);

  useEffect(() => {
    if (!slideDrawerOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSlideDrawerOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [slideDrawerOpen]);

  const imageOptions = useMemo(() => {
    const items: { key: string; label: string; value: string }[] = [];
    if (approvedImageUrl) {
      items.push({ key: "approved", label: "Утверждённое изображение", value: approvedImageUrl });
    }
    images.forEach((img) => {
      const label = img.is_approved
        ? "Утверждённый вариант"
        : `Вариант ${img.created_at?.slice(0, 10) || img.id.slice(0, 6)}`;
      items.push({ key: img.id, label, value: img.url });
    });
    return items;
  }, [approvedImageUrl, images]);

  const slides = sequence.slides;
  const activeSlide = slides[activeIndex] || null;
  const activeVariants = activeSlide?.variants || [];
  const autoPrompt = activeSlide ? buildAutoPrompt(promptBundle, activeSlide) : "";
  const finalPrompt = activeSlide ? buildFinalPrompt(promptBundle, activeSlide) : "";
  const slideJob = activeSlide ? slideJobs[activeSlide.id] : undefined;
  const slideJobProgress = toProgressPercent(slideJob?.progress);
  const isSlideJobActive = isActiveJobStatus(slideJob?.status);
  const castOptions = useMemo(() => {
    const presetMap = new Map((presets?.characters || []).map((preset) => [preset.id, preset.name]));
    const sceneOptions = sceneCharacters.map((link) => ({
      id: link.character_preset_id,
      name: presetMap.get(link.character_preset_id) || link.character_preset_id,
      in_frame: link.in_frame !== false,
      source: "scene" as const,
    }));
    const libraryOptions: Array<{ id: string; name: string; in_frame: boolean; source: "library" }> = [];
    if (showLibraryList && libraryList?.items) {
      libraryOptions.push(
        ...libraryList.items.map((char) => ({
          id: char.id,
          name: char.name,
          in_frame: true,
          source: "library" as const,
        })),
      );
    }
    if (showLibraryList) {
      const selectedLibraryIds = activeCastIds.filter((id) => !sceneCastIdSet.has(id));
      for (const id of selectedLibraryIds) {
        if (!libraryOptions.find((opt) => opt.id === id)) {
          libraryOptions.push({ id, name: id, in_frame: true, source: "library" as const });
        }
      }
    }
    const seen = new Set<string>();
    const merged = [...sceneOptions, ...libraryOptions].filter((opt) => {
      if (seen.has(opt.id)) return false;
      seen.add(opt.id);
      return true;
    });
    return merged;
  }, [presets, sceneCharacters, showLibraryList, libraryList, activeCastIds, sceneCastIdSet]);
  const hasCustomCast = Array.isArray(activeSlide?.cast_ids);
  const selectedCastIds = hasCustomCast ? (activeSlide?.cast_ids || []) : defaultCastIds;
  const isCreativeMode = creativeMode;
  const pipelineMode = isCreativeMode ? "standard" : activeSlide?.pipeline?.mode || "standard";
  const identityMode = activeSlide?.pipeline?.identity_mode || "ip_adapter";
  const locationRefMode = isCreativeMode ? "none" : activeSlide?.pipeline?.location_ref_mode || "auto";
  const locationRefUrl = isCreativeMode ? "" : activeSlide?.pipeline?.location_ref_url || "";
  const characterSlotIds = activeSlide?.pipeline?.character_slot_ids || [];
  const resolvedCharacterSlotIds = [
    characterSlotIds[0] || selectedCastIds[0] || "",
    characterSlotIds[1] || selectedCastIds[1] || "",
  ];

  const characterInfoById = useMemo(() => {
    const map = new Map<string, { name: string; previewUrl?: string | null }>();
    for (const character of projectCharacters) {
      const previewFromRefs =
        (character.reference_images || []).find((ref) => ref?.kind === "portrait" && ref?.url)?.url ||
        (character.reference_images || []).find((ref) => ref?.url)?.url ||
        null;
      map.set(character.id, {
        name: character.name || character.id,
        previewUrl: character.preview_image_url || previewFromRefs || character.preview_thumbnail_url || null,
      });
    }
    for (const preset of presets?.characters || []) {
      if (!map.has(preset.id)) {
        map.set(preset.id, { name: preset.name || preset.id });
      }
    }
    for (const option of castOptions) {
      if (!map.has(option.id)) {
        map.set(option.id, { name: option.name || option.id });
      }
    }
    return map;
  }, [projectCharacters, presets?.characters, castOptions]);

  const locationReferenceOptions = useMemo(() => {
    const options: Array<{ value: string; label: string }> = [];
    const location = scene.location;
    if (!location) return options;
    const pushOption = (value: string, label: string) => {
      if (!value) return;
      if (options.some((item) => item.value === value)) return;
      options.push({ value, label });
    };
    if (location.preview_image_url) {
      pushOption(location.preview_image_url, "Превью локации");
    }
    (location.reference_images || []).forEach((ref, index) => {
      const value = ref?.url || ref?.thumb_url || "";
      if (!value) return;
      const kind = typeof ref.kind === "string" && ref.kind ? ref.kind : "reference";
      const label = ref.label ? `${ref.label} (${kind})` : `Референс ${index + 1} (${kind})`;
      pushOption(value, label);
    });
    return options;
  }, [scene.location]);

  const getCharacterDisplayName = (characterId: string) =>
    characterInfoById.get(characterId)?.name || characterId || "—";

  const getCharacterPreviewUrl = (characterId: string) => characterInfoById.get(characterId)?.previewUrl || "";
  const getEffectiveLocationPreviewUrl = () => {
    if (isCreativeMode) return "";
    if (locationRefMode === "none") return "";
    if (locationRefUrl) return locationRefUrl;
    return locationReferenceOptions[0]?.value || "";
  };

  const slotCharacterOptions = useMemo(() => {
    const orderedIds = [...selectedCastIds, ...castOptions.map((opt) => opt.id)];
    const seen = new Set<string>();
    const uniqueIds: string[] = [];
    for (const id of orderedIds) {
      if (!id || seen.has(id)) continue;
      seen.add(id);
      uniqueIds.push(id);
    }
    return uniqueIds.map((id) => ({ id, label: characterInfoById.get(id)?.name || id }));
  }, [selectedCastIds, castOptions, characterInfoById]);

  const selectedSceneIndex = useMemo(
    () => orderedScenes.findIndex((item) => item.id === scene.id),
    [orderedScenes, scene.id],
  );

  const updatePipelineAndPersist = (patch: SceneSlide["pipeline"]) => {
    if (!activeSlide) return;
    setSequence((prev) => {
      const next = {
        ...prev,
        slides: prev.slides.map((slide, idx) =>
          idx === activeIndex ? { ...slide, pipeline: { ...(slide.pipeline || {}), ...(patch || {}) } } : slide,
        ),
      };
      schedulePersist(next);
      return next;
    });
  };

  const updateSlide = (index: number, patch: Partial<SceneSlide>) => {
    setSequence((prev) => {
      const next = {
        ...prev,
        slides: prev.slides.map((slide, idx) => (idx === index ? { ...slide, ...patch } : slide)),
      };
      schedulePersist(next);
      return next;
    });
  };

  const updateSlideById = (slideId: string, patch: Partial<SceneSlide>) => {
    setSequence((prev) => {
      const next = {
        ...prev,
        slides: prev.slides.map((slide) => (slide.id === slideId ? { ...slide, ...patch } : slide)),
      };
      schedulePersist(next);
      return next;
    });
  };

  const persistSequenceQuietly = (next: SceneSequence) => {
    if (saving) return;
    pendingPersistRef.current = null;
    const cleaned = {
      ...next,
      slides: next.slides.map((slide) => ({
        ...slide,
        exposition: slide.exposition?.trim() || "",
        thought: slide.thought?.trim() || "",
        title: slide.title?.trim() || "",
        dialogue: (slide.dialogue || []).filter((line) => line.text.trim()),
      })),
    };
    const isEmpty =
      cleaned.slides.length === 0 &&
      !(cleaned.choice_key || "").trim() &&
      !(cleaned.choice_prompt || "").trim();
    void onSave(isEmpty ? null : cleaned).catch((error) => {
      console.error("Failed to auto-save sequence", error);
    });
  };

  const schedulePersist = (next: SceneSequence) => {
    if (saving) return;
    pendingPersistRef.current = next;
    if (persistTimerRef.current) {
      clearTimeout(persistTimerRef.current);
    }
    persistTimerRef.current = setTimeout(() => {
      persistTimerRef.current = null;
      persistSequenceQuietly(next);
    }, 350);
  };

  const updatePipeline = (patch: SceneSlide["pipeline"]) => {
    if (!activeSlide) return;
    const next = { ...(activeSlide.pipeline || {}), ...(patch || {}) };
    updateSlide(activeIndex, { pipeline: next });
  };

  const updateCharacterSlot = (slotIndex: number, characterId: string) => {
    const next = [...resolvedCharacterSlotIds];
    next[slotIndex] = characterId;
    updatePipelineAndPersist({
      character_slot_ids: next.filter(Boolean),
    });
    setOpenCharacterSlotPicker(null);
  };

  const getSlotCastIds = () => {
    const fallback = selectedCastIds.filter(Boolean);
    const slotIds = resolvedCharacterSlotIds.filter(Boolean);
    if (slotIds.length > 0) return Array.from(new Set(slotIds)).slice(0, 2);
    return fallback.slice(0, 2);
  };

  const toggleCast = (linkId: string) => {
    if (!activeSlide) return;
    const next = new Set(selectedCastIds);
    if (next.has(linkId)) {
      next.delete(linkId);
    } else {
      next.add(linkId);
    }
    updateSlide(activeIndex, { cast_ids: Array.from(next) });
  };

  const resetCastToInFrame = () => {
    if (!activeSlide) return;
    updateSlide(activeIndex, { cast_ids: undefined });
  };

  const clearCast = () => {
    if (!activeSlide) return;
    updateSlide(activeIndex, { cast_ids: [] });
  };

  const updateDialogue = (lineIndex: number, patch: { speaker?: string; text?: string }) => {
    if (!activeSlide) return;
    const next = [...(activeSlide.dialogue || [])];
    const line = next[lineIndex] || { id: createId(), speaker: "", text: "" };
    next[lineIndex] = { ...line, ...patch };
    updateSlide(activeIndex, { dialogue: next });
  };

  const addDialogue = () => {
    if (!activeSlide) return;
    const next = [...(activeSlide.dialogue || [])];
    next.push({ id: createId(), speaker: "", text: "" });
    updateSlide(activeIndex, { dialogue: next });
  };

  const removeDialogue = (lineIndex: number) => {
    if (!activeSlide) return;
    const next = (activeSlide.dialogue || []).filter((_, idx) => idx !== lineIndex);
    updateSlide(activeIndex, { dialogue: next });
  };

  const addSlide = () => {
    const next = normalizeSlide({ id: createId() });
    setSequence((prev) => {
      const nextSequence = { ...prev, slides: [...prev.slides, next] };
      schedulePersist(nextSequence);
      return nextSequence;
    });
    setActiveIndex(slides.length);
  };

  const duplicateSlide = () => {
    if (!activeSlide) return;
    const clone = { ...activeSlide, id: createId() };
    setSequence((prev) => {
      const next = {
        ...prev,
        slides: [...prev.slides.slice(0, activeIndex + 1), clone, ...prev.slides.slice(activeIndex + 1)],
      };
      schedulePersist(next);
      return next;
    });
    setActiveIndex(activeIndex + 1);
  };

  const removeSlide = () => {
    if (!activeSlide) return;
    setSequence((prev) => {
      const next = {
        ...prev,
        slides: prev.slides.filter((_, idx) => idx !== activeIndex),
      };
      schedulePersist(next);
      return next;
    });
    setActiveIndex((prev) => Math.max(0, prev - 1));
  };

  const moveSlide = (direction: number) => {
    const nextIndex = activeIndex + direction;
    if (!activeSlide || nextIndex < 0 || nextIndex >= slides.length) return;
    setSequence((prev) => {
      const nextSlides = [...prev.slides];
      const [item] = nextSlides.splice(activeIndex, 1);
      nextSlides.splice(nextIndex, 0, item);
      const next = { ...prev, slides: nextSlides };
      schedulePersist(next);
      return next;
    });
    setActiveIndex(nextIndex);
  };

  const coerceNumber = (value: unknown) => {
    if (typeof value === "number" && !Number.isNaN(value)) return value;
    if (typeof value === "string" && value.trim()) {
      const parsed = Number(value);
      if (!Number.isNaN(parsed)) return parsed;
    }
    return undefined;
  };

  const pollJob = async (jobId: string, onUpdate?: (job: { status?: string; stage?: string | null; progress?: number | null; config?: Record<string, unknown> | null }) => void) => {
    return await waitForGenerationJob(jobId, {
      intervalMs: 2000,
      maxAttempts: 120,
      onUpdate: (job) => onUpdate?.(job),
    });
  };

  const applyCompositionResult = (
    targetSlideId: string,
    result: {
      composition_prompt?: string;
      location_ref_url?: string;
      character_ref_urls?: string[];
    },
    slotCastIds: string[],
  ) => {
    const generatedPrompt = result.composition_prompt?.trim() || "";
    setSequence((prev) => {
      const next = {
        ...prev,
        slides: prev.slides.map((slide) => {
          if (slide.id !== targetSlideId) return slide;
          const pipeline = { ...(slide.pipeline || {}) };
          if (result.location_ref_url && pipeline.location_ref_mode !== "none" && !pipeline.location_ref_url) {
            pipeline.location_ref_mode = "selected";
            pipeline.location_ref_url = result.location_ref_url;
          }
          if (slotCastIds.length > 0 && (!pipeline.character_slot_ids || pipeline.character_slot_ids.length === 0)) {
            pipeline.character_slot_ids = slotCastIds.slice(0, 2);
          }
          return {
            ...slide,
            composition_prompt: generatedPrompt || slide.composition_prompt || "",
            pipeline,
          };
        }),
      };
      persistSequenceQuietly(next);
      return next;
    });
    return generatedPrompt;
  };

  const handleGenerateVariants = async () => {
    if (generationDisabled) {
      setAiError(generationDisabledReason || "Генерация заблокирована: нет всех референсов.");
      return;
    }
    if (!activeSlide) {
      console.error("[SceneSequenceEditor] No active slide");
      return;
    }
    const targetSlideId = activeSlide.id;
    if (!promptBundle?.prompt) {
      console.error("[SceneSequenceEditor] Prompt bundle not ready:", { promptBundle, promptLoading, promptError });
      setSlideJobs((prev) => ({
        ...prev,
        [targetSlideId]: { status: "error", error: "Контекстный промпт ещё не готов." },
      }));
      return;
    }
    const slotCastIds = getSlotCastIds();
    let compositionPrompt = activeSlide.composition_prompt?.trim() || "";
    let useCompositionPrompt = pipelineMode !== "controlnet" && Boolean(compositionPrompt);
    if (!useCompositionPrompt && pipelineMode !== "controlnet") {
      setCompositionLoading(true);
      setCompositionError(null);
      try {
        const visualParts: string[] = [];
        const userVisual = activeSlide.user_prompt?.trim();
        if (userVisual) {
          visualParts.push(userVisual);
        } else {
          if (activeSlide.title) visualParts.push(activeSlide.title);
          if (activeSlide.exposition) visualParts.push(activeSlide.exposition);
          if (activeSlide.thought) visualParts.push(activeSlide.thought);
          const dialogueText = buildDialogueText(activeSlide);
          if (dialogueText) visualParts.push(dialogueText);
        }
        const slideVisual = visualParts.join(". ") || "Scene composition";
        const result = await generateCompositionPrompt(scene.id, {
          slide_visual: slideVisual,
          cast_ids: slotCastIds,
          slide_id: targetSlideId,
          location_id: scene.location_id || undefined,
          framing: activeSlide.framing || "full",
          has_location_reference: !isCreativeMode &&
            (activeSlide.pipeline?.location_ref_mode || "auto") !== "none" &&
            Boolean(getEffectiveLocationPreviewUrl()),
        });
        compositionPrompt = applyCompositionResult(targetSlideId, result, slotCastIds);
      } catch (error: any) {
        console.error("[SceneSequenceEditor] Auto composition generation failed:", error);
        setCompositionError(error?.message || "Не удалось сгенерировать композицию.");
      } finally {
        if (isMounted.current) {
          setCompositionLoading(false);
        }
      }
      useCompositionPrompt = Boolean(compositionPrompt);
    }
    const prompt = (useCompositionPrompt ? compositionPrompt : finalPrompt).trim();
    if (!prompt) {
      console.error("[SceneSequenceEditor] Final prompt is empty:", { finalPrompt, autoPrompt });
      setSlideJobs((prev) => ({
        ...prev,
        [targetSlideId]: { status: "error", error: "Промпт слайда пуст." },
      }));
      return;
    }
    const config = promptBundle?.config || {};
    const safeCount = Math.min(8, Math.max(1, Math.round(variantCount || 1)));
    const framingNegative = buildFramingNegative(activeSlide.framing);
    const negativePrompt = useCompositionPrompt
      ? ""
      : [promptBundle?.negative_prompt, framingNegative].filter(Boolean).join(", ") || undefined;
    const requestWidth = coerceNumber(config.width);
    const requestHeight = coerceNumber(config.height);
    const requestCfg = coerceNumber(config.cfg_scale);
    const requestSteps = coerceNumber(config.steps);
    const requestSeed = coerceNumber(config.seed);
    const pipeline = {
      mode: pipelineMode,
      cast_ids: selectedCastIds,
      character_slot_ids: slotCastIds,
      framing: activeSlide.framing || "full",
      pose_image_url: pipelineMode === "controlnet" ? activeSlide.pipeline?.pose_image_url || "" : undefined,
      identity_mode: pipelineMode === "controlnet" ? identityMode : undefined,
      location_ref_mode: isCreativeMode ? "none" : activeSlide.pipeline?.location_ref_mode || "auto",
      location_ref_url:
        isCreativeMode
          ? ""
          : activeSlide.pipeline?.location_ref_mode === "selected"
            ? activeSlide.pipeline?.location_ref_url || ""
            : "",
    };
    const resolvedParams: SlideProcessingParams = {
      workflow: useCompositionPrompt ? "scene_img2img_qwen" : "scene_standard_sd",
      prompt_mode: useCompositionPrompt ? "composition" : "context",
      width: requestWidth,
      height: requestHeight,
      cfg_scale: requestCfg,
      steps: requestSteps,
      seed: requestSeed,
      variants: safeCount,
      pipeline_mode: pipelineMode,
      identity_mode: pipelineMode === "controlnet" ? identityMode : undefined,
      location_ref_mode: pipeline.location_ref_mode,
      location_ref_url: pipeline.location_ref_url || undefined,
      character_slot_ids: slotCastIds.slice(0, 2),
    };

    console.log("[SceneSequenceEditor] Starting generation:", {
      sceneId: scene.id,
      slideId: targetSlideId,
      prompt: prompt.slice(0, 100) + "...",
      variantCount: safeCount,
      pipeline,
      resolvedParams,
    });

    setSlideJobs((prev) => ({
      ...prev,
      [targetSlideId]: {
        status: "generating",
        stage: "Подготовка запроса",
        progress: 0,
        params: resolvedParams,
      },
    }));
    try {
      const job = await generateSceneImage(scene.id, {
        use_prompt_engine: false,
        prompt,
        negative_prompt: negativePrompt,
        num_variants: safeCount,
        width: requestWidth as number | undefined,
        height: requestHeight as number | undefined,
        cfg_scale: requestCfg as number | undefined,
        steps: requestSteps as number | undefined,
        seed: requestSeed as number | undefined,
        pipeline,
        slide_id: targetSlideId,
      });
      console.log("[SceneSequenceEditor] Job created:", { jobId: job.id, status: job.status });
      if (isMounted.current) {
        setSlideJobs((prev) => ({
          ...prev,
          [targetSlideId]: {
            status: job.status || "queued",
            stage: job.stage || "Запрос отправлен",
            progress: toProgressPercent(job.progress),
            params: prev[targetSlideId]?.params || resolvedParams,
          },
        }));
      }
      upsertJob(job);
      
      const completed = await pollJob(job.id, (jobState) => {
        if (isMounted.current) {
          setSlideJobs((prev) => ({
            ...prev,
            [targetSlideId]: {
              status: jobState.status || prev[targetSlideId]?.status || "running",
              stage: jobState.stage || prev[targetSlideId]?.stage,
              progress: toProgressPercent(jobState.progress) ?? prev[targetSlideId]?.progress,
              params: {
                ...(prev[targetSlideId]?.params || resolvedParams),
                ...(jobState.config || {}),
              },
            },
          }));
        }
      });
      console.log("[SceneSequenceEditor] Job completed:", { jobId: completed.id, status: completed.status, variantCount: completed.variants?.length });
      
      if (completed.status !== "done") {
        const status = completed.status || "unknown";
        const hint =
          status === "queued" || status === "running"
            ? "Проверьте, что Celery worker и SD‑конвейер запущены, затем попробуйте снова."
            : "";
        throw new Error(completed.error || `Generation ${status}.${hint ? ` ${hint}` : ""}`);
      }
      const variants = (completed.variants || []).map<SlideVariant>((variant: ImageVariant) => ({
        id: variant.id,
        url: variant.url,
        thumbnail_url: variant.thumbnail_url || null,
      }));
      const nextImageUrl = activeSlide.image_url || variants[0]?.url || "";
      const nextVariantId = activeSlide.image_url ? activeSlide.image_variant_id || "" : variants[0]?.id || "";
      updateSlideById(targetSlideId, {
        variants,
        image_url: nextImageUrl,
        image_variant_id: nextVariantId,
      });
      if (isMounted.current) {
        setSlideJobs((prev) => ({
          ...prev,
          [targetSlideId]: {
            status: "done",
            stage: completed.stage || "Генерация завершена",
            progress: 100,
            params: {
              ...(prev[targetSlideId]?.params || resolvedParams),
              ...(completed.config || {}),
            },
          },
        }));
      }
      console.log("[SceneSequenceEditor] Generation complete, variants updated:", variants.length);
    } catch (error: any) {
      console.error("[SceneSequenceEditor] Generation failed:", error);
      if (isMounted.current) {
        setSlideJobs((prev) => ({
          ...prev,
          [targetSlideId]: {
            status: "error",
            error: error?.message || "Не удалось сгенерировать.",
            stage: "Ошибка генерации",
            progress: prev[targetSlideId]?.progress,
            params: prev[targetSlideId]?.params || resolvedParams,
          },
        }));
      }
    }
  };

  const handleSelectVariant = (variant: SlideVariant) => {
    if (!activeSlide) return;
    updateSlide(activeIndex, { image_url: variant.url, image_variant_id: variant.id });
  };

  const handleRemoveVariant = async (variant: SlideVariant) => {
    if (!activeSlide) return;
    const targetSlideId = activeSlide.id;
    try {
      if (variant.id) {
        await deleteSceneImage(scene.id, variant.id);
      }
    } catch (error) {
      console.error("Failed to delete variant", error);
    }
    const nextVariants = (activeSlide.variants || []).filter((item) => item.id !== variant.id);
    const isSelected = activeSlide.image_variant_id === variant.id || activeSlide.image_url === variant.url;
    updateSlideById(targetSlideId, {
      variants: nextVariants,
      image_url: isSelected ? "" : activeSlide.image_url,
      image_variant_id: isSelected ? "" : activeSlide.image_variant_id,
    });
  };

  const handleClearVariants = async () => {
    if (!activeSlide) return;
    const targetSlideId = activeSlide.id;
    const variants = activeSlide.variants || [];
    for (const variant of variants) {
      if (!variant.id) continue;
      try {
        await deleteSceneImage(scene.id, variant.id);
      } catch (error) {
        console.error("Failed to delete variant", error);
      }
    }
    updateSlideById(targetSlideId, { variants: [], image_url: "", image_variant_id: "" });
  };

  const handleGenerateCompositionPrompt = async () => {
    if (!activeSlide) {
      console.error("[SceneSequenceEditor] No active slide");
      return;
    }

    const targetSlideId = activeSlide.id;
    const slotCastIds = getSlotCastIds();
    setCompositionLoading(true);
    setCompositionError(null);

    try {
      // Prefer explicit visual notes (user_prompt) over narrative text.
      const visualParts: string[] = [];
      const userVisual = activeSlide.user_prompt?.trim();
      if (userVisual) {
        visualParts.push(userVisual);
      } else {
        if (activeSlide.title) visualParts.push(activeSlide.title);
        if (activeSlide.exposition) visualParts.push(activeSlide.exposition);
        if (activeSlide.thought) visualParts.push(activeSlide.thought);
        const dialogueText = buildDialogueText(activeSlide);
        if (dialogueText) visualParts.push(dialogueText);
      }

      const slideVisual = visualParts.join(". ") || "Scene composition";

      console.log("[SceneSequenceEditor] Generating composition prompt:", {
        sceneId: scene.id,
        slideId: targetSlideId,
        visual: slideVisual.slice(0, 100),
        castIds: slotCastIds,
        locationId: scene.location_id,
        framing: activeSlide.framing,
      });

      const result = await generateCompositionPrompt(scene.id, {
        slide_visual: slideVisual,
        cast_ids: slotCastIds,
        slide_id: targetSlideId,
        location_id: scene.location_id || undefined,
        framing: activeSlide.framing || "full",
        has_location_reference: !isCreativeMode &&
          (activeSlide.pipeline?.location_ref_mode || "auto") !== "none" &&
          Boolean(getEffectiveLocationPreviewUrl()),
      });

      console.log("[SceneSequenceEditor] Composition prompt generated:", result.composition_prompt);
      applyCompositionResult(targetSlideId, result, slotCastIds);

      if (isMounted.current) {
        setCompositionLoading(false);
      }
    } catch (error: any) {
      console.error("[SceneSequenceEditor] Composition generation failed:", error);
      if (isMounted.current) {
        setCompositionError(error?.message || "Не удалось сгенерировать композицию.");
        setCompositionLoading(false);
      }
    }
  };

  const handleSave = async () => {
    if (saving) return;
    if (sequence.slides.length === 0 && !sequence.choice_key && !sequence.choice_prompt) {
      await onSave(null);
      return;
    }
    const cleaned = {
      ...sequence,
      slides: sequence.slides.map((slide) => ({
        ...slide,
        exposition: slide.exposition?.trim() || "",
        thought: slide.thought?.trim() || "",
        title: slide.title?.trim() || "",
        dialogue: (slide.dialogue || []).filter((line) => line.text.trim()),
      })),
    };
    await onSave(cleaned);
  };

  const handleAIDraft = async () => {
    if (sequence.slides.length > 0) {
      setAiError("Удалите существующие слайды, чтобы сгенерировать новый AI‑черновик.");
      return;
    }
    setAiLoading(true);
    setAiError(null);
    try {
      const presetMap = new Map((presets?.characters || []).map((preset) => [preset.id, preset]));
      const contextParts = [
        scene.title ? `title: ${scene.title}` : null,
        scene.synopsis ? `synopsis: ${scene.synopsis}` : null,
        scene.content ? `content: ${scene.content}` : null,
        scene.location?.name ? `location: ${scene.location.name}` : null,
        scene.location?.description ? `location description: ${scene.location.description}` : null,
        `scene type: ${scene.scene_type}`,
      ].filter(Boolean);
      const castLines = sceneCharacters.map((link) => {
        const preset = presetMap.get(link.character_preset_id);
        const name = preset?.name || link.character_preset_id;
        const desc = preset?.description ? `; ${preset.description}` : "";
        const ctx = link.scene_context ? `; context: ${link.scene_context}` : "";
        const pos = link.position ? `; position: ${link.position}` : "";
        const inFrame = link.in_frame === false ? "; вне кадра" : "";
        return `- ${name} (id: ${link.character_preset_id}${inFrame}${desc}${ctx}${pos})`;
      });
      if (castLines.length > 0) {
        contextParts.push(`characters (use ids for cast_ids):\n${castLines.join("\n")}`);
      }
      const response = await generateFormFill({
        form_type: "scene_sequence",
        fields: AI_SEQUENCE_FIELDS,
        current_values: { sequence },
        context: contextParts.join("\n"),
        extra_context: aiPrompt.trim() || undefined,
        detail_level: aiDetail,
        // AI draft should regenerate the whole sequence even if choice fields are already filled.
        fill_only_empty: false,
      });
      const nextSequence = normalizeSequence(response.values.sequence);
      const withDefaults: SceneSequence = {
        ...nextSequence,
        choice_key: (nextSequence.choice_key || "").trim() ? nextSequence.choice_key : (sequence.choice_key || ""),
        choice_prompt: (nextSequence.choice_prompt || "").trim()
          ? nextSequence.choice_prompt
          : (sequence.choice_prompt || ""),
        slides: nextSequence.slides.map((slide) => {
          const hasExplicitNoCast = Array.isArray(slide.cast_ids) && slide.cast_ids.length === 0;
          const pipeline =
            slide.pipeline ||
            (!hasExplicitNoCast ? { mode: "standard" } : undefined);
          const framing = slide.framing || "full";
          return { ...slide, pipeline, framing };
        }),
      };
      if (nextSequence.slides.length === 0) {
        setAiError("AI не вернул слайды. Попробуйте добавить больше инструкций.");
      } else {
        setSequence(withDefaults);
        setActiveIndex(0);
      }
    } catch (err: any) {
      setAiError(err?.message || "Не удалось сгенерировать последовательность.");
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div className="sequence-editor">
      <div className="sequence-editor-header">
        <div>
          <h3>Последовательность сцен</h3>
          <p className="muted">
            {isCreativeMode
              ? "Текст слайдов + рефы персонажей. Остальное генерируется автоматически."
              : "Создайте много‑кадровый рассказ с подложками и выборами."}
          </p>
        </div>
        <div className="sequence-editor-actions">
          <button className="ghost" type="button" onClick={addSlide}>
            + Slide
          </button>
          <button className="ghost" type="button" onClick={duplicateSlide} disabled={!activeSlide}>
            Duplicate
          </button>
          <button className="danger ghost" type="button" onClick={removeSlide} disabled={!activeSlide}>Удалить</button>
          <button className="primary" type="button" onClick={handleSave} disabled={saving}>
            {saving ? "Сохранение..." : "Сохранить последовательность"}
          </button>
        </div>
      </div>

      {sideCollapsed && orderedScenes.length > 0 && (
        <div className="sequence-editor-floating-nav">
          <div className="sequence-editor-floating-row">
            <button
              className="sequence-editor-floating-arrow"
              type="button"
              onClick={() => {
                if (selectedSceneIndex <= 0) return;
                const prevScene = orderedScenes[selectedSceneIndex - 1];
                if (prevScene) onNavigateScene?.(prevScene.id);
              }}
              disabled={selectedSceneIndex <= 0}
              title="Предыдущая сцена"
            >
              ←
            </button>
            <span className="sequence-editor-floating-title" title={scene.title || "Без названия"}>
              <span className="sequence-editor-floating-badge">◉</span>
              <span>{selectedSceneIndex + 1}/{orderedScenes.length}</span>
            </span>
            <button
              className="sequence-editor-floating-arrow"
              type="button"
              onClick={() => {
                if (selectedSceneIndex < 0 || selectedSceneIndex >= orderedScenes.length - 1) return;
                const nextScene = orderedScenes[selectedSceneIndex + 1];
                if (nextScene) onNavigateScene?.(nextScene.id);
              }}
              disabled={selectedSceneIndex < 0 || selectedSceneIndex >= orderedScenes.length - 1}
              title="Следующая сцена"
            >
              →
            </button>
          </div>
          <div className="sequence-editor-floating-row">
            <button
              className="sequence-editor-floating-arrow"
              type="button"
              onClick={() => setActiveIndex((prev) => Math.max(0, prev - 1))}
              disabled={slides.length === 0 || activeIndex === 0}
              title="Предыдущий слайд"
            >
              ←
            </button>
            <span className="sequence-editor-floating-title" title={activeSlide?.title || "Без названия"}>
              <span className="sequence-editor-floating-badge">▦</span>
              {slides.length === 0
                ? "0/0"
                : `${activeIndex + 1}/${slides.length}`}
            </span>
            <button
              className="sequence-editor-floating-arrow"
              type="button"
              onClick={() => setActiveIndex((prev) => Math.min(slides.length - 1, prev + 1))}
              disabled={slides.length === 0 || activeIndex >= slides.length - 1}
              title="Следующий слайд"
            >
              →
            </button>
          </div>
        </div>
      )}

      <div className="sequence-editor-ai">
        <label>
          AI промпт
          <textarea
            rows={2}
            value={aiPrompt}
            onChange={(event) => setAiPrompt(event.target.value)}
            placeholder="Опишите ход сцены, эмоции и ключевые моменты"
          />
        </label>
        <label>
          Уровень детализации
          <select value={aiDetail} onChange={(event) => setAiDetail(event.target.value as typeof aiDetail)}>
            <option value="narrow">Кратко</option>
            <option value="standard">Стандартно</option>
            <option value="detailed">Подробно</option>
          </select>
        </label>
        <button className="secondary" type="button" onClick={handleAIDraft} disabled={aiLoading}>
          {aiLoading ? "Генерация..." : "AI‑черновик последовательности"}
        </button>
        {aiError && <div className="sequence-editor-error">{aiError}</div>}
      </div>

      <div className="sequence-editor-grid">
        <div className="sequence-editor-form">
          <div className="sequence-editor-slide-strip">
            <div className="sequence-editor-slide-strip-nav">
              <button
                className="ghost"
                type="button"
                onClick={() => setActiveIndex((prev) => Math.max(0, prev - 1))}
                disabled={slides.length === 0 || activeIndex === 0}
              >
                ←
              </button>
              <div className="sequence-editor-slide-strip-current">
                {slides.length === 0 ? (
                  <strong>Слайдов нет</strong>
                ) : (
                  <>
                    <strong>
                      Слайд {activeIndex + 1} из {slides.length}
                    </strong>
                    {slideJob?.status && (
                      <span
                        className={`sequence-editor-status ${slideJob.status} ${
                          isActiveJobStatus(slideJob.status) ? "is-active" : ""
                        }`}
                      >
                        {statusLabel(slideJob.status)}
                        {slideJobProgress !== undefined ? ` ${slideJobProgress}%` : ""}
                      </span>
                    )}
                  </>
                )}
              </div>
              <button
                className="ghost"
                type="button"
                onClick={() => setActiveIndex((prev) => Math.min(slides.length - 1, prev + 1))}
                disabled={slides.length === 0 || activeIndex >= slides.length - 1}
              >
                →
              </button>
            </div>
            <button className="ghost" type="button" onClick={() => setSlideDrawerOpen(true)} disabled={slides.length === 0}>
              Все слайды
            </button>
          </div>
          {activeSlide ? (
            <>
              <label>Заголовок<input
                  value={activeSlide.title || ""}
                  onChange={(event) => updateSlide(activeIndex, { title: event.target.value })}
                  placeholder="Необязательный заголовок слайда"
                />
              </label>
              <label>Изображение<select
                  value={activeSlide.image_url || ""}
                  onChange={(event) =>
                    updateSlide(activeIndex, { image_url: event.target.value, image_variant_id: "" })
                  }
                >
                  <option value="">Использовать по умолчанию</option>
                  {imageOptions.map((opt) => (
                    <option key={opt.key} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                URL пользовательского изображения
                <input
                  value={activeSlide.image_url || ""}
                  onChange={(event) =>
                    updateSlide(activeIndex, { image_url: event.target.value, image_variant_id: "" })
                  }
                  placeholder="https://..."
                />
              </label>
              {activeSlide.image_url && (
                <div className="sequence-editor-image-actions">
                  <button
                    className="ghost"
                    type="button"
                    onClick={() => onPreviewImage?.(activeSlide.image_url || "")}
                  >
                    Просмотр изображения
                  </button>
                  <button
                    className="ghost danger"
                    type="button"
                    onClick={() => updateSlide(activeIndex, { image_url: "", image_variant_id: "" })}
                  >
                    Очистить изображение
                  </button>
                </div>
              )}
              <label>
                Озвучка / закадровый текст
                <textarea
                  rows={3}
                  value={activeSlide.exposition || ""}
                  onChange={(event) => updateSlide(activeIndex, { exposition: event.target.value })}
                  placeholder="Закадровое повествование или описание сцены"
                />
              </label>
              <div className="sequence-editor-note muted">Порядок: озвучка → мысли → диалог.</div>
              <label>
                Внутренние мысли
                <textarea
                  rows={2}
                  value={activeSlide.thought || ""}
                  onChange={(event) => updateSlide(activeIndex, { thought: event.target.value })}
                  placeholder="Внутренний монолог"
                />
              </label>
              <label>
                Анимация
                <select
                  value={activeSlide.animation || "fade"}
                  onChange={(event) => updateSlide(activeIndex, { animation: event.target.value })}
                >
                  <option value="none">Нет</option>
                  <option value="fade">Плавно</option>
                  <option value="rise">Подъём</option>
                  <option value="float">Плавание</option>
                </select>
              </label>

                <div className="sequence-editor-render">
                  <div className="sequence-editor-render-header">
                    <strong>Параметры рендера</strong>
                    <div className="sequence-editor-render-actions">
                      <button className="ghost" type="button" onClick={resetCastToInFrame} disabled={!hasCustomCast}>
                        Использовать «в кадре»
                      </button>
                      <button className="ghost danger" type="button" onClick={clearCast} disabled={!activeSlide}>
                        Без персонажей
                      </button>
                    </div>
                  </div>
                <label>
                  Кадрирование
                  <select
                    value={activeSlide.framing || "full"}
                    onChange={(event) =>
                      updateSlide(activeIndex, {
                        framing: event.target.value as "full" | "half" | "portrait",
                      })
                    }
                  >
                    <option value="full">В полный рост</option>
                    <option value="half">Поясной</option>
                    <option value="portrait">Портрет</option>
                  </select>
                </label>
                {!isCreativeMode ? (
                  <>
                    <label>
                      Конвейер
                      <select
                        value={pipelineMode}
                        onChange={(event) => updatePipeline({ mode: event.target.value as "standard" | "controlnet" })}
                      >
                        <option value="standard">Стандартный (только промпт)</option>
                        <option value="controlnet">ControlNet + IP‑Adapter (мульти‑проход)</option>
                      </select>
                    </label>
                    {pipelineMode === "controlnet" && (
                      <label>
                        Фиксация личности
                        <select
                          value={identityMode}
                          onChange={(event) =>
                            updatePipeline({ identity_mode: event.target.value as "ip_adapter" | "reference" })
                          }
                        >
                          <option value="ip_adapter">IP‑Adapter (предпочтительно)</option>
                          <option value="reference">Только референсы</option>
                        </select>
                      </label>
                    )}
                    <div className="sequence-editor-note muted">
                      Используйте ControlNet, когда нужна сильная фиксация личности или позы. IP‑Adapter
                      автоматически переключится на референсы, если недоступен.
                    </div>
                    {pipelineMode === "controlnet" && (
                      <label>
                        URL изображения позы (необязательно)
                        <input
                          value={activeSlide.pipeline?.pose_image_url || ""}
                          onChange={(event) => updatePipeline({ pose_image_url: event.target.value })}
                          placeholder="/api/assets/..."
                        />
                      </label>
                    )}
                  </>
                ) : (
                  <div className="sequence-editor-note muted">
                    Творческий режим: используем фиксированные рефы персонажей. Локация и композиция строятся по тексту слайда.
                  </div>
                )}
                <div className="sequence-editor-cast">
                  <div className="sequence-editor-cast-header">
                    <strong>Состав</strong>
                    <span className="muted">{selectedCastIds.length} выбрано</span>
                  </div>
                  <label className="sequence-editor-cast-toggle">
                    <input
                      type="checkbox"
                      checked={showLibraryList}
                      onChange={(event) => setShowLibrary(event.target.checked)}
                    />
                    <span>Включать персонажей из библиотеки</span>
                  </label>
                  {showLibraryList && libraryLoading && <div className="muted">Загрузка персонажей библиотеки...</div>}
                  {showLibraryList && libraryError && (
                    <div className="sequence-editor-error">
                      Не удалось загрузить персонажей библиотеки.
                    </div>
                  )}
                  {castOptions.length === 0 ? (
                    <div className="muted">К этой сцене не привязаны персонажи.</div>
                  ) : (
                    <div className="sequence-editor-cast-list">
                      {castOptions.map((opt) => {
                        const isSelected = selectedCastIds.includes(opt.id);
                        const previewUrl = getCharacterPreviewUrl(opt.id);
                        return (
                          <button
                            key={opt.id}
                            type="button"
                            className={`sequence-editor-cast-tile ${isSelected ? "selected" : "muted"}`}
                            onClick={() => toggleCast(opt.id)}
                            title={isSelected ? "Убрать из состава" : "Добавить в состав"}
                          >
                            <div className={`sequence-editor-cast-thumb-wrap ${previewUrl ? "" : "fallback"}`}>
                              {previewUrl ? (
                                <img src={previewUrl} alt={opt.name} className="sequence-editor-cast-thumb" />
                              ) : (
                                <span className="sequence-editor-cast-fallback">
                                  {(opt.name || "?").slice(0, 1).toUpperCase()}
                                </span>
                              )}
                            </div>
                            <span className="sequence-editor-cast-name">{opt.name}</span>
                            {opt.source === "library" ? (
                              <span className="sequence-editor-cast-pill">библиотека</span>
                            ) : opt.in_frame ? (
                              <span className="sequence-editor-cast-pill">в кадре</span>
                            ) : (
                              <span className="sequence-editor-cast-pill">персонаж</span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              <div className="sequence-editor-dialogue">
                <div className="sequence-editor-dialogue-header">
                  <strong>Диалог</strong>
                  <button className="ghost" type="button" onClick={addDialogue}>
                    + Реплика
                  </button>
                </div>
                {(activeSlide.dialogue || []).length === 0 ? (
                  <div className="muted">Диалогов пока нет.</div>
                ) : (
                  (activeSlide.dialogue || []).map((line, idx) => (
                    <div key={line.id || `${activeSlide.id}-${idx}`} className="sequence-editor-dialogue-line">
                      <input
                        value={line.speaker || ""}
                        onChange={(event) => updateDialogue(idx, { speaker: event.target.value })}
                        placeholder="Говорящий"
                      />
                      <input
                        value={line.text || ""}
                        onChange={(event) => updateDialogue(idx, { text: event.target.value })}
                        placeholder="Текст реплики"
                      />
                      <button className="ghost" type="button" onClick={() => removeDialogue(idx)}>
                        ✕
                      </button>
                    </div>
                  ))
                )}
              </div>

              <div className="sequence-editor-prompt">
                <div className="sequence-editor-prompt-header">
                  <strong>Промпт слайда</strong>
                  <button
                    className="ghost"
                    type="button"
                    onClick={() => {
                      setPromptBundle(null);
                      setPromptError(null);
                      setPromptLoading(true);
                      previewScenePrompt(scene.id, { characterIds: activeSlide?.cast_ids })
                        .then((bundle) => {
                          if (isMounted.current) setPromptBundle(bundle);
                        })
                        .catch((error: any) => {
                          if (isMounted.current) {
                            setPromptError(error?.message || "Не удалось загрузить промпт.");
                          }
                        })
                        .finally(() => {
                          if (isMounted.current) setPromptLoading(false);
                        });
                    }}
                    disabled={promptLoading}
                  >
                    {promptLoading ? "Обновление..." : "Обновить контекст"}
                  </button>
                </div>
                <label>
                  Автопромпт (контекст)
                  <textarea rows={4} value={autoPrompt} readOnly />
                </label>
                <label>
                  Дополнение к промпту
                  <textarea
                    rows={3}
                    value={activeSlide.user_prompt || ""}
                    onChange={(event) => updateSlide(activeIndex, { user_prompt: event.target.value })}
                    placeholder="Добавьте детали кадра или заметки по камере"
                  />
                </label>
                <div className="sequence-editor-composition">
                  <div className="sequence-editor-composition-header">
                    <strong>Композиция (img2img)</strong>
                    <button
                      className="ghost"
                      type="button"
                      onClick={handleGenerateCompositionPrompt}
                      disabled={compositionLoading || !activeSlide}
                    >
                      {compositionLoading ? "Генерация..." : activeSlide?.composition_prompt ? "Перегенерировать" : "Сгенерировать композицию"}
                    </button>
                  </div>
                  <div className="sequence-editor-reference-slots">
                    <div className="sequence-editor-reference-grid">
                      {!isCreativeMode && (
                        <div className="sequence-editor-reference-card">
                          <div className="sequence-editor-reference-title">Вход image 1 (локация)</div>
                          <select
                            value={
                              locationRefMode === "none"
                                ? "none"
                                : locationRefMode === "selected" && locationRefUrl
                                  ? `selected:${locationRefUrl}`
                                  : "auto"
                            }
                            onChange={(event) => {
                              const value = event.target.value;
                              if (value === "none") {
                                updatePipelineAndPersist({ location_ref_mode: "none", location_ref_url: "" });
                                return;
                              }
                              if (value === "auto") {
                                updatePipelineAndPersist({ location_ref_mode: "auto", location_ref_url: "" });
                                return;
                              }
                              if (value.startsWith("selected:")) {
                                updatePipelineAndPersist({
                                  location_ref_mode: "selected",
                                  location_ref_url: value.slice("selected:".length),
                                });
                              }
                            }}
                          >
                            <option value="auto">Авто (из сцены)</option>
                            <option value="none">Без референса (сгенерировать фон)</option>
                            {locationReferenceOptions.map((opt) => (
                              <option key={opt.value} value={`selected:${opt.value}`}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                          {getEffectiveLocationPreviewUrl() ? (
                            <img
                              src={getEffectiveLocationPreviewUrl()}
                              alt="location reference"
                              className="sequence-editor-reference-preview sequence-editor-reference-preview-mini"
                              onClick={() => onPreviewImage?.(getEffectiveLocationPreviewUrl())}
                            />
                          ) : (
                            <div className="muted">Фон будет сгенерирован из текстового описания.</div>
                          )}
                        </div>
                      )}
                      {isCreativeMode && (
                        <div className="sequence-editor-reference-card">
                          <div className="sequence-editor-reference-title">Фон</div>
                          <div className="muted">
                            В творческом режиме локация всегда строится по текстовому описанию текущего слайда.
                          </div>
                        </div>
                      )}
                      {[0, 1].map((slotIndex) => {
                        const slotLabel = slotIndex === 0 ? "Вход image 2 (персонаж 1)" : "Вход image 3 (персонаж 2)";
                        const selectedId = resolvedCharacterSlotIds[slotIndex] || "";
                        const selectedName = selectedId ? getCharacterDisplayName(selectedId) : "Не использовать";
                        const previewUrl = selectedId ? getCharacterPreviewUrl(selectedId) : "";
                        return (
                          <div className="sequence-editor-reference-card" key={`slot-${slotIndex}`}>
                            <div className="sequence-editor-reference-title">{slotLabel}</div>
                            <div className="sequence-editor-slot-picker">
                              <button
                                type="button"
                                className="sequence-editor-slot-trigger"
                                onClick={() =>
                                  setOpenCharacterSlotPicker((prev) => (prev === slotIndex ? null : slotIndex))
                                }
                              >
                                {selectedName}
                                <span className="sequence-editor-slot-trigger-icon">▾</span>
                              </button>
                              {openCharacterSlotPicker === slotIndex && (
                                <div className="sequence-editor-slot-popover">
                                  <button
                                    type="button"
                                    className={`sequence-editor-slot-option ${selectedId ? "" : "selected"}`}
                                    onClick={() => updateCharacterSlot(slotIndex, "")}
                                  >
                                    <span className="sequence-editor-slot-option-media sequence-editor-slot-option-media-empty">
                                      —
                                    </span>
                                    <span className="sequence-editor-slot-option-label">Не использовать</span>
                                  </button>
                                  {slotCharacterOptions.map((opt) => {
                                    const optionPreviewUrl = getCharacterPreviewUrl(opt.id);
                                    return (
                                      <button
                                        key={opt.id}
                                        type="button"
                                        className={`sequence-editor-slot-option ${selectedId === opt.id ? "selected" : ""}`}
                                        onClick={() => updateCharacterSlot(slotIndex, opt.id)}
                                      >
                                        <span className="sequence-editor-slot-option-media">
                                          {optionPreviewUrl ? (
                                            <img
                                              src={optionPreviewUrl}
                                              alt={opt.label}
                                              className="sequence-editor-slot-option-thumb"
                                            />
                                          ) : (
                                            <span className="sequence-editor-slot-option-fallback">
                                              {(opt.label || "?").slice(0, 1).toUpperCase()}
                                            </span>
                                          )}
                                        </span>
                                        <span className="sequence-editor-slot-option-label">{opt.label}</span>
                                      </button>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                            {previewUrl ? (
                              <img
                                src={previewUrl}
                                alt={selectedId}
                                className="sequence-editor-reference-preview sequence-editor-reference-preview-mini"
                                onClick={() => onPreviewImage?.(previewUrl)}
                              />
                            ) : (
                              <div className="muted">Выберите персонажа для этого входа.</div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  <label>
                    Промпт композиции
                    <textarea
                      rows={3}
                      value={activeSlide.composition_prompt || ""}
                      onChange={(event) => updateSlide(activeIndex, { composition_prompt: event.target.value })}
                      onBlur={() => persistSequenceQuietly(sequence)}
                      placeholder="AI сгенерирует инструкции по размещению персонажей в локации"
                    />
                  </label>
                  {compositionError && <div className="sequence-editor-error">{compositionError}</div>}
                  <div className="sequence-editor-note muted">
                    {isCreativeMode
                      ? "Композиционный промпт описывает расстановку персонажей. Фон и кадр строятся только из текста слайда."
                      : "Композиционный промпт описывает, как разместить персонажей из референсов в фоновую локацию. Используется для img2img генерации с scene_img2img.json workflow."}
                  </div>
                </div>
                <label>
                  Негативный промпт (контекст)
                  <textarea rows={2} value={promptBundle?.negative_prompt || ""} readOnly />
                </label>
                {promptError && <div className="sequence-editor-error">{promptError}</div>}
              </div>

              <div className="sequence-editor-generation">
                <label>Варианты<select
                    value={variantCount}
                    onChange={(event) => setVariantCount(Number(event.target.value))}
                  >
                    {[1, 2, 3, 4, 5, 6, 7, 8].map((count) => (
                      <option key={count} value={count}>
                        {count}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="secondary"
                  type="button"
                  onClick={handleGenerateVariants}
                  title={generationDisabled ? generationDisabledReason : undefined}
                  disabled={
                    generationDisabled ||
                    promptLoading ||
                    !promptBundle?.prompt ||
                    !finalPrompt ||
                    isSlideJobActive
                  }
                >
                  {isSlideJobActive ? (
                    <span className="sequence-editor-button-busy">
                      <span className="sequence-editor-spinner" aria-hidden="true" />
                      Генерация...
                    </span>
                  ) : (
                    "Сгенерировать варианты"
                  )}
                </button>
                {slideJob?.status && (
                  <div className="sequence-editor-job-meta muted">
                    {statusLabel(slideJob.status)}
                    {slideJob.stage ? ` · ${slideJob.stage}` : ""}
                    {slideJobProgress !== undefined ? ` · ${slideJobProgress}%` : ""}
                  </div>
                )}
                {slideJob?.status === "error" && (
                  <div className="sequence-editor-error">{slideJob.error || "Не удалось сгенерировать."}</div>
                )}
                {isSlideJobActive && (
                  <div className="sequence-editor-progress">
                    <div className="sequence-editor-progress-track">
                      <div
                        className={`sequence-editor-progress-fill ${
                          slideJobProgress === undefined ? "indeterminate" : ""
                        }`}
                        style={
                          slideJobProgress === undefined
                            ? undefined
                            : { width: `${Math.max(0, Math.min(100, slideJobProgress))}%` }
                        }
                      />
                    </div>
                  </div>
                )}
              </div>

              {slideJob?.params && !isCreativeMode && (
                <div className="sequence-editor-runtime-card">
                  <div className="sequence-editor-runtime-title">Параметры обработки</div>
                  <div className="sequence-editor-runtime-grid">
                    <span>Workflow: {slideJob.params.workflow}</span>
                    <span>Prompt: {slideJob.params.prompt_mode}</span>
                    <span>Размер: {slideJob.params.width || "auto"} × {slideJob.params.height || "auto"}</span>
                    <span>CFG/Steps: {slideJob.params.cfg_scale || "auto"} / {slideJob.params.steps || "auto"}</span>
                    <span>Seed: {slideJob.params.seed || "auto"}</span>
                    <span>Варианты: {slideJob.params.variants}</span>
                    <span>Pipeline: {slideJob.params.pipeline_mode}</span>
                    <span>Identity: {slideJob.params.identity_mode || "-"}</span>
                    <span>Loc ref: {slideJob.params.location_ref_mode || "auto"}</span>
                    <span>Char slots: {(slideJob.params.character_slot_ids || []).join(", ") || "-"}</span>
                  </div>
                </div>
              )}

              <div className="sequence-editor-variants">
                <div className="sequence-editor-variants-header">
                  <strong>Сгенерированные варианты</strong>
                  {activeVariants.length > 0 && (
                    <button
                      className="ghost"
                      type="button"
                      onClick={handleClearVariants}
                    >
                      Очистить варианты
                    </button>
                  )}
                </div>
                {activeVariants.length === 0 ? (
                  <div className="muted">Вариантов пока нет.</div>
                ) : (
                  <div className="sequence-editor-variants-grid">
                    {activeVariants.map((variant) => (
                      <div
                        key={variant.id}
                        className={`sequence-editor-variant-card ${
                          activeSlide.image_variant_id === variant.id ? "selected" : ""
                        }`}
                      >
                        <div className="sequence-editor-variant-media">
                          <img
                            className="sequence-editor-variant-image"
                            src={variant.thumbnail_url || variant.url}
                            alt="вариант"
                            onClick={() => onPreviewImage?.(variant.url)}
                          />
                          <div className="sequence-editor-variant-actions-overlay">
                            <button
                              className="sequence-editor-variant-icon-btn"
                              type="button"
                              title="Использовать"
                              aria-label="Использовать вариант"
                              onClick={() => handleSelectVariant(variant)}
                            >
                              ✓
                            </button>
                            <button
                              className="sequence-editor-variant-icon-btn"
                              type="button"
                              title="Предпросмотр"
                              aria-label="Открыть предпросмотр"
                              onClick={() => onPreviewImage?.(variant.url)}
                            >
                              ↗
                            </button>
                            <button
                              className="sequence-editor-variant-icon-btn danger"
                              type="button"
                              title="Удалить"
                              aria-label="Удалить вариант"
                              onClick={() => handleRemoveVariant(variant)}
                            >
                              ✕
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

            </>
          ) : (
            <div className="muted">Выберите слайд для редактирования.</div>
          )}

          <div className="sequence-editor-choice">
            <label>
              Ключ выбора (переменная сессии)
              <input
                value={sequence.choice_key || ""}
                onChange={(event) => setSequence((prev) => ({ ...prev, choice_key: event.target.value }))}
                placeholder="например, вердикт"
              />
            </label>
            <label>
              Текст выбора
              <input
                value={sequence.choice_prompt || ""}
                onChange={(event) => setSequence((prev) => ({ ...prev, choice_prompt: event.target.value }))}
                placeholder="Что должен сделать игрок?"
              />
            </label>
          </div>
        </div>
      </div>

      {slideDrawerOpen && (
        <div className="sequence-editor-list-backdrop" onClick={() => setSlideDrawerOpen(false)}>
          <aside className="sequence-editor-list-drawer" onClick={(event) => event.stopPropagation()}>
            <div className="sequence-editor-list-drawer-head">
              <strong>Слайды</strong>
              <button className="ghost" type="button" onClick={() => setSlideDrawerOpen(false)}>
                Закрыть
              </button>
            </div>
            <div className="sequence-editor-list">
              {slides.map((slide, idx) => {
                const itemJob = slideJobs[slide.id];
                const itemProgress = toProgressPercent(itemJob?.progress);
                return (
                  <button
                    key={slide.id}
                    className={`sequence-editor-item ${idx === activeIndex ? "active" : ""}`}
                    type="button"
                    onClick={() => {
                      setActiveIndex(idx);
                      setSlideDrawerOpen(false);
                    }}
                  >
                    <div className="sequence-editor-item-head">
                      <span>Слайд {idx + 1}</span>
                      {itemJob?.status && (
                        <span
                          className={`sequence-editor-status ${itemJob.status} ${
                            isActiveJobStatus(itemJob.status) ? "is-active" : ""
                          }`}
                        >
                          {statusLabel(itemJob.status)}
                          {itemProgress !== undefined ? ` ${itemProgress}%` : ""}
                        </span>
                      )}
                    </div>
                    <span className="muted">{slide.title || slide.exposition?.slice(0, 40) || "Без названия"}</span>
                  </button>
                );
              })}
            </div>
            {slides.length > 0 && (
              <div className="sequence-editor-reorder">
                <button className="ghost" type="button" onClick={() => moveSlide(-1)} disabled={activeIndex === 0}>
                  ↑ Вверх
                </button>
                <button
                  className="ghost"
                  type="button"
                  onClick={() => moveSlide(1)}
                  disabled={activeIndex >= slides.length - 1}
                >
                  ↓ Вниз
                </button>
              </div>
            )}
          </aside>
        </div>
      )}

    </div>
  );
}
