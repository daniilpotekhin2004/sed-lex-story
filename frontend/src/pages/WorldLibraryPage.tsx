import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { generateDescription } from "../api/ai";
import type { AIFieldSpec } from "../api/ai";
import { getProject, updateProject } from "../api/projects";
import { bootstrapLegalStyleProfiles, createStyleProfile, listStyleProfiles } from "../api/styleProfiles";
import {
  createArtifact,
  createDocumentTemplate,
  createLocation,
  createStudioArtifact,
  createStudioDocumentTemplate,
  createStudioLocation,
  deleteArtifact,
  deleteDocumentTemplate,
  deleteLocation,
  deleteStudioArtifact,
  deleteStudioDocumentTemplate,
  deleteStudioLocation,
  getArtifact,
  getLocation,
  getStyleBible,
  listArtifacts,
  listDocumentTemplates,
  listLocations,
  listStudioArtifacts,
  listStudioDocumentTemplates,
  listStudioLocations,
  importArtifact,
  importDocumentTemplate,
  importLocation,
  uploadArtifactPreview,
  uploadLocationPreview,
  uploadLocationReference,
  updateArtifact,
  updateDocumentTemplate,
  updateLocation,
  updateStudioArtifact,
  updateStudioDocumentTemplate,
  updateStudioLocation,
  upsertStyleBible,
} from "../api/world";
import {
  createCharacterPreset,
  deleteCharacterPreset,
  getCharacterPreset,
  listCharacterPresets,
  listProjectCharacters,
  importCharacterPreset,
  uploadCharacterReference,
  updateCharacterPreset,
} from "../api/characters";
import { useAssetGeneration } from "../hooks/useAssetGeneration";
import { getAssetUrl } from "../api/client";
import type {
  Artifact,
  CharacterPreset,
  DocumentTemplate,
  GenerationOverrides,
  Location,
  Project,
  StyleProfile,
  StyleBible,
} from "../shared/types";
import {
  CREATIVE_CHARACTER_REFERENCE_KINDS,
  CHARACTER_REFERENCE_SLOTS,
  POSE_REFERENCE_KINDS,
  VIEW_REFERENCE_KINDS,
} from "../shared/characterReferences";
import {
  getProjectDevelopmentMode,
  setProjectDevelopmentMode,
  type ProjectDevelopmentMode,
} from "../utils/projectDevelopmentMode";
import QuickCreateModal, { type QuickCreateData } from "../components/QuickCreateModal";
import AssetWizardModal, { type WizardResult } from "../components/AssetWizardModal";
import { ImageLightbox } from "../components/ImageLightbox";
import CharacterVisualStudio from "../components/CharacterVisualStudio";
import AIFillModal from "../components/AIFillModal";
import ImportAssetModal from "../components/ImportAssetModal";
import AdvancedGenerationSettings from "../components/AdvancedGenerationSettings";
import UploadButton from "../components/UploadButton";
import { getGenerationEnvironment, setGenerationEnvironment } from "../utils/generationEnvironment";
import {
  formatAssetSourceLabel,
  getArtifactPreviewAssetSource,
  getLocationPreviewAssetSource,
  getReferenceAssetSource,
} from "../utils/assetSource";

type TabId = "locations" | "characters" | "artifacts" | "style" | "documents";
type CharacterRenderPayload = {
  kind: string;
  label?: string;
  count?: number;
  prompt_override?: string;
  negative_prompt?: string;
  width?: number;
  height?: number;
  steps?: number;
  cfg_scale?: number;
  seed?: number | null;
  sampler?: string;
  scheduler?: string;
  model_id?: string;
  vae_id?: string;
  loras?: { name: string; weight: number }[];
  pipeline_profile_id?: string;
  pipeline_profile_version?: number;
};
type AIFillConfig = {
  title: string;
  formType: string;
  fields: AIFieldSpec[];
  currentValues: Record<string, unknown>;
  context?: string;
  onApply: (values: Record<string, unknown>) => void;
};
type ImportType = "location" | "character" | "artifact" | "document";
type ImportItem = { id: string; name: string; description?: string | null; detail?: string | null; badges?: string[] };
const IMPORT_TYPE_LABELS: Record<ImportType, string> = {
  location: "локации",
  character: "персонажа",
  artifact: "артефакта",
  document: "шаблона документа",
};

const BASE_TAB_DEFS: { id: TabId; label: string; note: string }[] = [
  { id: "locations", label: "Локации", note: "Атмосферные якоря для каждой сцены" },
  { id: "characters", label: "Персонажи", note: "Голоса, роли и визуальные якоря" },
  { id: "artifacts", label: "Артефакты", note: "Доказательства, документы и ключевой реквизит" },
  { id: "style", label: "Библия стиля", note: "Тон, глоссарий, нарративные ограничения" },
  { id: "documents", label: "Документы", note: "Переиспользуемые юридические шаблоны" },
];

const CREATIVE_MODE_TAB_IDS: TabId[] = ["characters", "locations"];

const isTabId = (value: string | null): value is TabId =>
  value === "locations" ||
  value === "characters" ||
  value === "artifacts" ||
  value === "style" ||
  value === "documents";

const hasRequiredCharacterRefs = (character: CharacterPreset, requiredKinds: readonly string[]) => {
  const kinds = new Set(
    (character.reference_images || [])
      .map((ref) => ref?.kind)
      .filter((kind): kind is string => typeof kind === "string" && Boolean(kind)),
  );
  return requiredKinds.every((kind) => kinds.has(kind));
};

const getMissingRequiredCharacterRefs = (
  character: CharacterPreset,
  requiredKinds: readonly string[],
): string[] => {
  const kinds = new Set(
    (character.reference_images || [])
      .map((ref) => ref?.kind)
      .filter((kind): kind is string => typeof kind === "string" && Boolean(kind)),
  );
  return requiredKinds.filter((kind) => !kinds.has(kind));
};

const QWEN_SKETCH_DEFAULTS: Pick<GenerationOverrides, "steps" | "cfg_scale"> = {
  steps: 9,
  cfg_scale: 1,
};

const withQwenSketchDefaults = (overrides?: GenerationOverrides | null): GenerationOverrides => ({
  ...(overrides || {}),
  steps: overrides?.steps ?? QWEN_SKETCH_DEFAULTS.steps,
  cfg_scale: overrides?.cfg_scale ?? QWEN_SKETCH_DEFAULTS.cfg_scale,
});

// IMPORTANT: keep in sync with backend WorldService.generate_location_sheet()
// Current backend kinds: exterior, interior, detail, map
const LOCATION_REFERENCE_SLOTS: { kind: string; label: string }[] = [
  { kind: "exterior", label: "Экстерьер" },
  { kind: "interior", label: "Интерьер" },
  { kind: "detail", label: "Деталь" },
  { kind: "map", label: "Карта" },
];

const LOCATION_AI_FIELDS: AIFieldSpec[] = [
  { key: "name", label: "Название", type: "string" },
  { key: "description", label: "Описание", type: "string" },
  { key: "visual_reference", label: "Визуальный референс", type: "string" },
  { key: "negative_prompt", label: "Негативный промпт", type: "string" },
  { key: "tags", label: "Теги", type: "array" },
  { key: "atmosphere_rules", label: "Правила атмосферы", type: "object" },
  { key: "location_metadata", label: "Метаданные локации", type: "object" },
];

const ARTIFACT_AI_FIELDS: AIFieldSpec[] = [
  { key: "name", label: "Название", type: "string" },
  { key: "description", label: "Описание", type: "string" },
  { key: "artifact_type", label: "Тип", type: "string" },
  { key: "legal_significance", label: "Юридическая значимость", type: "string" },
  { key: "status", label: "Статус", type: "string" },
  { key: "tags", label: "Теги", type: "array" },
  { key: "artifact_metadata", label: "Метаданные", type: "object" },
];

const DOCUMENT_AI_FIELDS: AIFieldSpec[] = [
  { key: "name", label: "Название", type: "string" },
  { key: "template_type", label: "Тип шаблона", type: "string" },
  { key: "template_body", label: "Содержимое шаблона", type: "string" },
  { key: "placeholders", label: "Заполнители", type: "object" },
  { key: "formatting", label: "Форматирование", type: "object" },
  { key: "tags", label: "Теги", type: "array" },
];

const STYLE_BIBLE_AI_FIELDS: AIFieldSpec[] = [
  { key: "tone", label: "Тон", type: "string" },
  { key: "narrative_rules", label: "Нарративные правила", type: "string" },
  { key: "glossary", label: "Глоссарий", type: "object" },
  { key: "constraints", label: "Ограничения", type: "object" },
  { key: "dialogue_format", label: "Формат диалога", type: "object" },
  { key: "document_format", label: "Формат документа", type: "object" },
  { key: "ui_theme", label: "Тема интерфейса", type: "object" },
];

const STYLE_PROFILE_AI_FIELDS: AIFieldSpec[] = [
  { key: "name", label: "Название профиля", type: "string" },
  { key: "description", label: "Описание", type: "string" },
  { key: "base_prompt", label: "Базовый промпт", type: "string" },
  { key: "negative_prompt", label: "Негативный промпт", type: "string" },
  { key: "width", label: "Ширина", type: "number" },
  { key: "height", label: "Высота", type: "number" },
  { key: "steps", label: "Шаги", type: "number" },
  { key: "cfg_scale", label: "CFG scale", type: "number" },
];

export default function WorldLibraryPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const isStudio = !projectId;
  const [developmentMode, setDevelopmentModeState] = useState<ProjectDevelopmentMode>(() =>
    getProjectDevelopmentMode(projectId),
  );
  const isCreativeMode = !isStudio && developmentMode === "creative";
  const requestedTab = searchParams.get("tab");
  const initialTab: TabId = isTabId(requestedTab) ? requestedTab : "locations";
  const tabDefs = useMemo(
    () => {
      if (isStudio) return BASE_TAB_DEFS.filter((tabItem) => tabItem.id !== "style");
      if (isCreativeMode) {
        return BASE_TAB_DEFS.filter((tabItem) => CREATIVE_MODE_TAB_IDS.includes(tabItem.id));
      }
      return BASE_TAB_DEFS;
    },
    [isCreativeMode, isStudio],
  );
  const [project, setProject] = useState<Project | null>(null);
  const [tab, setTab] = useState<TabId>(initialTab);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiLocationLoading, setAiLocationLoading] = useState(false);
  const [aiArtifactLoading, setAiArtifactLoading] = useState(false);
  const [aiFillModal, setAiFillModal] = useState<AIFillConfig | null>(null);
  const [importModal, setImportModal] = useState<{ type: ImportType; items: ImportItem[]; note?: string } | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [assetUploadBusy, setAssetUploadBusy] = useState<string | null>(null);

  const [lightbox, setLightbox] = useState<{ url: string; title?: string; subtitle?: string } | null>(null);

  // Generation defaults (Style Profiles)
  const [styleProfiles, setStyleProfiles] = useState<StyleProfile[]>([]);
  const [activeStyleProfileId, setActiveStyleProfileId] = useState<string>("");
  const [creatingStyleProfile, setCreatingStyleProfile] = useState(false);
  const [installingLegalStylePack, setInstallingLegalStylePack] = useState(false);
  const [styleProfileForm, setStyleProfileForm] = useState({
    name: "По умолчанию",
    description: "",
    base_prompt: "",
    negative_prompt: "",
    width: 1024,
    height: 768,
    steps: 34,
    cfg_scale: 6,
  });

  const [styleBible, setStyleBible] = useState<StyleBible | null>(null);
  const [styleForm, setStyleForm] = useState({
    tone: "",
    narrative_rules: "",
    glossary: "",
    constraints: "",
    dialogue_format: "",
    document_format: "",
    ui_theme: "",
  });

  const [locations, setLocations] = useState<Location[]>([]);
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null);
  const [locationGenerationOverrides, setLocationGenerationOverrides] = useState<GenerationOverrides>({
    negative_prompt: null,
    width: null,
    height: null,
    steps: null,
    cfg_scale: null,
    sampler: null,
    scheduler: null,
    model_id: null,
    vae_id: null,
    loras: [],
    seed: null,
    pipeline_profile_id: null,
    pipeline_profile_version: null,
  });
  const [locationForm, setLocationForm] = useState({
    name: "",
    description: "",
    visual_reference: "",
    negative_prompt: "",
    atmosphere_rules: "",
    tags: "",
    location_metadata: "",
    is_public: false,
  });

  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [artifactForm, setArtifactForm] = useState({
    name: "",
    description: "",
    artifact_type: "",
    legal_significance: "",
    status: "",
    tags: "",
    artifact_metadata: "",
    is_public: false,
  });

  const [documents, setDocuments] = useState<DocumentTemplate[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [documentForm, setDocumentForm] = useState({
    name: "",
    template_type: "",
    template_body: "",
    placeholders: "",
    formatting: "",
    tags: "",
    is_public: false,
  });

  const [characters, setCharacters] = useState<CharacterPreset[]>([]);
  const [selectedCharacterId, setSelectedCharacterId] = useState<string | null>(null);
  const [bulkCharacterRefsBusy, setBulkCharacterRefsBusy] = useState(false);
  const [bulkCharacterRefsProgress, setBulkCharacterRefsProgress] = useState<{ done: number; total: number } | null>(
    null,
  );

  const [jsonErrors, setJsonErrors] = useState<Record<string, string>>({});


  // --- Unified generation jobs (polling only /v1/generation/jobs/{id})
  const refreshLocation = useCallback(async (locationId: string) => {
    try {
      const fresh = await getLocation(locationId);
      setLocations((prev) => {
        const has = prev.some((l) => l.id === fresh.id);
        const next = has ? prev.map((l) => (l.id === fresh.id ? fresh : l)) : [...prev, fresh];
        next.sort((a, b) => a.name.localeCompare(b.name));
        return next;
      });
    } catch {
      // ignore refresh errors during polling
    }
  }, []);

  const refreshCharacterPreset = useCallback(async (presetId: string) => {
    try {
      const fresh = await getCharacterPreset(presetId);
      setCharacters((prev) => {
        const has = prev.some((c) => c.id === fresh.id);
        const next = has ? prev.map((c) => (c.id === fresh.id ? fresh : c)) : [...prev, fresh];
        next.sort((a, b) => a.name.localeCompare(b.name));
        return next;
      });
    } catch {
      // ignore refresh errors during polling
    }
  }, []);

  const refreshArtifact = useCallback(async (artifactId: string) => {
    try {
      const fresh = await getArtifact(artifactId);
      setArtifacts((prev) => {
        const has = prev.some((a) => a.id === fresh.id);
        const next = has ? prev.map((a) => (a.id === fresh.id ? fresh : a)) : [...prev, fresh];
        next.sort((a, b) => a.name.localeCompare(b.name));
        return next;
      });
    } catch {
      // ignore refresh errors during polling
    }
  }, []);

  const locationSketchJob = useAssetGeneration({
    taskType: "location_sketch",
    entityType: "location",
    projectId,
    styleProfileId: activeStyleProfileId || undefined,
    onEntityRefresh: refreshLocation,
  });

  const locationSheetJob = useAssetGeneration({
    taskType: "location_sheet",
    entityType: "location",
    projectId,
    styleProfileId: activeStyleProfileId || undefined,
    onEntityRefresh: refreshLocation,
  });

  const characterSketchJob = useAssetGeneration({
    taskType: "character_sketch",
    entityType: "character",
    projectId,
    styleProfileId: activeStyleProfileId || undefined,
    onEntityRefresh: refreshCharacterPreset,
  });

  const characterSheetJob = useAssetGeneration({
    taskType: "character_sheet",
    entityType: "character",
    projectId,
    styleProfileId: activeStyleProfileId || undefined,
    onEntityRefresh: refreshCharacterPreset,
  });

  const characterRenderJob = useAssetGeneration({
    taskType: "character_render",
    entityType: "character",
    projectId,
    styleProfileId: activeStyleProfileId || undefined,
    onEntityRefresh: refreshCharacterPreset,
  });

  const characterReferenceJob = useAssetGeneration({
    taskType: "character_reference",
    entityType: "character",
    projectId,
    styleProfileId: activeStyleProfileId || undefined,
    onEntityRefresh: refreshCharacterPreset,
  });

  const artifactSketchJob = useAssetGeneration({
    taskType: "artifact_sketch",
    entityType: "artifact",
    projectId,
    styleProfileId: activeStyleProfileId || undefined,
    onEntityRefresh: refreshArtifact,
  });

  const sketchingLocation = locationSketchJob.isGenerating;
  const sheetingLocation = locationSheetJob.isGenerating;
  const sketchingCharacter = characterSketchJob.isGenerating;
  const sheetingCharacter = characterSheetJob.isGenerating;
  const renderingCharacter = characterRenderJob.isGenerating;
  const referencingCharacter = characterReferenceJob.isGenerating;
  const sketchingArtifact = artifactSketchJob.isGenerating;

  const formatJobStatus = (status?: string) => {
    if (!status) return "Генерация";
    if (status === "queued") return "В очереди";
    if (status === "running") return "Рендеринг";
    if (status === "saving") return "Сохранение";
    return status;
  };

  const locationStatusFor = (id: string) => {
    if (locationSketchJob.isGenerating && locationSketchJob.job?.entity_id === id) {
      return formatJobStatus(locationSketchJob.job?.status);
    }
    if (locationSheetJob.isGenerating && locationSheetJob.job?.entity_id === id) {
      return formatJobStatus(locationSheetJob.job?.status);
    }
    return null;
  };

  const characterStatusFor = (id: string) => {
    if (characterSketchJob.isGenerating && characterSketchJob.job?.entity_id === id) {
      return formatJobStatus(characterSketchJob.job?.status);
    }
    if (characterSheetJob.isGenerating && characterSheetJob.job?.entity_id === id) {
      return formatJobStatus(characterSheetJob.job?.status);
    }
    if (characterReferenceJob.isGenerating && characterReferenceJob.job?.entity_id === id) {
      return formatJobStatus(characterReferenceJob.job?.status);
    }
    if (characterRenderJob.isGenerating && characterRenderJob.job?.entity_id === id) {
      return formatJobStatus(characterRenderJob.job?.status);
    }
    return null;
  };

  const artifactStatusFor = (id: string) => {
    if (artifactSketchJob.isGenerating && artifactSketchJob.job?.entity_id === id) {
      return formatJobStatus(artifactSketchJob.job?.status);
    }
    return null;
  };
  
  // Quick create modal state
  const [quickCreateType, setQuickCreateType] = useState<"character" | "location" | null>(null);
  const [wizardType, setWizardType] = useState<"character" | "location" | null>(null);

  useEffect(() => {
    void loadAll(projectId);
  }, [projectId]);

  useEffect(() => {
    if (tab === "characters") {
      void loadCharacters();
    }
  }, [tab, projectId]);

  useEffect(() => {
    if (isStudio && tab === "style") {
      setTab("locations");
    }
  }, [isStudio, tab]);

  useEffect(() => {
    setDevelopmentModeState(getProjectDevelopmentMode(projectId));
  }, [projectId]);

  useEffect(() => {
    if (!isCreativeMode) return;
    if (getGenerationEnvironment() === "local") {
      setGenerationEnvironment("comfy_api");
    }
  }, [isCreativeMode]);

  useEffect(() => {
    const requestedMode = searchParams.get("mode");
    if (!projectId || !requestedMode) return;
    if (requestedMode !== "creative" && requestedMode !== "standard") return;
    setDevelopmentModeState(requestedMode);
    setProjectDevelopmentMode(projectId, requestedMode);
  }, [projectId, searchParams]);

  useEffect(() => {
    const requested = searchParams.get("tab");
    if (!isTabId(requested)) return;
    const available = tabDefs.some((item) => item.id === requested);
    if (available && requested !== tab) {
      setTab(requested);
    }
  }, [searchParams, tab, tabDefs]);

  useEffect(() => {
    if (tabDefs.some((item) => item.id === tab)) return;
    setTab(tabDefs[0]?.id || "locations");
  }, [tab, tabDefs]);

  async function loadAll(projectIdValue?: string) {
    try {
      setLoading(true);
      if (!projectIdValue) {
        const [locs, arts, docs, chars] = await Promise.all([
          listStudioLocations().catch(() => []),
          listStudioArtifacts().catch(() => []),
          listStudioDocumentTemplates().catch(() => []),
          listCharacterPresets().catch(() => []),
        ]);
        setProject(null);
        setLocations(locs || []);
        setArtifacts(arts || []);
        setDocuments(docs || []);
        setCharacters(chars || []);
        setStyleBible(null);
        setStyleProfiles([]);
        setActiveStyleProfileId("");
        setStyleForm({
          tone: "",
          narrative_rules: "",
          glossary: "",
          constraints: "",
          dialogue_format: "",
          document_format: "",
          ui_theme: "",
        });
        return;
      }
      // Load each resource separately to handle individual failures gracefully
      const [projectData, style, locs, arts, docs, chars, profiles] = await Promise.all([
        getProject(projectIdValue),
        loadStyleBible(projectIdValue).catch(() => null),
        listLocations(projectIdValue).catch(() => []),
        listArtifacts(projectIdValue).catch(() => []),
        listDocumentTemplates(projectIdValue).catch(() => []),
        listProjectCharacters(projectIdValue).catch(() => []),
        listStyleProfiles(projectIdValue).catch(() => []),
      ]);
      setProject(projectData);
      setLocations(locs || []);
      setArtifacts(arts || []);
      setDocuments(docs || []);
      setCharacters(chars || []);
      setStyleBible(style);
      setStyleProfiles(profiles || []);
      const active = projectData.style_profile?.id || "";
      setActiveStyleProfileId(active);
      if (style) {
        setStyleForm({
          tone: style.tone || "",
          narrative_rules: style.narrative_rules || "",
          glossary: style.glossary ? JSON.stringify(style.glossary, null, 2) : "",
          constraints: style.constraints ? JSON.stringify(style.constraints, null, 2) : "",
          dialogue_format: style.dialogue_format ? JSON.stringify(style.dialogue_format, null, 2) : "",
          document_format: style.document_format ? JSON.stringify(style.document_format, null, 2) : "",
          ui_theme: style.ui_theme ? JSON.stringify(style.ui_theme, null, 2) : "",
        });
      }
    } catch (err: any) {
      setError(err?.message || "Не удалось загрузить библиотеку мира.");
    } finally {
      setLoading(false);
    }
  }

  async function loadCharacters() {
    try {
      const data = projectId ? await listProjectCharacters(projectId) : await listCharacterPresets();
      setCharacters(data);
    } catch (err: any) {
      setError(err?.message || "Не удалось загрузить персонажей.");
    }
  }

  async function loadStyleBible(projectIdValue: string): Promise<StyleBible | null> {
    try {
      return await getStyleBible(projectIdValue);
    } catch (err: any) {
      // 404 means no style bible exists yet - that's OK
      if (err?.response?.status === 404 || err?.message?.includes("404") || err?.message?.includes("not found")) {
        return null;
      }
      // Don't throw for style bible errors - it's optional
      console.warn("Failed to load style bible:", err?.message);
      return null;
    }
  }

  function parseJsonField(value: string, key: string): Record<string, unknown> | unknown[] | null | undefined {
    if (!value.trim()) {
      setJsonErrors((prev) => ({ ...prev, [key]: "" }));
      return null;
    }
    try {
      const parsed = JSON.parse(value);
      setJsonErrors((prev) => ({ ...prev, [key]: "" }));
      return parsed;
    } catch (err) {
      setJsonErrors((prev) => ({ ...prev, [key]: "Неверный JSON" }));
      return undefined;
    }
  }

  const parseJsonLoose = (value: string): Record<string, unknown> | unknown[] | null => {
    if (!value.trim()) return null;
    try {
      return JSON.parse(value);
    } catch {
      return null;
    }
  };

  const getJsonCurrent = (value: string): unknown => {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const parsed = parseJsonLoose(value);
    return parsed ?? trimmed;
  };

  const toCsv = (value: unknown): string => {
    if (Array.isArray(value)) {
      return value.map((item) => String(item).trim()).filter(Boolean).join(", ");
    }
    if (typeof value === "string") return value;
    return value ? String(value) : "";
  };

  const toJsonString = (value: unknown): string => {
    if (value === null || value === undefined) return "";
    if (typeof value === "string") return value;
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  };

  const toStringValue = (value: unknown): string | null =>
    typeof value === "string" ? value : value === null || value === undefined ? null : String(value);

  const openLightboxAsset = useCallback(
    (assetPath: string | null | undefined, title?: string, subtitle?: string) => {
      const url = getAssetUrl(assetPath);
      if (!url) return;
      setLightbox({ url, title, subtitle });
    },
    [],
  );

  const toNumberValue = (value: unknown): number | null =>
    typeof value === "number" && Number.isFinite(value) ? value : null;

  const getProfileString = (profile: unknown, path: string[]): string => {
    let current: unknown = profile;
    for (const key of path) {
      if (!current || typeof current !== "object") return "";
      current = (current as Record<string, unknown>)[key];
    }
    return typeof current === "string" ? current : "";
  };

  const confirmUnsafeOverwrite = (label: string, name?: string, sourceVersion?: number | null) => {
    const target = name ? ` "${name}"` : "";
    const version = sourceVersion ? ` (studio v${sourceVersion})` : "";
    return window.confirm(
      `Этот ${label}${target}${version} импортирован из студии и зафиксирован по версии. ` +
        "Обновление перезапишет снимок и нарушит синхронизацию. Продолжить?",
    );
  };

  async function openImportModal(type: ImportType) {
    if (!projectId) return;
    try {
      setImportLoading(true);
      let items: ImportItem[] = [];
      let note: string | undefined;
      if (type === "character") {
        const data = await listCharacterPresets();
        const imported = new Set(
          characters.map((character) => character.source_preset_id).filter(Boolean) as string[],
        );
        note =
          "Recommended before import: portrait/profile/full body views plus 3 pose renders. Wardrobe details help keep outfits consistent.";
        items = data
          .filter((character) => !imported.has(character.id))
          .map((character) => {
            const refKinds = new Set(
              (character.reference_images || [])
                .map((ref) => ref?.kind)
                .filter((kind): kind is string => typeof kind === "string"),
            );
            const missingViews = VIEW_REFERENCE_KINDS.filter((kind) => !refKinds.has(kind));
            const missingPoses = POSE_REFERENCE_KINDS.filter((kind) => !refKinds.has(kind));
            const badges: string[] = [];
            if (missingViews.length > 0) badges.push("Недостающие ракурсы");
            if (missingPoses.length > 0) badges.push("Недостающие позы");
            if (badges.length === 0) badges.push("Набор референсов готов");

            const outfit = getProfileString(character.appearance_profile, ["visual_profile", "style", "outfit"]);
            const palette = getProfileString(character.appearance_profile, ["visual_profile", "style", "palette"]);
            const materials = getProfileString(character.appearance_profile, ["visual_profile", "style", "materials"]);
            const detailParts = [];
            if (outfit) detailParts.push(`Outfit: ${outfit}`);
            if (palette) detailParts.push(`Palette: ${palette}`);
            if (materials) detailParts.push(`Materials: ${materials}`);

            return {
              id: character.id,
              name: character.name,
              description: character.description || null,
              detail: detailParts.length ? detailParts.join(" · ") : null,
              badges,
            };
          });
      } else if (type === "location") {
        const data = await listStudioLocations();
        const imported = new Set(
          locations.map((location) => location.source_location_id).filter(Boolean) as string[],
        );
        items = data
          .filter((location) => !imported.has(location.id))
          .map((location) => ({
            id: location.id,
            name: location.name,
            description: location.description || location.visual_reference || null,
          }));
      } else if (type === "artifact") {
        const data = await listStudioArtifacts();
        const imported = new Set(
          artifacts.map((artifact) => artifact.source_artifact_id).filter(Boolean) as string[],
        );
        items = data
          .filter((artifact) => !imported.has(artifact.id))
          .map((artifact) => ({
            id: artifact.id,
            name: artifact.name,
            description: artifact.description || artifact.artifact_type || null,
          }));
      } else if (type === "document") {
        const data = await listStudioDocumentTemplates();
        const imported = new Set(
          documents.map((doc) => doc.source_template_id).filter(Boolean) as string[],
        );
        items = data
          .filter((doc) => !imported.has(doc.id))
          .map((doc) => ({
            id: doc.id,
            name: doc.name,
            description: doc.template_type || null,
          }));
      }
      setImportModal({ type, items, note });
    } catch (err: any) {
      setError(err?.message || "Не удалось загрузить ассеты студии.");
    } finally {
      setImportLoading(false);
    }
  }

  async function handleImportAsset(assetId: string) {
    if (!projectId || !importModal) return;
    try {
      if (importModal.type === "character") {
        const created = await importCharacterPreset(projectId, assetId);
        setCharacters((prev) => [created, ...prev]);
        setSelectedCharacterId(created.id);
      } else if (importModal.type === "location") {
        const created = await importLocation(projectId, assetId);
        setLocations((prev) => [created, ...prev]);
        setSelectedLocationId(created.id);
      } else if (importModal.type === "artifact") {
        const created = await importArtifact(projectId, assetId);
        setArtifacts((prev) => [created, ...prev]);
        setSelectedArtifactId(created.id);
      } else if (importModal.type === "document") {
        const created = await importDocumentTemplate(projectId, assetId);
        setDocuments((prev) => [created, ...prev]);
        setSelectedDocumentId(created.id);
      }
    } catch (err: any) {
      setError(err?.message || "Не удалось импортировать ассет.");
    }
  }

  async function handleStyleSave() {
    if (!projectId) return;
    const glossary = parseJsonField(styleForm.glossary, "glossary");
    const constraints = parseJsonField(styleForm.constraints, "constraints");
    const dialogue = parseJsonField(styleForm.dialogue_format, "dialogue_format");
    const docFormat = parseJsonField(styleForm.document_format, "document_format");
    const theme = parseJsonField(styleForm.ui_theme, "ui_theme");
    if ([glossary, constraints, dialogue, docFormat, theme].some((v) => v === undefined)) return;

    try {
      setSaving(true);
      const updated = await upsertStyleBible(projectId, {
        tone: styleForm.tone || null,
        narrative_rules: styleForm.narrative_rules || null,
        glossary: glossary as Record<string, unknown> | null,
        constraints: constraints as unknown[] | null,
        dialogue_format: dialogue as Record<string, unknown> | null,
        document_format: docFormat as Record<string, unknown> | null,
        ui_theme: theme as Record<string, unknown> | null,
      });
      setStyleBible(updated);
    } catch (err: any) {
      setError(err?.message || "Не удалось сохранить библию стиля.");
    } finally {
      setSaving(false);
    }
  }

  async function handleApplyStyleProfile(styleId: string) {
    if (!projectId) return;
    try {
      setCreatingStyleProfile(true);
      const updated = await updateProject(projectId, { style_profile_id: styleId || null });
      setProject(updated);
      setActiveStyleProfileId(updated.style_profile?.id || "");
    } catch (err: any) {
      setError(err?.message || "Не удалось обновить параметры генерации.");
    } finally {
      setCreatingStyleProfile(false);
    }
  }

  async function handleCreateGenerationProfile() {
    if (!projectId) return;
    if (!styleProfileForm.name.trim()) {
      setError("Нужно указать название профиля стиля.");
      return;
    }
    try {
      setCreatingStyleProfile(true);
      const created = await createStyleProfile({
        project_id: projectId,
        name: styleProfileForm.name.trim(),
        description: styleProfileForm.description || undefined,
        base_prompt: styleProfileForm.base_prompt || undefined,
        negative_prompt: styleProfileForm.negative_prompt || undefined,
        cfg_scale: Number.isFinite(styleProfileForm.cfg_scale) ? styleProfileForm.cfg_scale : undefined,
        steps: Number.isFinite(styleProfileForm.steps) ? styleProfileForm.steps : undefined,
        resolution: {
          width: Number(styleProfileForm.width) || 1024,
          height: Number(styleProfileForm.height) || 768,
        },
      });
      const profiles = await listStyleProfiles(projectId).catch(() => []);
      setStyleProfiles(profiles);
      const updated = await updateProject(projectId, { style_profile_id: created.id });
      setProject(updated);
      setActiveStyleProfileId(updated.style_profile?.id || created.id);
      setStyleProfileForm((prev) => ({ ...prev, name: "По умолчанию" }));
    } catch (err: any) {
      setError(err?.message || "Не удалось создать профиль стиля.");
    } finally {
      setCreatingStyleProfile(false);
    }
  }

  async function handleInstallLegalStylePack() {
    if (!projectId) return;
    try {
      setInstallingLegalStylePack(true);
      await bootstrapLegalStyleProfiles(projectId, false);
      const profiles = await listStyleProfiles(projectId).catch(() => []);
      setStyleProfiles(profiles);
      // Auto-select the recommended one if current selection is empty.
      if (!activeStyleProfileId) {
        const recommended = profiles.find((p) => (p as any)?.style_metadata?.recommended === true);
        if (recommended) {
          setActiveStyleProfileId(recommended.id);
        }
      }
    } catch (err: any) {
      setError(err?.message || "Не удалось установить юридический пакет стилей.");
    } finally {
      setInstallingLegalStylePack(false);
    }
  }

  async function handleLocationSheet() {
    if (!selectedLocationId) return;
    try {
      await locationSheetJob.start({
        entityId: selectedLocationId,
        overrides: locationGenerationOverrides || undefined,
      });
    } catch (err: any) {
      setError(err?.message || "Не удалось поставить в очередь генерацию набора референсов локации.");
    }
  }

  async function handleLocationSave() {
    if (!locationForm.name.trim()) return;
    const meta = parseJsonField(locationForm.location_metadata, "location_metadata");
    const atmosphere = parseJsonField(locationForm.atmosphere_rules, "atmosphere_rules");
    if ([meta, atmosphere].some((value) => value === undefined)) return;
    try {
      setSaving(true);
      const payload = {
        name: locationForm.name.trim(),
        description: locationForm.description || null,
        visual_reference: locationForm.visual_reference || null,
        negative_prompt: locationForm.negative_prompt || null,
        atmosphere_rules: atmosphere as Record<string, unknown> | null,
        tags: locationForm.tags ? locationForm.tags.split(",").map((tag) => tag.trim()).filter(Boolean) : null,
        location_metadata: meta as Record<string, unknown> | null,
        ...(isStudio ? { is_public: locationForm.is_public } : {}),
      };
      let updated: Location;
      if (selectedLocationId) {
        if (isStudio) {
          updated = await updateStudioLocation(selectedLocationId, payload);
        } else {
          const needsUnsafe = Boolean(selectedLocation?.source_location_id);
          if (needsUnsafe && !confirmUnsafeOverwrite("location", selectedLocation?.name, selectedLocation?.source_version)) {
            return;
          }
          updated = await updateLocation(selectedLocationId, payload, needsUnsafe ? { unsafe: true } : undefined);
        }
        setLocations((prev) => prev.map((loc) => (loc.id === updated.id ? updated : loc)));
      } else {
        if (isStudio) {
          updated = await createStudioLocation(payload);
        } else if (projectId) {
          updated = await createLocation(projectId, payload);
        } else {
          return;
        }
        setLocations((prev) => [updated, ...prev]);
      }
      setSelectedLocationId(updated.id);
    } catch (err: any) {
      setError(err?.message || "Не удалось сохранить локацию.");
    } finally {
      setSaving(false);
    }
  }

  async function handleGenerateLocationDescription() {
    if (!locationForm.name.trim()) return;
    try {
      setAiLocationLoading(true);
      const contextParts = [
        locationForm.visual_reference ? `visual reference: ${locationForm.visual_reference}` : null,
        locationForm.tags ? `tags: ${locationForm.tags}` : null,
        locationForm.atmosphere_rules ? `atmosphere rules: ${locationForm.atmosphere_rules}` : null,
        locationForm.negative_prompt ? `negative prompt: ${locationForm.negative_prompt}` : null,
      ].filter(Boolean);
      const response = await generateDescription({
        entity_type: "location",
        name: locationForm.name.trim(),
        context: contextParts.join("\n"),
      });
      setLocationForm((prev) => ({ ...prev, description: response.description }));
    } catch (err: any) {
      setError(err?.message || "Не удалось сгенерировать описание локации.");
    } finally {
      setAiLocationLoading(false);
    }
  }

  async function handleLocationDelete(locationId: string) {
    try {
      if (isStudio) {
        await deleteStudioLocation(locationId);
      } else {
        await deleteLocation(locationId);
      }
      setLocations((prev) => prev.filter((loc) => loc.id !== locationId));
      if (selectedLocationId === locationId) {
        setSelectedLocationId(null);
        setLocationForm({
          name: "",
          description: "",
          visual_reference: "",
          negative_prompt: "",
          atmosphere_rules: "",
          tags: "",
          location_metadata: "",
          is_public: false,
        });
      }
    } catch (err: any) {
      setError(err?.message || "Не удалось удалить локацию.");
    }
  }

  async function handleLocationSketch() {
    if (!selectedLocationId) return;
    try {
      await locationSketchJob.start({
        entityId: selectedLocationId,
        overrides: withQwenSketchDefaults(locationGenerationOverrides),
      });
    } catch (err: any) {
      setError(err?.message || "Не удалось поставить в очередь генерацию скетча локации.");
    }
  }

  async function handleLocationPreviewUpload(file: File) {
    if (!selectedLocationId) return;
    try {
      setAssetUploadBusy("location-preview");
      const needsUnsafe = !isStudio && Boolean(selectedLocation?.source_location_id);
      if (
        needsUnsafe &&
        !confirmUnsafeOverwrite("location", selectedLocation?.name, selectedLocation?.source_version)
      ) {
        return;
      }
      const updated = await uploadLocationPreview(selectedLocationId, file, needsUnsafe ? { unsafe: true } : undefined);
      setLocations((prev) => prev.map((location) => (location.id === updated.id ? updated : location)));
    } catch (err: any) {
      setError(err?.message || "Не удалось загрузить изображение локации.");
    } finally {
      setAssetUploadBusy(null);
    }
  }

  async function handleLocationReferenceUpload(kind: string, file: File) {
    if (!selectedLocationId) return;
    try {
      setAssetUploadBusy(`location-ref:${kind}`);
      const needsUnsafe = !isStudio && Boolean(selectedLocation?.source_location_id);
      if (
        needsUnsafe &&
        !confirmUnsafeOverwrite("location", selectedLocation?.name, selectedLocation?.source_version)
      ) {
        return;
      }
      const updated = await uploadLocationReference(
        selectedLocationId,
        kind,
        file,
        needsUnsafe
          ? { unsafe: true, setAsPreview: !selectedLocation?.preview_image_url }
          : { setAsPreview: !selectedLocation?.preview_image_url },
      );
      setLocations((prev) => prev.map((location) => (location.id === updated.id ? updated : location)));
    } catch (err: any) {
      setError(err?.message || "Не удалось загрузить референс локации.");
    } finally {
      setAssetUploadBusy(null);
    }
  }

  async function handleArtifactSave() {
    if (!artifactForm.name.trim()) return;
    const meta = parseJsonField(artifactForm.artifact_metadata, "artifact_metadata");
    if (meta === undefined) return;
    try {
      setSaving(true);
      const payload = {
        name: artifactForm.name.trim(),
        description: artifactForm.description || null,
        artifact_type: artifactForm.artifact_type || null,
        legal_significance: artifactForm.legal_significance || null,
        status: artifactForm.status || null,
        tags: artifactForm.tags ? artifactForm.tags.split(",").map((tag) => tag.trim()).filter(Boolean) : null,
        artifact_metadata: meta as Record<string, unknown> | null,
        ...(isStudio ? { is_public: artifactForm.is_public } : {}),
      };
      let updated: Artifact;
      if (selectedArtifactId) {
        if (isStudio) {
          updated = await updateStudioArtifact(selectedArtifactId, payload);
        } else {
          const needsUnsafe = Boolean(selectedArtifact?.source_artifact_id);
          if (
            needsUnsafe &&
            !confirmUnsafeOverwrite("artifact", selectedArtifact?.name, selectedArtifact?.source_version)
          ) {
            return;
          }
          updated = await updateArtifact(selectedArtifactId, payload, needsUnsafe ? { unsafe: true } : undefined);
        }
        setArtifacts((prev) => prev.map((art) => (art.id === updated.id ? updated : art)));
      } else {
        if (isStudio) {
          updated = await createStudioArtifact(payload);
        } else if (projectId) {
          updated = await createArtifact(projectId, payload);
        } else {
          return;
        }
        setArtifacts((prev) => [updated, ...prev]);
      }
      setSelectedArtifactId(updated.id);
    } catch (err: any) {
      setError(err?.message || "Не удалось сохранить артефакт.");
    } finally {
      setSaving(false);
    }
  }

  async function handleGenerateArtifactDescription() {
    if (!artifactForm.name.trim()) return;
    try {
      setAiArtifactLoading(true);
      const contextParts = [
        artifactForm.artifact_type ? `type: ${artifactForm.artifact_type}` : null,
        artifactForm.legal_significance ? `legal significance: ${artifactForm.legal_significance}` : null,
        artifactForm.status ? `status: ${artifactForm.status}` : null,
        artifactForm.tags ? `tags: ${artifactForm.tags}` : null,
      ].filter(Boolean);
      const response = await generateDescription({
        entity_type: "artifact",
        name: artifactForm.name.trim(),
        context: contextParts.join("\n"),
      });
      setArtifactForm((prev) => ({ ...prev, description: response.description }));
    } catch (err: any) {
      setError(err?.message || "Не удалось сгенерировать описание артефакта.");
    } finally {
      setAiArtifactLoading(false);
    }
  }

  function openLocationAIFill() {
    const contextParts = [
      project?.name ? `project: ${project.name}` : null,
      locationForm.name ? `name: ${locationForm.name}` : null,
      locationForm.visual_reference ? `visual reference: ${locationForm.visual_reference}` : null,
      locationForm.tags ? `tags: ${locationForm.tags}` : null,
    ].filter(Boolean);
    setAiFillModal({
      title: "Форма локации",
      formType: "location",
      fields: LOCATION_AI_FIELDS,
      currentValues: {
        name: locationForm.name,
        description: locationForm.description,
        visual_reference: locationForm.visual_reference,
        negative_prompt: locationForm.negative_prompt,
        tags: locationForm.tags ? locationForm.tags.split(",").map((tag) => tag.trim()).filter(Boolean) : [],
        atmosphere_rules: getJsonCurrent(locationForm.atmosphere_rules),
        location_metadata: getJsonCurrent(locationForm.location_metadata),
      },
      context: contextParts.join("\n"),
      onApply: (values) => {
        setLocationForm((prev) => ({
          ...prev,
          name: toStringValue(values.name) ?? prev.name,
          description: toStringValue(values.description) ?? prev.description,
          visual_reference: toStringValue(values.visual_reference) ?? prev.visual_reference,
          negative_prompt: toStringValue(values.negative_prompt) ?? prev.negative_prompt,
          tags: toCsv(values.tags),
          atmosphere_rules: toJsonString(values.atmosphere_rules),
          location_metadata: toJsonString(values.location_metadata),
        }));
      },
    });
  }

  function openArtifactAIFill() {
    const contextParts = [
      project?.name ? `project: ${project.name}` : null,
      artifactForm.name ? `name: ${artifactForm.name}` : null,
      artifactForm.artifact_type ? `type: ${artifactForm.artifact_type}` : null,
      artifactForm.legal_significance ? `legal significance: ${artifactForm.legal_significance}` : null,
    ].filter(Boolean);
    setAiFillModal({
      title: "Форма артефакта",
      formType: "artifact",
      fields: ARTIFACT_AI_FIELDS,
      currentValues: {
        name: artifactForm.name,
        description: artifactForm.description,
        artifact_type: artifactForm.artifact_type,
        legal_significance: artifactForm.legal_significance,
        status: artifactForm.status,
        tags: artifactForm.tags ? artifactForm.tags.split(",").map((tag) => tag.trim()).filter(Boolean) : [],
        artifact_metadata: getJsonCurrent(artifactForm.artifact_metadata),
      },
      context: contextParts.join("\n"),
      onApply: (values) => {
        setArtifactForm((prev) => ({
          ...prev,
          name: toStringValue(values.name) ?? prev.name,
          description: toStringValue(values.description) ?? prev.description,
          artifact_type: toStringValue(values.artifact_type) ?? prev.artifact_type,
          legal_significance: toStringValue(values.legal_significance) ?? prev.legal_significance,
          status: toStringValue(values.status) ?? prev.status,
          tags: toCsv(values.tags),
          artifact_metadata: toJsonString(values.artifact_metadata),
        }));
      },
    });
  }

  function openDocumentAIFill() {
    const contextParts = [
      project?.name ? `project: ${project.name}` : null,
      documentForm.name ? `name: ${documentForm.name}` : null,
      documentForm.template_type ? `template type: ${documentForm.template_type}` : null,
    ].filter(Boolean);
    setAiFillModal({
      title: "Шаблон документа",
      formType: "document_template",
      fields: DOCUMENT_AI_FIELDS,
      currentValues: {
        name: documentForm.name,
        template_type: documentForm.template_type,
        template_body: documentForm.template_body,
        placeholders: getJsonCurrent(documentForm.placeholders),
        formatting: getJsonCurrent(documentForm.formatting),
        tags: documentForm.tags ? documentForm.tags.split(",").map((tag) => tag.trim()).filter(Boolean) : [],
      },
      context: contextParts.join("\n"),
      onApply: (values) => {
        setDocumentForm((prev) => ({
          ...prev,
          name: toStringValue(values.name) ?? prev.name,
          template_type: toStringValue(values.template_type) ?? prev.template_type,
          template_body: toStringValue(values.template_body) ?? prev.template_body,
          placeholders: toJsonString(values.placeholders),
          formatting: toJsonString(values.formatting),
          tags: toCsv(values.tags),
        }));
      },
    });
  }

  function openStyleBibleAIFill() {
    const contextParts = [
      project?.name ? `project: ${project.name}` : null,
      styleForm.tone ? `tone: ${styleForm.tone}` : null,
      styleForm.narrative_rules ? `narrative rules: ${styleForm.narrative_rules}` : null,
    ].filter(Boolean);
    setAiFillModal({
      title: "Библия стиля",
      formType: "style_bible",
      fields: STYLE_BIBLE_AI_FIELDS,
      currentValues: {
        tone: styleForm.tone,
        narrative_rules: styleForm.narrative_rules,
        glossary: getJsonCurrent(styleForm.glossary),
        constraints: getJsonCurrent(styleForm.constraints),
        dialogue_format: getJsonCurrent(styleForm.dialogue_format),
        document_format: getJsonCurrent(styleForm.document_format),
        ui_theme: getJsonCurrent(styleForm.ui_theme),
      },
      context: contextParts.join("\n"),
      onApply: (values) => {
        setStyleForm((prev) => ({
          ...prev,
          tone: toStringValue(values.tone) ?? prev.tone,
          narrative_rules: toStringValue(values.narrative_rules) ?? prev.narrative_rules,
          glossary: toJsonString(values.glossary),
          constraints: toJsonString(values.constraints),
          dialogue_format: toJsonString(values.dialogue_format),
          document_format: toJsonString(values.document_format),
          ui_theme: toJsonString(values.ui_theme),
        }));
      },
    });
  }

  function openStyleProfileAIFill() {
    const contextParts = [
      project?.name ? `project: ${project.name}` : null,
      styleProfileForm.name ? `profile name: ${styleProfileForm.name}` : null,
      styleProfileForm.base_prompt ? `base prompt: ${styleProfileForm.base_prompt}` : null,
    ].filter(Boolean);
    setAiFillModal({
      title: "Профиль стиля",
      formType: "style_profile",
      fields: STYLE_PROFILE_AI_FIELDS,
      currentValues: {
        name: styleProfileForm.name,
        description: styleProfileForm.description,
        base_prompt: styleProfileForm.base_prompt,
        negative_prompt: styleProfileForm.negative_prompt,
        width: styleProfileForm.width,
        height: styleProfileForm.height,
        steps: styleProfileForm.steps,
        cfg_scale: styleProfileForm.cfg_scale,
      },
      context: contextParts.join("\n"),
      onApply: (values) => {
        setStyleProfileForm((prev) => ({
          ...prev,
          name: toStringValue(values.name) ?? prev.name,
          description: toStringValue(values.description) ?? prev.description,
          base_prompt: toStringValue(values.base_prompt) ?? prev.base_prompt,
          negative_prompt: toStringValue(values.negative_prompt) ?? prev.negative_prompt,
          width: toNumberValue(values.width) ?? prev.width,
          height: toNumberValue(values.height) ?? prev.height,
          steps: toNumberValue(values.steps) ?? prev.steps,
          cfg_scale: toNumberValue(values.cfg_scale) ?? prev.cfg_scale,
        }));
      },
    });
  }

  async function handleArtifactDelete(artifactId: string) {
    try {
      if (isStudio) {
        await deleteStudioArtifact(artifactId);
      } else {
        await deleteArtifact(artifactId);
      }
      setArtifacts((prev) => prev.filter((item) => item.id !== artifactId));
      if (selectedArtifactId === artifactId) {
        setSelectedArtifactId(null);
        setArtifactForm({
          name: "",
          description: "",
          artifact_type: "",
          legal_significance: "",
          status: "",
          tags: "",
          artifact_metadata: "",
          is_public: false,
        });
      }
    } catch (err: any) {
      setError(err?.message || "Не удалось удалить артефакт.");
    }
  }

  async function handleArtifactSketch() {
    if (!selectedArtifactId) return;
    try {
      await artifactSketchJob.start({
        entityId: selectedArtifactId,
        overrides: withQwenSketchDefaults(null),
      });
    } catch (err: any) {
      setError(err?.message || "Не удалось поставить в очередь генерацию скетча артефакта.");
    }
  }

  async function handleArtifactPreviewUpload(file: File) {
    if (!selectedArtifactId) return;
    try {
      setAssetUploadBusy("artifact-preview");
      const needsUnsafe = !isStudio && Boolean(selectedArtifact?.source_artifact_id);
      if (
        needsUnsafe &&
        !confirmUnsafeOverwrite("artifact", selectedArtifact?.name, selectedArtifact?.source_version)
      ) {
        return;
      }
      const updated = await uploadArtifactPreview(selectedArtifactId, file, needsUnsafe ? { unsafe: true } : undefined);
      setArtifacts((prev) => prev.map((artifact) => (artifact.id === updated.id ? updated : artifact)));
    } catch (err: any) {
      setError(err?.message || "Не удалось загрузить изображение артефакта.");
    } finally {
      setAssetUploadBusy(null);
    }
  }

  async function handleDocumentSave() {
    if (!documentForm.name.trim()) return;
    const placeholders = parseJsonField(documentForm.placeholders, "placeholders");
    const formatting = parseJsonField(documentForm.formatting, "formatting");
    if ([placeholders, formatting].some((v) => v === undefined)) return;
    try {
      setSaving(true);
      const payload = {
        name: documentForm.name.trim(),
        template_type: documentForm.template_type || null,
        template_body: documentForm.template_body || null,
        placeholders: placeholders as Record<string, unknown> | null,
        formatting: formatting as Record<string, unknown> | null,
        tags: documentForm.tags ? documentForm.tags.split(",").map((tag) => tag.trim()).filter(Boolean) : null,
        ...(isStudio ? { is_public: documentForm.is_public } : {}),
      };
      let updated: DocumentTemplate;
      if (selectedDocumentId) {
        if (isStudio) {
          updated = await updateStudioDocumentTemplate(selectedDocumentId, payload);
        } else {
          const needsUnsafe = Boolean(selectedDocument?.source_template_id);
          if (
            needsUnsafe &&
            !confirmUnsafeOverwrite("document", selectedDocument?.name, selectedDocument?.source_version)
          ) {
            return;
          }
          updated = await updateDocumentTemplate(selectedDocumentId, payload, needsUnsafe ? { unsafe: true } : undefined);
        }
        setDocuments((prev) => prev.map((doc) => (doc.id === updated.id ? updated : doc)));
      } else {
        if (isStudio) {
          updated = await createStudioDocumentTemplate(payload);
        } else if (projectId) {
          updated = await createDocumentTemplate(projectId, payload);
        } else {
          return;
        }
        setDocuments((prev) => [updated, ...prev]);
      }
      setSelectedDocumentId(updated.id);
    } catch (err: any) {
      setError(err?.message || "Не удалось сохранить шаблон документа.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDocumentDelete(templateId: string) {
    try {
      if (isStudio) {
        await deleteStudioDocumentTemplate(templateId);
      } else {
        await deleteDocumentTemplate(templateId);
      }
      setDocuments((prev) => prev.filter((doc) => doc.id !== templateId));
      if (selectedDocumentId === templateId) {
        setSelectedDocumentId(null);
        setDocumentForm({
          name: "",
          template_type: "",
          template_body: "",
          placeholders: "",
          formatting: "",
          tags: "",
          is_public: false,
        });
      }
    } catch (err: any) {
      setError(err?.message || "Не удалось удалить шаблон документа.");
    }
  }

  async function handleCharacterSheet(
    characterId?: string,
    options?: { overrides?: GenerationOverrides; kinds?: string[] },
  ) {
    const targetId = characterId || selectedCharacterId;
    if (!targetId) return;
    try {
      await characterSheetJob.start({
        entityId: targetId,
        overrides: options?.overrides || undefined,
        payload: options?.kinds ? { kinds: options.kinds } : undefined,
      });
    } catch (err: any) {
      setError(err?.message || "Не удалось поставить в очередь генерацию ассета персонажа.");
    }
  }

  async function createCharacterInCurrentLibrary(payload: Partial<CharacterPreset>) {
    if (isStudio) {
      return createCharacterPreset(payload);
    }
    if (!projectId || !isCreativeMode) {
      throw new Error("Создайте персонажей в студии и импортируйте их в проект.");
    }
    const created = await createCharacterPreset(payload);
    return importCharacterPreset(projectId, created.id);
  }

  async function handleCharacterStudioSave(payload: Partial<CharacterPreset>, characterId?: string) {
    try {
      setSaving(true);
      let updated: CharacterPreset;
      if (characterId) {
        if (isStudio) {
          updated = await updateCharacterPreset(characterId, payload);
        } else {
          const target = characters.find((character) => character.id === characterId);
          const needsUnsafe = Boolean(target?.source_preset_id);
          if (
            needsUnsafe &&
            !confirmUnsafeOverwrite("character", target?.name, target?.source_version)
          ) {
            return;
          }
          updated = await updateCharacterPreset(characterId, payload, needsUnsafe ? { unsafe: true } : undefined);
        }
        setCharacters((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      } else {
        updated = await createCharacterInCurrentLibrary(payload);
        setCharacters((prev) => [updated, ...prev]);
      }
      setSelectedCharacterId(updated.id);
    } catch (err: any) {
      setError(err?.message || "Не удалось сохранить персонажа.");
    } finally {
      setSaving(false);
    }
  }

  async function handleCharacterPatch(characterId: string, payload: Partial<CharacterPreset>) {
    try {
      if (isStudio) {
        const updated = await updateCharacterPreset(characterId, payload);
        setCharacters((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
        return;
      }
      const target = characters.find((character) => character.id === characterId);
      const needsUnsafe = Boolean(target?.source_preset_id);
      if (
        needsUnsafe &&
        !confirmUnsafeOverwrite("character", target?.name, target?.source_version)
      ) {
        return;
      }
      const updated = await updateCharacterPreset(characterId, payload, needsUnsafe ? { unsafe: true } : undefined);
      setCharacters((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
    } catch (err: any) {
      setError(err?.message || "Не удалось обновить персонажа.");
    }
  }

  async function handleCharacterRender(characterId: string, payload: CharacterRenderPayload) {
    try {
      await characterRenderJob.start({
        entityId: characterId,
        payload,
      });
    } catch (err: any) {
      setError(err?.message || "Не удалось поставить в очередь рендер персонажа.");
    }
  }

  async function handleCharacterReference(
    characterId: string,
    kind: string,
    overrides?: GenerationOverrides,
  ) {
    try {
      await characterReferenceJob.start({
        entityId: characterId,
        kind,
        overrides: overrides || undefined,
      });
    } catch (err: any) {
      setError(err?.message || "Не удалось поставить в очередь референс персонажа.");
    }
  }

  async function handleCharacterDelete(characterId: string) {
    try {
      await deleteCharacterPreset(characterId);
      setCharacters((prev) => prev.filter((c) => c.id !== characterId));
      if (selectedCharacterId === characterId) {
        setSelectedCharacterId(null);
      }
    } catch (err: any) {
      setError(err?.message || "Не удалось удалить персонажа.");
    }
  }

  async function handleCharacterSketch(characterId?: string) {
    const targetId = characterId || selectedCharacterId;
    if (!targetId) return;
    try {
      await characterSketchJob.start({
        entityId: targetId,
        overrides: withQwenSketchDefaults(null),
      });
    } catch (err: any) {
      setError(err?.message || "Не удалось поставить в очередь генерацию скетча персонажа.");
    }
  }

  async function handleCharacterReferenceUpload(
    characterId: string,
    kind: string,
    file: File,
    options?: { setAsPreview?: boolean },
  ) {
    try {
      setAssetUploadBusy(`character-ref:${kind}`);
      const target = characters.find((character) => character.id === characterId);
      const needsUnsafe = !isStudio && Boolean(target?.source_preset_id);
      if (
        needsUnsafe &&
        !confirmUnsafeOverwrite("character", target?.name, target?.source_version)
      ) {
        return;
      }
      const updated = await uploadCharacterReference(
        characterId,
        kind,
        file,
        needsUnsafe ? { unsafe: true, setAsPreview: options?.setAsPreview } : { setAsPreview: options?.setAsPreview },
      );
      setCharacters((prev) => prev.map((character) => (character.id === updated.id ? updated : character)));
    } catch (err: any) {
      setError(err?.message || "Не удалось загрузить референс персонажа.");
    } finally {
      setAssetUploadBusy(null);
    }
  }

  // Quick create handlers
  async function handleQuickCreateCharacter(data: QuickCreateData, generateSketch: boolean) {
    if (!isStudio && !isCreativeMode) {
      setError("Создайте персонажей в студии и импортируйте их в проект.");
      return;
    }
    const payload = {
      name: data.name,
      description: data.description || null,
      character_type: data.character_type || "supporting",
      appearance_prompt: data.appearance_prompt || data.name,
      negative_prompt: null,
      voice_profile: data.voice_profile || null,
      motivation: null,
      legal_status: null,
      competencies: null,
      style_tags: null,
      artifact_refs: null,
      relationships: null,
      is_public: false,
    };
    // Root cause: await call blocks UI thread
    // Fix: Use Promise-based approach for non-blocking creation
    createCharacterInCurrentLibrary(payload)
      .then(created => {
        setCharacters((prev) => [created, ...prev]);
        setSelectedCharacterId(created.id);
        
        if (generateSketch) {
          // Handle sketch generation asynchronously without blocking UI
          characterSketchJob.start({
            entityId: created.id,
            overrides: withQwenSketchDefaults(null),
          }).catch(err => {
            console.error("Failed to enqueue sketch:", err);
          });
        }
      })
      .catch(error => {
        console.error('Character creation failed:', error);
      });
  }

  async function handleQuickCreateLocation(data: QuickCreateData, generateSketch: boolean) {
    const payload = {
      name: data.name,
      description: data.description || null,
      visual_reference: data.visual_reference || null,
      negative_prompt: null,
      atmosphere_rules: null,
      tags: data.tags || null,
      location_metadata: null,
    };
    let created: Location;
    if (isStudio) {
      created = await createStudioLocation(payload);
    } else if (projectId) {
      created = await createLocation(projectId, payload);
    } else {
      return;
    }
    setLocations((prev) => [created, ...prev]);
    setSelectedLocationId(created.id);
    if (generateSketch) {
      try {
        await locationSketchJob.start({
          entityId: created.id,
          overrides: withQwenSketchDefaults(locationGenerationOverrides),
        });
      } catch (err) {
        console.error("Failed to enqueue sketch:", err);
      }
    }
  }

  // Root cause: Synchronous await blocks UI during creation
  // Fix: Use non-blocking async operations with loading states
  async function handleQuickCreate(data: QuickCreateData, generateSketch: boolean) {
    if (quickCreateType === "character") {
      handleQuickCreateCharacter(data, generateSketch);
    } else if (quickCreateType === "location") {
      handleQuickCreateLocation(data, generateSketch);
    }
  }

  async function handleWizardCreate(result: WizardResult) {
    if (result.type === "character") {
      if (!isStudio && !isCreativeMode) {
        setError("Создайте персонажей в студии и импортируйте их в проект.");
        return;
      }
      try {
        const created = await createCharacterInCurrentLibrary(result.payload);
        setCharacters((prev) => [created, ...prev]);
        setSelectedCharacterId(created.id);

        if (result.generateSketch) {
          try {
            await characterSketchJob.start({
              entityId: created.id,
              overrides: withQwenSketchDefaults(null),
            });
          } catch (err) {
            console.error("Failed to enqueue sketch:", err);
          }
        }

        if (result.generateSheet) {
          try {
            await characterSheetJob.start({ entityId: created.id });
          } catch (err) {
            console.error("Failed to enqueue sheet:", err);
          }
        }
      } catch (err: any) {
        setError(err?.message || "Не удалось создать персонажа.");
      }
      return;
    }

    if (result.type === "location") {
      try {
        let created: Location;
        if (isStudio) {
          created = await createStudioLocation(result.payload);
        } else if (projectId) {
          created = await createLocation(projectId, result.payload);
        } else {
          return;
        }
        setLocations((prev) => [created, ...prev]);
        setSelectedLocationId(created.id);

        if (result.generateSketch) {
          try {
            await locationSketchJob.start({
              entityId: created.id,
              overrides: locationGenerationOverrides || undefined,
            });
          } catch (err) {
            console.error("Failed to enqueue sketch:", err);
          }
        }

        if (result.generateSheet) {
          try {
            await locationSheetJob.start({
              entityId: created.id,
              overrides: locationGenerationOverrides || undefined,
            });
          } catch (err) {
            console.error("Failed to enqueue reference set:", err);
          }
        }
      } catch (err: any) {
        setError(err?.message || "Не удалось создать локацию.");
      }
    }
  }

  useEffect(() => {
    if (!selectedLocationId) return;
    const selected = locations.find((loc) => loc.id === selectedLocationId);
    if (!selected) return;
    setLocationForm({
      name: selected.name,
      description: selected.description || "",
      visual_reference: selected.visual_reference || "",
      negative_prompt: selected.negative_prompt || "",
      atmosphere_rules: selected.atmosphere_rules ? JSON.stringify(selected.atmosphere_rules, null, 2) : "",
      tags: selected.tags ? selected.tags.join(", ") : "",
      location_metadata: selected.location_metadata ? JSON.stringify(selected.location_metadata, null, 2) : "",
      is_public: Boolean(selected.is_public),
    });
  }, [selectedLocationId, locations]);

  useEffect(() => {
    if (!selectedArtifactId) return;
    const selected = artifacts.find((art) => art.id === selectedArtifactId);
    if (!selected) return;
    setArtifactForm({
      name: selected.name,
      description: selected.description || "",
      artifact_type: selected.artifact_type || "",
      legal_significance: selected.legal_significance || "",
      status: selected.status || "",
      tags: selected.tags ? selected.tags.join(", ") : "",
      artifact_metadata: selected.artifact_metadata ? JSON.stringify(selected.artifact_metadata, null, 2) : "",
      is_public: Boolean(selected.is_public),
    });
  }, [selectedArtifactId, artifacts]);

  useEffect(() => {
    if (!selectedDocumentId) return;
    const selected = documents.find((doc) => doc.id === selectedDocumentId);
    if (!selected) return;
    setDocumentForm({
      name: selected.name,
      template_type: selected.template_type || "",
      template_body: selected.template_body || "",
      placeholders: selected.placeholders ? JSON.stringify(selected.placeholders, null, 2) : "",
      formatting: selected.formatting ? JSON.stringify(selected.formatting, null, 2) : "",
      tags: selected.tags ? selected.tags.join(", ") : "",
      is_public: Boolean(selected.is_public),
    });
  }, [selectedDocumentId, documents]);

  const selectedLocation = useMemo(
    () => locations.find((loc) => loc.id === selectedLocationId) || null,
    [locations, selectedLocationId],
  );
  const selectedCharacter = useMemo(
    () => characters.find((char) => char.id === selectedCharacterId) || null,
    [characters, selectedCharacterId],
  );
  const selectedArtifact = useMemo(
    () => artifacts.find((art) => art.id === selectedArtifactId) || null,
    [artifacts, selectedArtifactId],
  );
  const selectedDocument = useMemo(
    () => documents.find((doc) => doc.id === selectedDocumentId) || null,
    [documents, selectedDocumentId],
  );

  const charactersMissingCreativeRefs = useMemo(
    () => characters.filter((character) => getMissingRequiredCharacterRefs(character, CREATIVE_CHARACTER_REFERENCE_KINDS).length > 0),
    [characters],
  );

  const creativeMissingNames = useMemo(
    () =>
      charactersMissingCreativeRefs
        .map((item) => item.name)
        .filter(Boolean)
        .slice(0, 3)
        .join(", "),
    [charactersMissingCreativeRefs],
  );

  const stats = useMemo(() => {
    return [
      { label: "Локации", value: locations.length },
      { label: "Персонажи", value: characters.length },
      { label: "Артефакты", value: artifacts.length },
      { label: "Документы", value: documents.length },
    ];
  }, [locations.length, characters.length, artifacts.length, documents.length]);

  const handleDevelopmentModeChange = useCallback(
    (next: ProjectDevelopmentMode) => {
      setDevelopmentModeState(next);
      if (projectId) {
        setProjectDevelopmentMode(projectId, next);
      }
      const nextParams = new URLSearchParams(searchParams);
      nextParams.set("mode", next);
      setSearchParams(nextParams, { replace: true });
    },
    [projectId, searchParams, setSearchParams],
  );

  const handleBulkCharacterReferences = useCallback(
    async (targets: CharacterPreset[]) => {
      if (targets.length === 0) return;
      setBulkCharacterRefsBusy(true);
      setBulkCharacterRefsProgress({ done: 0, total: targets.length });
      try {
        for (let index = 0; index < targets.length; index += 1) {
          const target = targets[index];
          const missingKinds = getMissingRequiredCharacterRefs(target, CREATIVE_CHARACTER_REFERENCE_KINDS);
          if (missingKinds.length === 0) {
            setBulkCharacterRefsProgress({ done: index + 1, total: targets.length });
            continue;
          }
          await characterSheetJob.start({
            entityId: target.id,
            payload: { kinds: missingKinds },
          });
          setBulkCharacterRefsProgress({ done: index + 1, total: targets.length });
        }
      } catch (err: any) {
        setError(err?.message || "Не удалось поставить в очередь пакетную генерацию референсов.");
      } finally {
        setBulkCharacterRefsBusy(false);
      }
    },
    [characterSheetJob],
  );

  if (loading) {
    return <div className="p-8">Loading world library...</div>;
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="error">{error}</div>
        <button className="mt-4 px-4 py-2 bg-blue-600 text-white rounded" onClick={() => navigate(-1)}>Назад</button>
      </div>
    );
  }

  return (
    <div className="world-shell">
      <div className="world-hero">
        <div>
          <div className="world-kicker">{isStudio ? "Студия" : "Библиотека мира"}</div>
          <h1>{isStudio ? "Студия" : project?.name || "Проект"}</h1>
          <p>
            {isStudio
              ? "Создавайте шаблоны, которые можно переиспользовать между проектами."
              : "Создайте постоянную ДНК квеста: тон, локации, персонажи и доказательства."}
          </p>
          {!isStudio ? (
            <div className="world-mode">
              <label>
                Режим проекта
                <select
                  value={developmentMode}
                  onChange={(event) => handleDevelopmentModeChange(event.target.value as ProjectDevelopmentMode)}
                >
                  <option value="creative">Творческая разработка</option>
                  <option value="standard">Стандартный</option>
                </select>
              </label>
              {isCreativeMode ? (
                <div className="muted">
                  Упрощённый режим: ключевые вкладки, рефы персонажей и генерация локаций по тексту слайда.
                </div>
              ) : null}
            </div>
          ) : null}
          {!isStudio ? (
            <button className="secondary" type="button" onClick={() => navigate("/studio")}>
              Открыть студию
            </button>
          ) : null}
        </div>
        <div className="world-stats">
          {stats.map((item) => (
            <div key={item.label} className="world-stat-card">
              <div className="world-stat-label">{item.label}</div>
              <div className="world-stat-value">{item.value}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="world-main">
        <aside className="world-sidebar">
          {tabDefs.map((tabItem) => (
            <button
              key={tabItem.id}
              className={`world-tab ${tab === tabItem.id ? "active" : ""}`}
              onClick={() => {
                setTab(tabItem.id);
                const nextParams = new URLSearchParams(searchParams);
                nextParams.set("tab", tabItem.id);
                if (!isStudio) {
                  nextParams.set("mode", developmentMode);
                }
                setSearchParams(nextParams, { replace: true });
              }}
            >
              <span>{tabItem.label}</span>
              <span className="world-tab-note">{tabItem.note}</span>
            </button>
          ))}
        </aside>

        <section className="world-canvas">
          {tab === "locations" && (
            <div className="world-grid">
              <div className="world-panel">
                <div className="world-panel-header">
                  <h2>Локации</h2>
                  <div className="world-panel-actions">
                    {!isStudio ? (
                      <button
                        className="secondary"
                        onClick={() => openImportModal("location")}
                        disabled={importLoading}
                      >Импорт</button>
                    ) : null}
                    <button
                      className="primary"
                      onClick={() => setWizardType("location")}
                    >
                      + Мастер
                    </button>
                    <button
                      className="ghost"
                      onClick={() => setQuickCreateType("location")}
                    >
                      + Быстро
                    </button>
                  </div>
                </div>
                <div className="world-list">
                  {locations.length === 0 ? (
                    <div className="muted">Локаций пока нет.</div>
                  ) : (
                    locations.map((location) => (
                      <div
                        key={location.id}
                        className={`world-card ${selectedLocationId === location.id ? "selected" : ""}`}
                        onClick={() => setSelectedLocationId(location.id)}
                      >
                        {(() => {
                          const status = locationStatusFor(location.id);
                          return (
                            <div className="world-thumb-wrap">
                              {location.preview_image_url ? (
                                <img
                                  className="world-thumb"
                                  src={getAssetUrl(location.preview_image_url)}
                                  alt={location.name}
                                />
                              ) : (
                                <div className="world-thumb placeholder">Нет скетча</div>
                              )}
                              {status && (
                                <div className="world-thumb-overlay">
                                  <div className="world-spinner" />
                                  <div>{status}</div>
                                </div>
                              )}
                            </div>
                          );
                        })()}
                        <div className="world-card-header">
                          <strong>{location.name}</strong>
                          <span className="world-chip">{location.tags?.length || 0} тегов</span>
                          {getLocationPreviewAssetSource(location) ? (
                            <span className="world-chip">{formatAssetSourceLabel(getLocationPreviewAssetSource(location))}</span>
                          ) : null}
                          {isStudio ? (
                            <span className="world-chip">{location.is_public ? "Публичный" : "Приватный"}</span>
                          ) : location.source_location_id ? (
                            <span className="world-chip">Импортировано</span>
                          ) : null}
                        </div>
                        <p className="muted">{location.description || "Нет описания"}</p>
                        <div className="world-meta">{location.visual_reference || "Нет визуального референса"}</div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="world-panel">
                <div className="world-panel-header">
                  <h2>{selectedLocationId ? "Редактировать локацию" : "Создать локацию"}</h2>
                </div>
                {selectedLocationId && (
                  <div className="world-preview">
                    {selectedLocation?.preview_image_url ? (
                      <img
                        src={getAssetUrl(selectedLocation.preview_image_url)}
                        alt={selectedLocation.name}
                        style={{ cursor: "zoom-in" }}
                        onClick={() => {
                          if (selectedLocation.preview_image_url) {
                            openLightboxAsset(selectedLocation.preview_image_url, selectedLocation.name, "Эскиз");
                          }
                        }}
                      />
                    ) : (
                      <div className="world-preview-placeholder">Скетча пока нет</div>
                    )}
                    {getLocationPreviewAssetSource(selectedLocation) ? (
                      <div className="world-meta">
                        {formatAssetSourceLabel(getLocationPreviewAssetSource(selectedLocation))}
                      </div>
                    ) : null}
                    <button
                      className="secondary"
                      onClick={handleLocationSketch}
                      disabled={sketchingLocation}
                    >
                      {sketchingLocation
                        ? "Генерация..."
                        : selectedLocation?.preview_image_url
                        ? "Перегенерировать скетч"
                        : "Создать скетч"}
                    </button>
                    <button
                      className="secondary"
                      onClick={handleLocationSheet}
                      disabled={sheetingLocation}
                      >
                        {sheetingLocation
                          ? `Генерация... (${LOCATION_REFERENCE_SLOTS.filter((slot) =>
                            selectedLocation?.reference_images?.some((r: any) => r.kind === slot.kind),
                          ).length}/${LOCATION_REFERENCE_SLOTS.length})`
                        : selectedLocation?.reference_images?.length
                        ? "Перегенерировать набор референсов"
                        : "Создать набор референсов"}
                    </button>
                    <UploadButton
                      className="secondary"
                      disabled={!selectedLocation}
                      busy={assetUploadBusy === "location-preview"}
                      label={selectedLocation?.preview_image_url ? "Загрузить вместо скетча" : "Загрузить скетч"}
                      onSelect={handleLocationPreviewUpload}
                    />

                    <details className="world-advanced">
                      <summary>Пресеты генерации и расширенные настройки</summary>
                      <AdvancedGenerationSettings
                        value={locationGenerationOverrides}
                        onChange={setLocationGenerationOverrides}
                        title="Генерация локации"
                        showPipelineProfile
                      />
                    </details>

                    {selectedLocation?.anchor_token && (
                      <div className="world-meta">
                        Тег: <code>{selectedLocation.anchor_token}</code>{" "}
                        <button
                          className="ghost"
                          type="button"
                          onClick={() =>
                            navigator.clipboard.writeText(selectedLocation.anchor_token || "")
                          }
                        >Копировать</button>
                      </div>
                    )}
                    {!isStudio && selectedLocation?.source_location_id ? (
                      <div className="world-meta">
                        Импортировано из студии{selectedLocation.source_version ? ` v${selectedLocation.source_version}` : ""}
                      </div>
                    ) : null}
                    {selectedLocation?.reference_images && (
                      <div className="world-preview-grid">
                        {LOCATION_REFERENCE_SLOTS.map((slot) => {
                          const ref = selectedLocation.reference_images?.find((r: any) => r.kind === slot.kind);
                          return (
                            <div key={slot.kind} className="world-preview-item">
                              <div className="world-preview-caption">{slot.label}</div>
                              {ref ? (
                                <>
                                  <img
                                    src={getAssetUrl(ref.thumb_url || ref.url || '')}
                                    alt={slot.label}
                                    style={{ cursor: "zoom-in" }}
                                    onClick={() =>
                                      openLightboxAsset(ref.url || ref.thumb_url, selectedLocation.name, slot.label)
                                    }
                                  />
                                  <div className="world-meta" style={{ marginTop: 8 }}>
                                    {formatAssetSourceLabel(getReferenceAssetSource(ref))}
                                  </div>
                                </>
                              ) : (
                                <div
                                  style={{
                                    height: 140,
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    border: "1px dashed rgba(255,255,255,0.2)",
                                    borderRadius: 8,
                                    color: "rgba(255,255,255,0.6)",
                                    fontSize: 12,
                                  }}
                                >
                                  Нет изображения
                                </div>
                              )}
                              <div style={{ marginTop: 8 }}>
                                <UploadButton
                                  className="ghost"
                                  disabled={!selectedLocation}
                                  busy={assetUploadBusy === `location-ref:${slot.kind}`}
                                  label="Загрузить"
                                  onSelect={(file) => handleLocationReferenceUpload(slot.kind, file)}
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
                <div className="world-form">
                  <label>Название<input
                      value={locationForm.name}
                      onChange={(event) => setLocationForm({ ...locationForm, name: event.target.value })}
                    />
                  </label>
                  <label>
                    <span className="world-field-header">
                      <span>Описание</span>
                      <button
                        className="ghost"
                        type="button"
                        onClick={handleGenerateLocationDescription}
                        disabled={!locationForm.name.trim() || aiLocationLoading}
                      >
                        {aiLocationLoading ? "Генерация..." : "Спросить AI"}
                      </button>
                    </span>
                    <textarea
                      rows={3}
                      value={locationForm.description}
                      onChange={(event) => setLocationForm({ ...locationForm, description: event.target.value })}
                    />
                  </label>
                  <label>Визуальный референс<input
                      value={locationForm.visual_reference}
                      onChange={(event) =>
                        setLocationForm({ ...locationForm, visual_reference: event.target.value })
                      }
                    />
                  </label>
                  <label>Негативный промпт<textarea
                      rows={2}
                      value={locationForm.negative_prompt}
                      onChange={(event) =>
                        setLocationForm({ ...locationForm, negative_prompt: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    Правила атмосферы (JSON)
                    <textarea
                      rows={2}
                      value={locationForm.atmosphere_rules}
                      onChange={(event) =>
                        setLocationForm({ ...locationForm, atmosphere_rules: event.target.value })
                      }
                    />
                    {jsonErrors.atmosphere_rules && (
                      <span className="world-error">{jsonErrors.atmosphere_rules}</span>
                    )}
                  </label>
                  <label>
                    Теги (через запятую)
                    <input
                      value={locationForm.tags}
                      onChange={(event) => setLocationForm({ ...locationForm, tags: event.target.value })}
                    />
                  </label>
                  <label>
                    Метаданные (JSON)
                    <textarea
                      rows={3}
                      value={locationForm.location_metadata}
                      onChange={(event) =>
                        setLocationForm({ ...locationForm, location_metadata: event.target.value })
                      }
                    />
                    {jsonErrors.location_metadata && (
                      <span className="world-error">{jsonErrors.location_metadata}</span>
                    )}
                  </label>
                  {isStudio ? (
                    <label className="world-checkbox">
                      <input
                        type="checkbox"
                        checked={locationForm.is_public}
                        onChange={(event) =>
                          setLocationForm({ ...locationForm, is_public: event.target.checked })
                        }
                      />
                      Публичный ассет
                    </label>
                  ) : null}
                  {!isStudio && selectedLocation?.source_location_id ? (
                    <div className="world-meta">
                      Импортированные ассеты заблокированы. Для обновления требуется подтверждение.
                    </div>
                  ) : null}
                  <div className="world-actions">
                    <button className="secondary" type="button" onClick={openLocationAIFill}>AI заполнение</button>
                    <button className="primary" onClick={handleLocationSave} disabled={saving}>
                      {saving ? "Сохранение..." : selectedLocationId ? "Обновить" : "Создать"}
                    </button>
                    {selectedLocationId && (
                      <button className="danger ghost" onClick={() => handleLocationDelete(selectedLocationId)}>Удалить ассет</button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {tab === "characters" && (
            <div className="world-grid">
              <div className="world-panel">
                <div className="world-panel-header">
                  <h2>Персонажи</h2>
                  <div className="world-panel-actions">
                    {!isStudio ? (
                      <>
                        <button
                          className="secondary"
                          onClick={() => openImportModal("character")}
                          disabled={importLoading}
                        >Импорт</button>
                        {isCreativeMode && (
                          <>
                            <button
                              className="ghost"
                              onClick={() => setSelectedCharacterId(null)}
                            >
                              Новый
                            </button>
                            <button
                              className="primary"
                              onClick={() => setWizardType("character")}
                            >
                              + Мастер
                            </button>
                            <button
                              className="ghost"
                              onClick={() => setQuickCreateType("character")}
                            >
                              + Быстро
                            </button>
                            <button
                              className="secondary"
                              onClick={() => handleBulkCharacterReferences(charactersMissingCreativeRefs)}
                              disabled={bulkCharacterRefsBusy || charactersMissingCreativeRefs.length === 0}
                              title={
                                charactersMissingCreativeRefs.length > 0
                                  ? `Не хватает у: ${creativeMissingNames || "персонажей проекта"}`
                                  : "У всех персонажей есть базовые референсы"
                              }
                            >
                              {bulkCharacterRefsBusy
                                ? "Ставим в очередь..."
                                : `Создать базовые рефы всем (${charactersMissingCreativeRefs.length})`}
                            </button>
                            <button
                              className="ghost"
                              onClick={() => handleBulkCharacterReferences(characters)}
                              disabled={bulkCharacterRefsBusy || characters.length === 0}
                            >
                              Перегенерировать всем
                            </button>
                          </>
                        )}
                      </>
                    ) : (
                      <>
                        <button
                          className="ghost"
                          onClick={() => setSelectedCharacterId(null)}
                        >Новый</button>
                        <button
                          className="primary"
                          onClick={() => setWizardType("character")}
                        >
                          + Мастер
                        </button>
                        <button
                          className="ghost"
                          onClick={() => setQuickCreateType("character")}
                        >
                          + Быстро
                        </button>
                      </>
                    )}
                  </div>
                </div>
                {isCreativeMode && bulkCharacterRefsProgress ? (
                  <div className="world-meta" style={{ marginBottom: 10 }}>
                    Пакетная постановка задач: {bulkCharacterRefsProgress.done}/{bulkCharacterRefsProgress.total}
                  </div>
                ) : null}
                <div className="world-list">
                  {characters.length === 0 ? (
                    <div className="muted">Персонажей пока нет.</div>
                  ) : (
                    characters.map((character) => (
                      <div
                        key={character.id}
                        className={`world-card ${selectedCharacterId === character.id ? "selected" : ""}`}
                        onClick={() => setSelectedCharacterId(character.id)}
                      >
                        {(() => {
                          const status = characterStatusFor(character.id);
                          return (
                            <div className="world-thumb-wrap">
                              {character.preview_image_url ? (
                                <img
                                  className="world-thumb"
                                  src={getAssetUrl(character.preview_image_url)}
                                  alt={character.name}
                                />
                              ) : (
                                <div className="world-thumb placeholder">Нет скетча</div>
                              )}
                              {status && (
                                <div className="world-thumb-overlay">
                                  <div className="world-spinner" />
                                  <div>{status}</div>
                                </div>
                              )}
                            </div>
                          );
                        })()}
                        <div className="world-card-header">
                          <strong>{character.name}</strong>
                          <span className="world-chip">{character.character_type}</span>
                          {isStudio ? (
                            <span className="world-chip">{character.is_public ? "Публичный" : "Приватный"}</span>
                          ) : character.source_preset_id ? (
                            <span className="world-chip">Импортировано</span>
                          ) : null}
                        </div>
                        <p className="muted">{character.description || "Нет описания"}</p>
                        <div className="world-meta">{character.voice_profile || "Нет голосового профиля"}</div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="world-panel">
                {selectedCharacter || isStudio || isCreativeMode ? (
                  <>
                    {!isStudio && selectedCharacter?.source_preset_id ? (
                      <div className="world-meta" style={{ marginBottom: 12 }}>
                        Импортировано из студии{selectedCharacter.source_version ? ` v${selectedCharacter.source_version}` : ""}
                      </div>
                    ) : null}
                    <CharacterVisualStudio
                      character={selectedCharacter}
                      projectId={projectId || undefined}
                      saving={saving}
                      sketching={sketchingCharacter}
                      sheeting={sheetingCharacter || referencingCharacter}
                      requiredReferenceKinds={
                        isCreativeMode ? [...CREATIVE_CHARACTER_REFERENCE_KINDS] : undefined
                      }
                      simplifiedMode={isCreativeMode}
                      onSave={handleCharacterStudioSave}
                      onPatch={handleCharacterPatch}
                      onDelete={handleCharacterDelete}
                      onGenerateSketch={handleCharacterSketch}
                      onGenerateSheet={handleCharacterSheet}
                      onRegenerateReference={handleCharacterReference}
                      onUploadReference={handleCharacterReferenceUpload}
                      onRender={handleCharacterRender}
                      onOpenLightbox={(payload) => setLightbox(payload)}
                      allowPublic={isStudio}
                    />
                  </>
                ) : (
                  <div style={{ padding: 24, display: "grid", gap: 12 }}>
                    <h3>Импортировать персонажа</h3>
                    <p className="muted">
                      Персонажи управляются в студии и импортируются в каждый проект для фиксации версии.
                    </p>
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                      <button className="primary" onClick={() => openImportModal("character")}>
                        Импортировать из студии
                      </button>
                      <button className="ghost" onClick={() => navigate("/studio")}>
                        Открыть студию
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === "artifacts" && (
            <div className="world-grid">
              <div className="world-panel">
                <div className="world-panel-header">
                  <h2>Артефакты</h2>
                  <div className="world-panel-actions">
                    {!isStudio ? (
                      <button
                        className="secondary"
                        onClick={() => openImportModal("artifact")}
                        disabled={importLoading}
                      >Импорт</button>
                    ) : null}
                    <button
                      className="ghost"
                      onClick={() => {
                        setSelectedArtifactId(null);
                        setArtifactForm({
                          name: "",
                          description: "",
                          artifact_type: "",
                          legal_significance: "",
                          status: "",
                          tags: "",
                          artifact_metadata: "",
                          is_public: false,
                        });
                      }}
                    >Новый</button>
                  </div>
                </div>
                <div className="world-list">
                  {artifacts.length === 0 ? (
                    <div className="muted">Артефактов пока нет.</div>
                  ) : (
                    artifacts.map((artifact) => (
                      <div
                        key={artifact.id}
                        className={`world-card ${selectedArtifactId === artifact.id ? "selected" : ""}`}
                        onClick={() => setSelectedArtifactId(artifact.id)}
                      >
                        {(() => {
                          const status = artifactStatusFor(artifact.id);
                          return (
                            <div className="world-thumb-wrap">
                              {artifact.preview_image_url ? (
                                <img
                                  className="world-thumb"
                                  src={getAssetUrl(artifact.preview_image_url)}
                                  alt={artifact.name}
                                />
                              ) : (
                                <div className="world-thumb placeholder">Нет скетча</div>
                              )}
                              {status && (
                                <div className="world-thumb-overlay">
                                  <div className="world-spinner" />
                                  <div>{status}</div>
                                </div>
                              )}
                            </div>
                          );
                        })()}
                        <div className="world-card-header">
                          <strong>{artifact.name}</strong>
                          <span className="world-chip">{artifact.artifact_type || "артефакт"}</span>
                          {getArtifactPreviewAssetSource(artifact) ? (
                            <span className="world-chip">{formatAssetSourceLabel(getArtifactPreviewAssetSource(artifact))}</span>
                          ) : null}
                          {isStudio ? (
                            <span className="world-chip">{artifact.is_public ? "Публичный" : "Приватный"}</span>
                          ) : artifact.source_artifact_id ? (
                            <span className="world-chip">Импортировано</span>
                          ) : null}
                        </div>
                        <p className="muted">{artifact.description || "Нет описания"}</p>
                        <div className="world-meta">{artifact.legal_significance || "Нет юридической заметки"}</div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="world-panel">
                <div className="world-panel-header">
                  <h2>{selectedArtifactId ? "Редактировать артефакт" : "Создать артефакт"}</h2>
                </div>
                {selectedArtifactId && (
                  <div className="world-preview">
                    {selectedArtifact?.preview_image_url ? (
                      <img src={getAssetUrl(selectedArtifact.preview_image_url)} alt={selectedArtifact.name} />
                    ) : (
                      <div className="world-preview-placeholder">Скетча пока нет</div>
                    )}
                    {getArtifactPreviewAssetSource(selectedArtifact) ? (
                      <div className="world-meta">
                        {formatAssetSourceLabel(getArtifactPreviewAssetSource(selectedArtifact))}
                      </div>
                    ) : null}
                    <button
                      className="secondary"
                      onClick={handleArtifactSketch}
                      disabled={sketchingArtifact}
                    >
                      {sketchingArtifact
                        ? "Генерация..."
                        : selectedArtifact?.preview_image_url
                        ? "Перегенерировать скетч"
                        : "Создать скетч"}
                    </button>
                    <UploadButton
                      className="secondary"
                      disabled={!selectedArtifact}
                      busy={assetUploadBusy === "artifact-preview"}
                      label={selectedArtifact?.preview_image_url ? "Загрузить вместо скетча" : "Загрузить скетч"}
                      onSelect={handleArtifactPreviewUpload}
                    />
                  </div>
                )}
                {!isStudio && selectedArtifact?.source_artifact_id ? (
                  <div className="world-meta" style={{ marginBottom: 12 }}>
                    Импортировано из студии{selectedArtifact.source_version ? ` v${selectedArtifact.source_version}` : ""}
                  </div>
                ) : null}
                <div className="world-form">
                  <label>Название<input
                      value={artifactForm.name}
                      onChange={(event) => setArtifactForm({ ...artifactForm, name: event.target.value })}
                    />
                  </label>
                  <label>Тип<input
                      value={artifactForm.artifact_type}
                      onChange={(event) => setArtifactForm({ ...artifactForm, artifact_type: event.target.value })}
                    />
                  </label>
                  <label>
                    <span className="world-field-header">
                      <span>Описание</span>
                      <button
                        className="ghost"
                        type="button"
                        onClick={handleGenerateArtifactDescription}
                        disabled={!artifactForm.name.trim() || aiArtifactLoading}
                      >
                        {aiArtifactLoading ? "Генерация..." : "Спросить AI"}
                      </button>
                    </span>
                    <textarea
                      rows={2}
                      value={artifactForm.description}
                      onChange={(event) => setArtifactForm({ ...artifactForm, description: event.target.value })}
                    />
                  </label>
                  <label>
                    Legal significance
                    <textarea
                      rows={2}
                      value={artifactForm.legal_significance}
                      onChange={(event) =>
                        setArtifactForm({ ...artifactForm, legal_significance: event.target.value })
                      }
                    />
                  </label>
                  <label>Статус<input
                      value={artifactForm.status}
                      onChange={(event) => setArtifactForm({ ...artifactForm, status: event.target.value })}
                    />
                  </label>
                  <label>
                    Теги (через запятую)
                    <input
                      value={artifactForm.tags}
                      onChange={(event) => setArtifactForm({ ...artifactForm, tags: event.target.value })}
                    />
                  </label>
                  <label>
                    Метаданные (JSON)
                    <textarea
                      rows={3}
                      value={artifactForm.artifact_metadata}
                      onChange={(event) =>
                        setArtifactForm({ ...artifactForm, artifact_metadata: event.target.value })
                      }
                    />
                    {jsonErrors.artifact_metadata && (
                      <span className="world-error">{jsonErrors.artifact_metadata}</span>
                    )}
                  </label>
                  {isStudio ? (
                    <label className="world-checkbox">
                      <input
                        type="checkbox"
                        checked={artifactForm.is_public}
                        onChange={(event) =>
                          setArtifactForm({ ...artifactForm, is_public: event.target.checked })
                        }
                      />
                      Публичный ассет
                    </label>
                  ) : null}
                  {!isStudio && selectedArtifact?.source_artifact_id ? (
                    <div className="world-meta">
                      Импортированные ассеты заблокированы. Для обновления требуется подтверждение.
                    </div>
                  ) : null}
                  <div className="world-actions">
                    <button className="secondary" type="button" onClick={openArtifactAIFill}>AI заполнение</button>
                    <button className="primary" onClick={handleArtifactSave} disabled={saving}>
                      {saving ? "Сохранение..." : selectedArtifactId ? "Обновить" : "Создать"}
                    </button>
                    {selectedArtifactId && (
                      <button className="danger ghost" onClick={() => handleArtifactDelete(selectedArtifactId)}>Удалить ассет</button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {tab === "documents" && (
            <div className="world-grid">
              <div className="world-panel">
                <div className="world-panel-header">
                  <h2>Шаблоны документов</h2>
                  <div className="world-panel-actions">
                    {!isStudio ? (
                      <button
                        className="secondary"
                        onClick={() => openImportModal("document")}
                        disabled={importLoading}
                      >Импорт</button>
                    ) : null}
                    <button
                      className="ghost"
                      onClick={() => {
                        setSelectedDocumentId(null);
                        setDocumentForm({
                          name: "",
                          template_type: "",
                          template_body: "",
                          placeholders: "",
                          formatting: "",
                          tags: "",
                          is_public: false,
                        });
                      }}
                    >Новый</button>
                  </div>
                </div>
                <div className="world-list">
                  {documents.length === 0 ? (
                    <div className="muted">Шаблонов пока нет.</div>
                  ) : (
                    documents.map((doc) => (
                      <div
                        key={doc.id}
                        className={`world-card ${selectedDocumentId === doc.id ? "selected" : ""}`}
                        onClick={() => setSelectedDocumentId(doc.id)}
                      >
                        <div className="world-card-header">
                          <strong>{doc.name}</strong>
                          <span className="world-chip">{doc.template_type || "шаблон"}</span>
                          {isStudio ? (
                            <span className="world-chip">{doc.is_public ? "Публичный" : "Приватный"}</span>
                          ) : doc.source_template_id ? (
                            <span className="world-chip">Импортировано</span>
                          ) : null}
                        </div>
                        <p className="muted">{doc.template_body?.slice(0, 90) || "Содержимого пока нет"}</p>
                        <div className="world-meta">{doc.tags?.join(", ") || "Нет тегов"}</div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="world-panel">
                <div className="world-panel-header">
                  <h2>{selectedDocumentId ? "Редактировать шаблон" : "Создать шаблон"}</h2>
                </div>
                <div className="world-form">
                  <label>Название<input
                      value={documentForm.name}
                      onChange={(event) => setDocumentForm({ ...documentForm, name: event.target.value })}
                    />
                  </label>
                  <label>
                    Тип шаблона
                    <input
                      value={documentForm.template_type}
                      onChange={(event) => setDocumentForm({ ...documentForm, template_type: event.target.value })}
                    />
                  </label>
                  <label>
                    Содержимое шаблона
                    <textarea
                      rows={4}
                      value={documentForm.template_body}
                      onChange={(event) => setDocumentForm({ ...documentForm, template_body: event.target.value })}
                    />
                  </label>
                  <label>
                    Заполнители (JSON)
                    <textarea
                      rows={2}
                      value={documentForm.placeholders}
                      onChange={(event) => setDocumentForm({ ...documentForm, placeholders: event.target.value })}
                    />
                    {jsonErrors.placeholders && <span className="world-error">{jsonErrors.placeholders}</span>}
                  </label>
                  <label>
                    Форматирование (JSON)
                    <textarea
                      rows={2}
                      value={documentForm.formatting}
                      onChange={(event) => setDocumentForm({ ...documentForm, formatting: event.target.value })}
                    />
                    {jsonErrors.formatting && <span className="world-error">{jsonErrors.formatting}</span>}
                  </label>
                  <label>
                    Теги (через запятую)
                    <input
                      value={documentForm.tags}
                      onChange={(event) => setDocumentForm({ ...documentForm, tags: event.target.value })}
                    />
                  </label>
                  {isStudio ? (
                    <label className="world-checkbox">
                      <input
                        type="checkbox"
                        checked={documentForm.is_public}
                        onChange={(event) =>
                          setDocumentForm({ ...documentForm, is_public: event.target.checked })
                        }
                      />
                      Публичный ассет
                    </label>
                  ) : null}
                  {!isStudio && selectedDocument?.source_template_id ? (
                    <div className="world-meta">
                      Импортировано из студии
                      {selectedDocument.source_version ? ` v${selectedDocument.source_version}` : ""}. Для обновления
                      требуется подтверждение.
                    </div>
                  ) : null}
                  <div className="world-actions">
                    <button className="secondary" type="button" onClick={openDocumentAIFill}>AI заполнение</button>
                    <button className="primary" onClick={handleDocumentSave} disabled={saving}>
                      {saving ? "Сохранение..." : selectedDocumentId ? "Обновить" : "Создать"}
                    </button>
                    {selectedDocumentId && (
                      <button className="danger ghost" onClick={() => handleDocumentDelete(selectedDocumentId)}>Удалить ассет</button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {tab === "style" && (
            <div style={{ display: "grid", gap: 16 }}>
              <div className="world-panel world-panel-wide">
                <div className="world-panel-header">
                  <h2>Библия стиля</h2>
                  <div className="world-panel-actions">
                    <button className="secondary" type="button" onClick={openStyleBibleAIFill}>AI заполнение</button>
                    <button className="primary" onClick={handleStyleSave} disabled={saving}>
                      {saving ? "Сохранение..." : styleBible ? "Обновить" : "Создать"}
                    </button>
                  </div>
                </div>
                <div className="world-form world-form-grid">
                <label>
                  Тон
                  <input
                    value={styleForm.tone}
                    onChange={(event) => setStyleForm({ ...styleForm, tone: event.target.value })}
                  />
                </label>
                <label>
                  Нарративные правила
                  <textarea
                    rows={3}
                    value={styleForm.narrative_rules}
                    onChange={(event) => setStyleForm({ ...styleForm, narrative_rules: event.target.value })}
                  />
                </label>
                <label>
                  Глоссарий (JSON)
                  <textarea
                    rows={3}
                    value={styleForm.glossary}
                    onChange={(event) => setStyleForm({ ...styleForm, glossary: event.target.value })}
                  />
                  {jsonErrors.glossary && <span className="world-error">{jsonErrors.glossary}</span>}
                </label>
                <label>
                  Ограничения (JSON)
                  <textarea
                    rows={3}
                    value={styleForm.constraints}
                    onChange={(event) => setStyleForm({ ...styleForm, constraints: event.target.value })}
                  />
                  {jsonErrors.constraints && <span className="world-error">{jsonErrors.constraints}</span>}
                </label>
                <label>
                  Формат диалога (JSON)
                  <textarea
                    rows={3}
                    value={styleForm.dialogue_format}
                    onChange={(event) => setStyleForm({ ...styleForm, dialogue_format: event.target.value })}
                  />
                  {jsonErrors.dialogue_format && (
                    <span className="world-error">{jsonErrors.dialogue_format}</span>
                  )}
                </label>
                <label>
                  Формат документа (JSON)
                  <textarea
                    rows={3}
                    value={styleForm.document_format}
                    onChange={(event) => setStyleForm({ ...styleForm, document_format: event.target.value })}
                  />
                  {jsonErrors.document_format && (
                    <span className="world-error">{jsonErrors.document_format}</span>
                  )}
                </label>
                <label>
                  Тема интерфейса (JSON)
                  <textarea
                    rows={3}
                    value={styleForm.ui_theme}
                    onChange={(event) => setStyleForm({ ...styleForm, ui_theme: event.target.value })}
                  />
                  {jsonErrors.ui_theme && <span className="world-error">{jsonErrors.ui_theme}</span>}
                </label>
                </div>
              </div>

              <div className="world-panel world-panel-wide">
                <div className="world-panel-header">
                  <h2>Параметры генерации</h2>
                  <div className="world-panel-actions">
                    <button className="secondary" type="button" onClick={openStyleProfileAIFill}>AI заполнение</button>
                    <button
                      className="secondary"
                      type="button"
                      onClick={handleInstallLegalStylePack}
                      disabled={!projectId || installingLegalStylePack || creatingStyleProfile}
                      title="Создать набор юридических профилей стиля (рекомендуемые пресеты)"
                    >
                      {installingLegalStylePack ? "Установка..." : "Установить юридический пакет"}
                    </button>
                    <button
                      className="primary"
                      onClick={() => handleApplyStyleProfile(activeStyleProfileId)}
                      disabled={!projectId || creatingStyleProfile}
                      title="Применить выбранный профиль стиля к проекту"
                    >
                      {creatingStyleProfile ? "Применение..." : "Применить"}
                    </button>
                  </div>
                </div>

                <div className="world-form world-form-grid">
                  <label>
                    Активный профиль стиля
                    <select
                      value={activeStyleProfileId}
                      onChange={(e) => setActiveStyleProfileId(e.target.value)}
                    >
                      <option value="">(Нет / первый доступный)</option>
                      {styleProfiles.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <div style={{ gridColumn: "1 / -1" }}>
                    <div className="muted" style={{ marginBottom: 8 }}>
                      Эти настройки используются как глобальные по умолчанию для генерации сцен и наборов референсов
                      локаций/персонажей внутри проекта.
                    </div>
                  </div>

                  <label>
                    Название нового профиля
                    <input
                      value={styleProfileForm.name}
                      onChange={(e) => setStyleProfileForm({ ...styleProfileForm, name: e.target.value })}
                      placeholder="например, Кино / юридическая иллюстрация"
                    />
                  </label>

                  <label>
                    Разрешение
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <input
                        type="number"
                        value={styleProfileForm.width}
                        onChange={(e) => setStyleProfileForm({ ...styleProfileForm, width: Number(e.target.value) })}
                        style={{ width: 110 }}
                      />
                      ×
                      <input
                        type="number"
                        value={styleProfileForm.height}
                        onChange={(e) => setStyleProfileForm({ ...styleProfileForm, height: Number(e.target.value) })}
                        style={{ width: 110 }}
                      />
                    </div>
                  </label>

                  <label>
                    Шаги
                    <input
                      type="number"
                      value={styleProfileForm.steps}
                      onChange={(e) => setStyleProfileForm({ ...styleProfileForm, steps: Number(e.target.value) })}
                    />
                  </label>

                  <label>
                    CFG scale
                    <input
                      type="number"
                      value={styleProfileForm.cfg_scale}
                      onChange={(e) => setStyleProfileForm({ ...styleProfileForm, cfg_scale: Number(e.target.value) })}
                    />
                  </label>

                  <label style={{ gridColumn: "1 / -1" }}>
                    Базовый промпт
                    <textarea
                      rows={3}
                      value={styleProfileForm.base_prompt}
                      onChange={(e) => setStyleProfileForm({ ...styleProfileForm, base_prompt: e.target.value })}
                      placeholder="Глобальные теги стиля (например, clean vector illustration, cinematic lighting...)"
                    />
                  </label>

                  <label style={{ gridColumn: "1 / -1" }}>Негативный промпт<textarea
                      rows={2}
                      value={styleProfileForm.negative_prompt}
                      onChange={(e) => setStyleProfileForm({ ...styleProfileForm, negative_prompt: e.target.value })}
                      placeholder="Что исключить (например, extra fingers, watermark...)"
                    />
                  </label>

                  <div style={{ gridColumn: "1 / -1", display: "flex", gap: 8, alignItems: "center" }}>
                    <button
                      className="secondary"
                      onClick={handleCreateGenerationProfile}
                      disabled={!projectId || creatingStyleProfile}
                      title="Создать профиль стиля и сделать активным"
                    >
                      {creatingStyleProfile ? "Выполняется..." : "Создать и активировать"}
                    </button>
                    <button
                      className="secondary"
                      onClick={async () => {
                        if (!projectId) return;
                        const profiles = await listStyleProfiles(projectId).catch(() => []);
                        setStyleProfiles(profiles);
                      }}
                      disabled={!projectId || creatingStyleProfile}
                    >
                      Обновить список
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      </div>

      {/* Quick Create Modal */}
      {aiFillModal && (
        <AIFillModal
          title={aiFillModal.title}
          formType={aiFillModal.formType}
          fields={aiFillModal.fields}
          currentValues={aiFillModal.currentValues}
          context={aiFillModal.context}
          onApply={aiFillModal.onApply}
          onClose={() => setAiFillModal(null)}
        />
      )}
      {quickCreateType && (
        <QuickCreateModal
          type={quickCreateType}
          onClose={() => setQuickCreateType(null)}
          onCreate={handleQuickCreate}
        />
      )}
      {wizardType && (
        <AssetWizardModal
          key={wizardType}
          type={wizardType}
          onClose={() => setWizardType(null)}
          onCreate={handleWizardCreate}
        />
      )}
      {importModal ? (
        <ImportAssetModal
          title={`Импорт ${IMPORT_TYPE_LABELS[importModal.type]} из студии`}
          note={importModal.note}
          items={importModal.items}
          onImport={handleImportAsset}
          onClose={() => setImportModal(null)}
        />
      ) : null}

      {lightbox ? (
        <ImageLightbox
          url={lightbox.url}
          title={lightbox.title}
          subtitle={lightbox.subtitle}
          onClose={() => setLightbox(null)}
        />
      ) : null}
    </div>
  );
}
