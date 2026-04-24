import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useEdgesState,
  useNodesState,
  addEdge,
  Connection,
  Edge as FlowEdge,
  Node as FlowNode,
  MarkerType,
  NodeProps,
  Position,
  ReactFlowInstance,
} from "reactflow";
import "reactflow/dist/style.css";
import "./GraphEditorPage.css";

import { createEdge, createScene, getGraph, updateEdge, updateScene, validateGraph } from "../api/scenario";
import { createAssetGenerationJob, getSceneImages, generateSceneImage, approveSceneImage, deleteSceneImage } from "../api/generation";
import {
  getCharacterPreset,
  listCharacterPresets,
  listProjectCharacters,
  importCharacterPreset,
  updateCharacterPreset,
} from "../api/characters";
import { listSceneCharacters } from "../api/sceneCharacters";
import {
  getLocation,
  importLocation,
  listLocations,
  listStudioLocations,
  updateLocation,
} from "../api/world";
import SceneEditorPanel from "../components/SceneEditorPanel";
import { ImageLightbox } from "../components/ImageLightbox";
import AIFillModal from "../components/AIFillModal";
import SceneSequenceEditor from "../components/SceneSequenceEditor";
import QuestPreviewModal from "../components/QuestPreviewModal";
import type { AIFieldSpec } from "../api/ai";
import { trackEvent } from "../utils/tracker";
import { waitForGenerationJob } from "../utils/waitForGenerationJob";
import { useGenerationJobStore } from "../hooks/useGenerationJobStore";
import { CREATIVE_CHARACTER_REFERENCE_KINDS, REQUIRED_CHARACTER_REFERENCE_KINDS } from "../shared/characterReferences";
import { getProjectDevelopmentMode } from "../utils/projectDevelopmentMode";
import { getGenerationEnvironment, setGenerationEnvironment } from "../utils/generationEnvironment";
import { getAssetUrl } from "../api/client";
import type {
  Edge,
  ImageVariant,
  Location,
  SceneNode,
  SceneSequence,
  ScenarioGraph,
  SceneNodeCharacter,
  GraphValidationReport,
  CharacterPreset,
} from "../shared/types";

type SceneFormState = {
  title: string;
  content: string;
  synopsis: string;
  scene_type: "story" | "decision";
};

type AssetQueueItem = {
  id: string;
  kind: "character" | "location" | "scene";
  entityId: string;
  label: string;
  status: "queued" | "running" | "done" | "failed";
  jobId?: string | null;
  stage?: string | null;
  progress?: number | null;
  error?: string | null;
};

type AssetEditState =
  | {
      kind: "character";
      item: CharacterPreset;
      draft: {
        name: string;
        description: string;
        appearance_prompt: string;
        negative_prompt: string;
        style_tags: string;
        voice_profile: string;
        motivation: string;
        legal_status: string;
      };
    }
  | {
      kind: "location";
      item: Location;
      draft: {
        name: string;
        description: string;
        visual_reference: string;
        negative_prompt: string;
        tags: string;
      };
    };

type AIFillConfig = {
  title: string;
  formType: string;
  fields: AIFieldSpec[];
  currentValues: Record<string, unknown>;
  context?: string;
  onApply: (values: Record<string, unknown>) => void;
};

const SCENE_AI_FIELDS: AIFieldSpec[] = [
  { key: "title", label: "Заголовок", type: "string" },
  { key: "synopsis", label: "Синопсис", type: "string" },
  { key: "content", label: "Содержание", type: "string" },
  { key: "scene_type", label: "Тип сцены", type: "string", options: ["story", "decision"] },
];

const CHARACTER_ASSET_FIELDS: AIFieldSpec[] = [
  { key: "name", label: "Имя", type: "string" },
  { key: "description", label: "Описание", type: "string" },
  { key: "appearance_prompt", label: "Промпт внешности", type: "string" },
  { key: "negative_prompt", label: "Негативный промпт", type: "string" },
  { key: "style_tags", label: "Теги стиля", type: "array" },
  { key: "voice_profile", label: "Голосовой профиль", type: "string" },
  { key: "motivation", label: "Мотивация", type: "string" },
  { key: "legal_status", label: "Правовой статус", type: "string" },
];

const LOCATION_ASSET_FIELDS: AIFieldSpec[] = [
  { key: "name", label: "Название", type: "string" },
  { key: "description", label: "Описание", type: "string" },
  { key: "visual_reference", label: "Визуальный референс", type: "string" },
  { key: "negative_prompt", label: "Негативный промпт", type: "string" },
  { key: "tags", label: "Теги", type: "array" },
];

type SceneNodeData = {
  title: string;
  sceneType: "story" | "decision";
  summary: string;
  locationName?: string;
  onSelect?: () => void;
};

type AutoDerivedEdge = {
  id: string;
  from_scene_id: string;
  to_scene_id: string;
  choice_label: string;
  condition: string | null;
  edge_metadata: Record<string, unknown>;
  auto_reason: "linear_order";
};

type GraphFlowEdgeData = {
  persisted: boolean;
  autoReason?: "linear_order";
  condition?: string | null;
  choiceValue?: string;
};

type GraphFlowEdge = FlowEdge<GraphFlowEdgeData>;
type AssetActionIconName = "edit" | "ai" | "queue" | "import" | "open";

const GRAPH_LAYOUT_KEY = "lwq_graph_layout";
const GRAPH_SELECTED_KEY = "lwq_graph_selected";
const REQUIRED_LOCATION_REFERENCE_KINDS = ["exterior", "interior", "detail", "map"];

const makeQueueId = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `asset_${Date.now()}_${Math.random().toString(16).slice(2)}`;
};

const formatAssetError = (error?: string | null) => {
  if (!error) return null;
  const text = String(error);
  const lower = text.toLowerCase();
  if (
    lower.includes("content_moderated") ||
    lower.includes("content moderated") ||
    lower.includes("safety filter") ||
    lower.includes("moderation")
  ) {
    let reason = "";
    const parts = text.split(":");
    if (parts.length > 1) {
      reason = parts.slice(1).join(":").trim();
    }
    const suffix = reason ? ` Причина: ${reason}.` : "";
    return `Заблокировано модерацией. Проверьте описание и попробуйте снова.${suffix}`;
  }
  return text;
};

const SceneNodeCard: React.FC<NodeProps<SceneNodeData>> = ({ data, selected }) => {
  return (
    <div className={`scene-node ${data.sceneType} ${selected ? "selected" : ""}`} onClick={data.onSelect}>
      <div className="scene-node__header">
        <span className="scene-node__title">{data.title}</span>
        <span className="scene-node__badge">{data.sceneType === "decision" ? "Выбор" : "Сцена"}</span>
      </div>
      {data.locationName && <div className="scene-node__meta">{data.locationName}</div>}
      {data.summary && <div className="scene-node__content">{data.summary}</div>}
    </div>
  );
};

function AssetActionIcon({ name }: { name: AssetActionIconName }) {
  if (name === "edit") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3 17.25V21h3.75L18.8 8.95l-3.75-3.75L3 17.25z" />
        <path d="M14.96 4.04l3.75 3.75" />
      </svg>
    );
  }
  if (name === "ai") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3l1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8L12 3z" />
        <path d="M19 14l.9 2.1L22 17l-2.1.9L19 20l-.9-2.1L16 17l2.1-.9L19 14z" />
      </svg>
    );
  }
  if (name === "queue") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 6h10" />
        <path d="M4 12h10" />
        <path d="M4 18h10" />
        <path d="M18 10v8" />
        <path d="M14 14h8" />
      </svg>
    );
  }
  if (name === "import") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3v10" />
        <path d="M8 9l4 4 4-4" />
        <path d="M4 15v5h16v-5" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M14 3h7v7" />
      <path d="M10 14L21 3" />
      <path d="M20 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h5" />
    </svg>
  );
}

function readLayout(graphId?: string | null) {
  if (!graphId) return null;
  const raw = localStorage.getItem(`${GRAPH_LAYOUT_KEY}_${graphId}`);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Record<string, { x: number; y: number }>;
  } catch {
    return null;
  }
}

function readSelectedScene(graphId?: string | null) {
  if (!graphId) return null;
  return localStorage.getItem(`${GRAPH_SELECTED_KEY}_${graphId}`);
}

export default function GraphEditorPage() {
  const { graphId, projectId } = useParams<{ graphId: string; projectId: string }>();
  const navigate = useNavigate();
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null);
  const [graph, setGraph] = useState<ScenarioGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [sceneForm, setSceneForm] = useState<SceneFormState>({
    title: "",
    content: "",
    synopsis: "",
    scene_type: "story",
  });
  const [viewMode, setViewMode] = useState<"writer" | "graph">("writer");
  const [sideCollapsed, setSideCollapsed] = useState(false);
  const [writerForm, setWriterForm] = useState<SceneFormState>({
    title: "",
    content: "",
    synopsis: "",
    scene_type: "story",
  });
  const [writerSaving, setWriterSaving] = useState(false);
  const [reordering, setReordering] = useState(false);
  const [choiceForm, setChoiceForm] = useState({
    label: "Продолжить",
    targetId: "",
    value: "",
    condition: "",
  });
  const [creatingScene, setCreatingScene] = useState(false);
  const [selectedScene, setSelectedScene] = useState<SceneNode | null>(null);
  const [images, setImages] = useState<ImageVariant[]>([]);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [sceneCharacters, setSceneCharacters] = useState<SceneNodeCharacter[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [sceneFilter, setSceneFilter] = useState<"all" | "story" | "decision">("all");
  const [aiFillModal, setAiFillModal] = useState<AIFillConfig | null>(null);
  const [validationReport, setValidationReport] = useState<GraphValidationReport | null>(null);
  const [validating, setValidating] = useState(false);
  const [sequenceSaving, setSequenceSaving] = useState(false);
  const [edgeDrafts, setEdgeDrafts] = useState<
    Record<string, { label: string; value: string; condition: string }>
  >({});
  const [projectCharacters, setProjectCharacters] = useState<CharacterPreset[]>([]);
  const [projectLocations, setProjectLocations] = useState<Location[]>([]);
  const [libraryCharacters, setLibraryCharacters] = useState<CharacterPreset[]>([]);
  const [libraryLocations, setLibraryLocations] = useState<Location[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [useLibraryAssets, setUseLibraryAssets] = useState(true);
  const [sceneCharacterMap, setSceneCharacterMap] = useState<Record<string, SceneNodeCharacter[]>>({});
  const [assetsLoading, setAssetsLoading] = useState(false);
  const [assetsError, setAssetsError] = useState<string | null>(null);
  const [assetQueue, setAssetQueue] = useState<AssetQueueItem[]>([]);
  const [assetQueuePaused, setAssetQueuePaused] = useState(false);
  const [assetEdit, setAssetEdit] = useState<AssetEditState | null>(null);
  const [assetEditSaving, setAssetEditSaving] = useState(false);
  const [questPreviewOpen, setQuestPreviewOpen] = useState(false);
  const [questPreviewStartSceneId, setQuestPreviewStartSceneId] = useState<string | null>(null);
  const [projectMode, setProjectMode] = useState<"creative" | "standard">(() => getProjectDevelopmentMode(projectId));
  const sequenceSaveVersionRef = useRef(0);
  const sequenceSavePendingRef = useRef(0);
  const latestSequenceRef = useRef<SceneSequence | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState<SceneNodeData>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<GraphFlowEdge>([]);
  const [autoDerivedEdges, setAutoDerivedEdges] = useState<AutoDerivedEdge[]>([]);
  const [persistingAutoEdges, setPersistingAutoEdges] = useState(false);
  const upsertJob = useGenerationJobStore((s) => s.upsert);
  const isCreativeMode = projectMode === "creative";
  const requiredCharacterReferenceKinds = isCreativeMode
    ? [...CREATIVE_CHARACTER_REFERENCE_KINDS]
    : REQUIRED_CHARACTER_REFERENCE_KINDS;
  const requiredLocationReferenceKinds = isCreativeMode ? [] : REQUIRED_LOCATION_REFERENCE_KINDS;

  useEffect(() => {
    if (graphId) loadGraph();
  }, [graphId]);

  useEffect(() => {
    setProjectMode(getProjectDevelopmentMode(projectId));
  }, [projectId]);

  useEffect(() => {
    if (!isCreativeMode) return;
    if (getGenerationEnvironment() === "local") {
      setGenerationEnvironment("comfy_api");
    }
  }, [isCreativeMode]);

  useEffect(() => {
    if (!projectId) return;
    setAssetsLoading(true);
    setAssetsError(null);
    Promise.all([listProjectCharacters(projectId), listLocations(projectId)])
      .then(([characters, locations]) => {
        setProjectCharacters(characters);
        setProjectLocations(locations);
      })
      .catch((error) => {
        console.error("Failed to load project assets", error);
        setAssetsError("Не удалось загрузить ассеты проекта.");
      })
      .finally(() => setAssetsLoading(false));
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !useLibraryAssets) return;
    setLibraryLoading(true);
    setLibraryError(null);
    Promise.all([
      listCharacterPresets().catch(() => []),
      listStudioLocations().catch(() => []),
    ])
      .then(([characters, locations]) => {
        setLibraryCharacters(characters);
        setLibraryLocations(locations);
      })
      .catch((error) => {
        console.error("Failed to load library assets", error);
        setLibraryError("Не удалось загрузить библиотеку ассетов.");
      })
      .finally(() => setLibraryLoading(false));
  }, [projectId, useLibraryAssets]);

  useEffect(() => {
    if (graph) {
      buildFlow(graph.scenes, graph.edges, { autoLayout: nodes.length === 0 });
    }
  }, [graph, nodes.length]);

  useEffect(() => {
    if (!graph?.scenes?.length) return;
    let cancelled = false;
    Promise.all(
      graph.scenes.map((scene) =>
        listSceneCharacters(scene.id).catch((error) => {
          console.error("Failed to load scene characters", scene.id, error);
          return [];
        }),
      ),
    ).then((results) => {
      if (cancelled) return;
      const next: Record<string, SceneNodeCharacter[]> = {};
      graph.scenes.forEach((scene, idx) => {
        next[scene.id] = results[idx] || [];
      });
      setSceneCharacterMap(next);
    });
    return () => {
      cancelled = true;
    };
  }, [graph?.scenes]);

  useEffect(() => {
    if (!jobId || !selectedScene) return;
    void waitForGenerationJob(jobId, {
      intervalMs: 2000,
      maxAttempts: 120,
      onUpdate: (job) => setJobStatus(job.status),
    }).then((job) => {
      if (job.status === "done" || job.status === "failed") {
        loadSceneAssets(selectedScene.id).catch(error => {
          console.error("Failed to load scene assets after generation", error);
        });
        trackEvent("generation_finished", { sceneId: selectedScene.id, jobId, status: job.status });
      }
    });
  }, [jobId, selectedScene]);

  useEffect(() => {
    if (!graphId || nodes.length === 0) return;
    const layout = nodes.reduce<Record<string, { x: number; y: number }>>((acc, node) => {
      acc[node.id] = { x: node.position.x, y: node.position.y };
      return acc;
    }, {});
    localStorage.setItem(`${GRAPH_LAYOUT_KEY}_${graphId}`, JSON.stringify(layout));
  }, [nodes, graphId]);

  useEffect(() => {
    if (!graphId || !selectedScene) return;
    localStorage.setItem(`${GRAPH_SELECTED_KEY}_${graphId}`, selectedScene.id);
  }, [selectedScene, graphId]);

  useEffect(() => {
    if (!selectedScene) return;
    setSceneCharacterMap((prev) => ({ ...prev, [selectedScene.id]: sceneCharacters }));
  }, [selectedScene?.id, sceneCharacters]);

  useEffect(() => {
    if (!selectedScene) {
      setWriterForm({ title: "", content: "", synopsis: "", scene_type: "story" });
      setChoiceForm({ label: "Продолжить", targetId: "", value: "", condition: "" });
      return;
    }
    setWriterForm({
      title: selectedScene.title,
      content: selectedScene.content,
      synopsis: selectedScene.synopsis || "",
      scene_type: selectedScene.scene_type,
    });
    setChoiceForm({
      label: selectedScene.scene_type === "decision" ? "Выбор" : "Продолжить",
      targetId: "",
      value: "",
      condition: "",
    });
  }, [selectedScene?.id]);

  function loadGraph() {
    setLoading(true);
    getGraph(graphId!).then(data => {
      setGraph(data);
      trackEvent("graph_loaded", { graphId });
      const preferredSceneId = readSelectedScene(graphId);
      const initialScene =
        data.scenes.find((scene) => scene.id === preferredSceneId) ?? data.scenes[0] ?? null;
      if (initialScene) {
        setSelectedScene(initialScene);
        // Load scene assets asynchronously without blocking
        loadSceneAssets(initialScene.id).catch(error => {
          console.error("Failed to load scene assets", error);
        });
      }
    }).catch(error => {
      console.error("Failed to load graph", error);
    }).finally(() => {
      setLoading(false);
    });
  }

  function loadSceneAssets(sceneId: string) {
    setJobId(null);
    setJobStatus(null);
    
    return getSceneImages(sceneId).then(variants => {
      setImages(variants);
      return listSceneCharacters(sceneId);
    }).then(chars => {
      setSceneCharacters(chars);
      setSceneCharacterMap((prev) => ({ ...prev, [sceneId]: chars }));
    }).catch(error => {
      console.error("Failed to load scene assets", error);
    });
  }

  const buildSceneContext = (form: SceneFormState, mode: "new" | "edit") => {
    const parts = [
      graph?.title ? `graph: ${graph.title}` : null,
      graph?.description ? `graph description: ${graph.description}` : null,
      selectedScene?.title ? `selected scene: ${selectedScene.title}` : null,
      selectedScene?.synopsis ? `selected synopsis: ${selectedScene.synopsis}` : null,
      selectedScene?.content ? `selected content: ${selectedScene.content}` : null,
      selectedScene?.location?.name ? `selected location: ${selectedScene.location.name}` : null,
      sceneCharacters.length ? `linked characters: ${sceneCharacters.length}` : null,
      form.title ? `draft title: ${form.title}` : null,
      form.synopsis ? `draft synopsis: ${form.synopsis}` : null,
      form.content ? `draft content: ${form.content}` : null,
      `mode: ${mode}`,
    ].filter(Boolean);
    return parts.join("\n");
  };

  const openSceneAIFill = (mode: "new" | "edit") => {
    const form = mode === "new" ? sceneForm : writerForm;
    setAiFillModal({
      title: mode === "new" ? "Новая сцена" : "Редактор сцены",
      formType: "scene",
      fields: SCENE_AI_FIELDS,
      currentValues: {
        title: form.title,
        synopsis: form.synopsis,
        content: form.content,
        scene_type: form.scene_type,
      },
      context: buildSceneContext(form, mode),
      onApply: (values) => {
        const title = typeof values.title === "string" ? values.title : form.title;
        const synopsis = typeof values.synopsis === "string" ? values.synopsis : form.synopsis;
        const content = typeof values.content === "string" ? values.content : form.content;
        const sceneType =
          values.scene_type === "story" || values.scene_type === "decision"
            ? values.scene_type
            : form.scene_type;

        const nextForm = { title, synopsis, content, scene_type: sceneType };
        if (mode === "new") {
          setSceneForm(nextForm);
        } else {
          setWriterForm(nextForm);
        }
      },
    });
  };

  const characterById = useMemo(
    () => new Map(projectCharacters.map((character) => [character.id, character])),
    [projectCharacters],
  );

  const locationById = useMemo(
    () => new Map(projectLocations.map((location) => [location.id, location])),
    [projectLocations],
  );

  const getReferenceKinds = useCallback((items?: { kind?: string }[] | null) => {
    const refs = Array.isArray(items) ? items : [];
    const kinds = refs
      .map((ref) => (ref && typeof ref === "object" ? ref.kind : undefined))
      .filter((kind): kind is string => Boolean(kind));
    return new Set(kinds);
  }, []);

  const characterReferenceStatus = useMemo(() => {
    const map = new Map<string, { missing: string[]; ready: boolean }>();
    projectCharacters.forEach((character) => {
      const kinds = getReferenceKinds(character.reference_images || []);
      const missing = requiredCharacterReferenceKinds.filter((kind) => !kinds.has(kind));
      map.set(character.id, { missing, ready: missing.length === 0 });
    });
    return map;
  }, [projectCharacters, getReferenceKinds, requiredCharacterReferenceKinds]);

  const locationReferenceStatus = useMemo(() => {
    const map = new Map<string, { missing: string[]; ready: boolean }>();
    projectLocations.forEach((location) => {
      const kinds = getReferenceKinds(location.reference_images || []);
      const missing = requiredLocationReferenceKinds.filter((kind) => !kinds.has(kind));
      map.set(location.id, { missing, ready: missing.length === 0 });
    });
    return map;
  }, [projectLocations, getReferenceKinds, requiredLocationReferenceKinds]);

  const sceneCastMap = useMemo(() => {
    const map = new Map<string, Set<string>>();
    (graph?.scenes || []).forEach((scene) => {
      const cast = new Set<string>();
      const slides = scene.context?.sequence?.slides;
      if (Array.isArray(slides)) {
        slides.forEach((slide) => {
          if (!Array.isArray(slide.cast_ids)) return;
          slide.cast_ids.forEach((id) => {
            if (id) cast.add(id);
          });
        });
      }
      (sceneCharacterMap[scene.id] || []).forEach((link) => {
        if (link.in_frame === false) return;
        if (link.character_preset_id) cast.add(link.character_preset_id);
      });
      map.set(scene.id, cast);
    });
    return map;
  }, [graph?.scenes, sceneCharacterMap]);

  const sceneAssetStatus = useMemo(() => {
    const map = new Map<
      string,
      {
        blocked: boolean;
        reason: string;
        missingCharacters: string[];
        missingLocations: string[];
      }
    >();
    (graph?.scenes || []).forEach((scene) => {
      const castIds = Array.from(sceneCastMap.get(scene.id) || []);
      const missingCharacters = castIds.filter((id) => !characterReferenceStatus.get(id)?.ready);
      const locationId = scene.location_id || scene.location?.id || null;
      const locationMissing = locationId
        ? !isCreativeMode && !locationReferenceStatus.get(locationId)?.ready
        : false;
      const missingLocations = locationMissing ? [locationId as string] : [];

      const reasonParts: string[] = [];
      if (missingCharacters.length) {
        const names = missingCharacters
          .map((id) => characterById.get(id)?.name || id)
          .join(", ");
        reasonParts.push(`нет рефов персонажей: ${names}`);
      }
      if (locationMissing && locationId) {
        reasonParts.push(`нет рефов локации: ${locationById.get(locationId)?.name || locationId}`);
      }

      map.set(scene.id, {
        blocked: missingCharacters.length > 0 || locationMissing,
        reason: reasonParts.join("; "),
        missingCharacters,
        missingLocations,
      });
    });
    return map;
  }, [graph?.scenes, sceneCastMap, characterReferenceStatus, locationReferenceStatus, characterById, locationById, isCreativeMode]);

  const selectedSceneAssetStatus = useMemo(() => {
    if (!selectedScene) return null;
    return sceneAssetStatus.get(selectedScene.id) || null;
  }, [sceneAssetStatus, selectedScene]);

  const getEdgeChoiceValue = useCallback((edge: Pick<Edge, "edge_metadata">) => {
    const raw = edge.edge_metadata?.choice_value;
    if (typeof raw === "string") return raw.trim();
    if (raw === null || raw === undefined) return "";
    return String(raw).trim();
  }, []);

  const getEdgeLabel = useCallback(
    (edge: Pick<Edge, "choice_label" | "condition" | "edge_metadata">) => {
      const explicit = (edge.choice_label || "").trim();
      if (explicit) return explicit;
      const value = getEdgeChoiceValue(edge);
      if (value) return value;
      const condition = (edge.condition || "").trim();
      if (condition) return `if ${condition}`;
      return "Далее";
    },
    [getEdgeChoiceValue],
  );

  const buildAutoDerivedEdges = useCallback((scenes: SceneNode[], edgesData: Edge[]): AutoDerivedEdge[] => {
    if (scenes.length < 2) return [];
    const sortedScenes = [...scenes].sort((a, b) => {
      const orderDiff =
        (a.order_index ?? Number.MAX_SAFE_INTEGER) - (b.order_index ?? Number.MAX_SAFE_INTEGER);
      if (orderDiff !== 0) return orderDiff;
      return a.title.localeCompare(b.title);
    });
    const outgoingCount = new Map<string, number>();
    const existingPairs = new Set<string>();
    edgesData.forEach((edge) => {
      outgoingCount.set(edge.from_scene_id, (outgoingCount.get(edge.from_scene_id) || 0) + 1);
      existingPairs.add(`${edge.from_scene_id}->${edge.to_scene_id}`);
    });

    const derived: AutoDerivedEdge[] = [];
    for (let idx = 0; idx < sortedScenes.length - 1; idx += 1) {
      const fromScene = sortedScenes[idx];
      const toScene = sortedScenes[idx + 1];
      if (!fromScene?.id || !toScene?.id) continue;
      if ((outgoingCount.get(fromScene.id) || 0) > 0) continue;
      const pairKey = `${fromScene.id}->${toScene.id}`;
      if (existingPairs.has(pairKey)) continue;
      derived.push({
        id: `__auto_order__${fromScene.id}__${toScene.id}`,
        from_scene_id: fromScene.id,
        to_scene_id: toScene.id,
        choice_label: "Далее",
        condition: null,
        edge_metadata: { auto_source: "order", auto_generated: true },
        auto_reason: "linear_order",
      });
    }
    return derived;
  }, []);

  const toFlowEdge = useCallback(
    (
      edge: Pick<Edge, "id" | "from_scene_id" | "to_scene_id" | "choice_label" | "condition" | "edge_metadata">,
      opts: { persisted: boolean; autoReason?: "linear_order" } = { persisted: true },
    ): GraphFlowEdge => {
      const persisted = opts.persisted;
      const choiceValue = getEdgeChoiceValue(edge);
      return {
        id: edge.id,
        source: edge.from_scene_id,
        target: edge.to_scene_id,
        label: getEdgeLabel(edge),
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 18,
          height: 18,
          color: persisted ? "#38bdf8" : "#fbbf24",
        },
        animated: !persisted,
        style: {
          stroke: persisted ? "#38bdf8" : "#fbbf24",
          strokeWidth: persisted ? 2.2 : 1.8,
          opacity: 0.96,
          ...(persisted ? {} : { strokeDasharray: "6 6" }),
        },
        labelStyle: {
          fill: "#e5e7eb",
          fontSize: 11,
          fontWeight: 600,
        },
        labelBgPadding: [8, 4],
        labelBgBorderRadius: 6,
        labelBgStyle: {
          fill: "rgba(2, 6, 23, 0.95)",
          fillOpacity: 0.92,
          stroke: persisted ? "rgba(56, 189, 248, 0.45)" : "rgba(251, 191, 36, 0.45)",
          strokeWidth: 1,
        },
        data: {
          persisted,
          autoReason: opts.autoReason,
          condition: edge.condition || null,
          choiceValue: choiceValue || undefined,
        },
        selectable: true,
        deletable: persisted,
      };
    },
    [getEdgeChoiceValue, getEdgeLabel],
  );

  function buildFlow(
    scenes: SceneNode[],
    edgesData: Edge[],
    opts?: { autoLayout?: boolean; ignoreSaved?: boolean },
  ) {
    const prevPositions = new Map(nodes.map((n) => [n.id, n.position]));
    const layoutPositions = opts?.autoLayout ? computeLayoutPositions(scenes, edgesData) : null;
    const savedPositions = opts?.ignoreSaved ? null : readLayout(graphId);
    const flowNodes: FlowNode<SceneNodeData>[] = scenes.map((scene, idx) => {
      const summary = (scene.synopsis || scene.content || "").slice(0, 80);
      return {
        id: scene.id,
        type: "scene",
        data: {
          title: scene.title,
          sceneType: scene.scene_type,
          summary,
          locationName: scene.location?.name,
          onSelect: () => {
            setSelectedScene(scene);
            void loadSceneAssets(scene.id);
          },
        },
        position:
          savedPositions?.[scene.id] ??
          layoutPositions?.[scene.id] ??
          prevPositions.get(scene.id) ?? {
            x: (idx % 4) * 260,
            y: Math.floor(idx / 4) * 180,
          },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      };
    });
    const sceneIds = new Set(scenes.map((scene) => scene.id));
    const persistedEdges = edgesData
      .filter((edge) => sceneIds.has(edge.from_scene_id) && sceneIds.has(edge.to_scene_id))
      .map((edge) => toFlowEdge(edge, { persisted: true }));
    const derivedEdges = buildAutoDerivedEdges(scenes, edgesData);
    const virtualEdges = derivedEdges.map((edge) =>
      toFlowEdge(edge, { persisted: false, autoReason: edge.auto_reason }),
    );
    setNodes(flowNodes);
    setEdges([...persistedEdges, ...virtualEdges]);
    setAutoDerivedEdges(derivedEdges);
  }

  function computeLayoutPositions(scenes: SceneNode[], edgesData: Edge[]) {
    const positions: Record<string, { x: number; y: number }> = {};
    const children = new Map<string, string[]>();
    edgesData.forEach((e) => {
      children.set(e.from_scene_id, [...(children.get(e.from_scene_id) ?? []), e.to_scene_id]);
    });
    const visited = new Set<string>();
    const depths = new Map<string, number>();
    const rootId = graph?.root_scene_id ?? scenes[0]?.id ?? null;
    const queue: string[] = [];
    if (rootId) {
      queue.push(rootId);
      visited.add(rootId);
      depths.set(rootId, 0);
    }
    while (queue.length > 0) {
      const current = queue.shift()!;
      const depth = depths.get(current) ?? 0;
      const next = children.get(current) ?? [];
      next.forEach((child) => {
        if (!visited.has(child)) {
          visited.add(child);
          depths.set(child, depth + 1);
          queue.push(child);
        }
      });
    }
    scenes.forEach((scene) => {
      if (!visited.has(scene.id)) {
        visited.add(scene.id);
        depths.set(scene.id, 0);
      }
    });
    const levels: Record<number, string[]> = {};
    depths.forEach((depth, id) => {
      levels[depth] = levels[depth] ? [...levels[depth], id] : [id];
    });
    const xGap = 280;
    const yGap = 170;
    Object.entries(levels).forEach(([depthStr, ids]) => {
      const depth = Number(depthStr);
      ids.forEach((id, idx) => {
        positions[id] = { x: depth * xGap, y: idx * yGap };
      });
    });
    return positions;
  }

  function handleCreateScene() {
    if (!graphId || !sceneForm.title.trim()) return;
    
    setCreatingScene(true);
    const content = sceneForm.content.trim() || "Опишите, что происходит в этой сцене.";
    
    // Root cause: await call blocks UI thread during scene creation
    // Fix: Use Promise-based approach for non-blocking creation
    createScene(graphId, {
      ...sceneForm,
      content,
      synopsis: sceneForm.synopsis || null,
    })
    .then(scene => {
      setGraph((prev) =>
        prev
          ? { ...prev, scenes: [...(prev.scenes || []), scene] }
          : prev,
      );
      trackEvent("scene_created", { graphId, sceneId: scene.id });
      setSceneForm({ title: "", content: "", synopsis: "", scene_type: "story" });
      setSelectedScene(scene);
      
      // Load scene assets asynchronously without blocking
      return loadSceneAssets(scene.id);
    })
    .catch(error => {
      console.error("Failed to create scene", error);
    })
    .finally(() => {
      setCreatingScene(false);
    });
  }

  function handleWriterSave() {
    if (!selectedScene) return;
    if (!writerForm.title.trim()) return;
    
    setWriterSaving(true);
    updateScene(selectedScene.id, {
      title: writerForm.title.trim(),
      content: writerForm.content.trim() || "Опишите, что происходит в этой сцене.",
      synopsis: writerForm.synopsis.trim() || null,
      scene_type: writerForm.scene_type,
    }).then(updated => {
      setSelectedScene(updated);
      setGraph((prev) =>
        prev
          ? {
              ...prev,
              scenes: prev.scenes.map((sc) => (sc.id === updated.id ? updated : sc)),
            }
          : prev,
      );
    }).catch(error => {
      console.error("Failed to save scene", error);
    }).finally(() => {
      setWriterSaving(false);
    });
  }

  async function handleSequenceSave(sequence: SceneSequence | null) {
    if (!selectedScene) return;

    latestSequenceRef.current = sequence;
    sequenceSavePendingRef.current += 1;
    const requestVersion = ++sequenceSaveVersionRef.current;
    setSequenceSaving(true);

    const nextContext = { ...(selectedScene.context || {}) };
    if (sequence) {
      nextContext.sequence = sequence;
    } else {
      delete nextContext.sequence;
    }
    const optimisticScene: SceneNode = {
      ...selectedScene,
      context: Object.keys(nextContext).length ? nextContext : null,
    };
    setSelectedScene(optimisticScene);
    setGraph((prev) =>
      prev
        ? {
            ...prev,
            scenes: prev.scenes.map((sc) => (sc.id === optimisticScene.id ? optimisticScene : sc)),
          }
        : prev,
    );

    try {
      const updated = await updateScene(selectedScene.id, {
        context: Object.keys(nextContext).length ? nextContext : null,
      });

      if (requestVersion !== sequenceSaveVersionRef.current) return;

      const latestSequence = latestSequenceRef.current;
      const mergedContext = { ...(updated.context || {}) };
      if (latestSequence) {
        mergedContext.sequence = latestSequence;
      } else {
        delete mergedContext.sequence;
      }
      const mergedScene: SceneNode = {
        ...updated,
        context: Object.keys(mergedContext).length ? mergedContext : null,
      };
      setSelectedScene(mergedScene);
      setGraph((prev) =>
        prev
          ? {
              ...prev,
              scenes: prev.scenes.map((sc) => (sc.id === mergedScene.id ? mergedScene : sc)),
            }
          : prev,
      );
    } catch (error) {
      console.error("Failed to save sequence", error);
    } finally {
      sequenceSavePendingRef.current = Math.max(0, sequenceSavePendingRef.current - 1);
      if (sequenceSavePendingRef.current === 0) {
        setSequenceSaving(false);
      }
    }
  }

  const refreshCharacter = useCallback(async (characterId: string) => {
    try {
      const updated = await getCharacterPreset(characterId);
      setProjectCharacters((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch (error) {
      console.error("Failed to refresh character", error);
    }
  }, []);

  const refreshLocation = useCallback(async (locationId: string) => {
    try {
      const updated = await getLocation(locationId);
      setProjectLocations((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
    } catch (error) {
      console.error("Failed to refresh location", error);
    }
  }, []);

  const enqueueAssetTasks = useCallback((tasks: AssetQueueItem[]) => {
    if (!tasks.length) return;
    setAssetQueue((prev) => {
      const existingKeys = new Set(
        prev
          .filter((task) => task.status === "queued" || task.status === "running")
          .map((task) => `${task.kind}:${task.entityId}`),
      );
      const next = [...prev];
      tasks.forEach((task) => {
        const key = `${task.kind}:${task.entityId}`;
        if (existingKeys.has(key)) return;
        existingKeys.add(key);
        next.push(task);
      });
      return next;
    });
  }, []);

  const enqueueCharacterTask = useCallback(
    (character: CharacterPreset) => {
      enqueueAssetTasks([
        {
          id: makeQueueId(),
          kind: "character",
          entityId: character.id,
          label: character.name || "Персонаж",
          status: "queued",
        },
      ]);
    },
    [enqueueAssetTasks],
  );

  const enqueueLocationTask = useCallback(
    (location: Location) => {
      enqueueAssetTasks([
        {
          id: makeQueueId(),
          kind: "location",
          entityId: location.id,
          label: location.name || "Локация",
          status: "queued",
        },
      ]);
    },
    [enqueueAssetTasks],
  );

  const enqueueSceneTask = useCallback(
    (scene: SceneNode) => {
      const status = sceneAssetStatus.get(scene.id);
      if (status?.blocked) {
        setAssetsError(status.reason || "Сцена заблокирована для генерации.");
        return;
      }
      enqueueAssetTasks([
        {
          id: makeQueueId(),
          kind: "scene",
          entityId: scene.id,
          label: scene.title || "Сцена",
          status: "queued",
        },
      ]);
    },
    [enqueueAssetTasks, sceneAssetStatus],
  );

  const characterAssets = useMemo(
    () =>
      projectCharacters.map((character) => {
        const status = characterReferenceStatus.get(character.id);
        return {
          character,
          ready: status?.ready ?? false,
          missing: status?.missing ?? requiredCharacterReferenceKinds,
        };
      }),
    [projectCharacters, characterReferenceStatus, requiredCharacterReferenceKinds],
  );

  const locationAssets = useMemo(
    () =>
      projectLocations.map((location) => {
        const status = locationReferenceStatus.get(location.id);
        return {
          location,
          ready: status?.ready ?? false,
          missing: status?.missing ?? requiredLocationReferenceKinds,
        };
      }),
    [projectLocations, locationReferenceStatus, requiredLocationReferenceKinds],
  );

  const libraryCharacterOptions = useMemo(() => {
    const importedSourceIds = new Set(
      projectCharacters.map((item) => item.source_preset_id).filter(Boolean) as string[],
    );
    return libraryCharacters.filter((item) => !importedSourceIds.has(item.id));
  }, [libraryCharacters, projectCharacters]);

  const libraryLocationOptions = useMemo(() => {
    const importedSourceIds = new Set(
      projectLocations.map((item) => item.source_location_id).filter(Boolean) as string[],
    );
    return libraryLocations.filter((item) => !importedSourceIds.has(item.id));
  }, [libraryLocations, projectLocations]);

  const enqueueMissingCharacters = useCallback(() => {
    const tasks = characterAssets
      .filter((item) => !item.ready)
      .map((item) => ({
        id: makeQueueId(),
        kind: "character" as const,
        entityId: item.character.id,
        label: item.character.name || "Персонаж",
        status: "queued" as const,
      }));
    enqueueAssetTasks(tasks);
  }, [characterAssets, enqueueAssetTasks]);

  const enqueueMissingLocations = useCallback(() => {
    const tasks = locationAssets
      .filter((item) => !item.ready)
      .map((item) => ({
        id: makeQueueId(),
        kind: "location" as const,
        entityId: item.location.id,
        label: item.location.name || "Локация",
        status: "queued" as const,
      }));
    enqueueAssetTasks(tasks);
  }, [locationAssets, enqueueAssetTasks]);

  const enqueueReadyScenes = useCallback(() => {
    const scenes = [...(graph?.scenes || [])];
    scenes.sort(
      (a, b) =>
        (a.order_index ?? Number.MAX_SAFE_INTEGER) - (b.order_index ?? Number.MAX_SAFE_INTEGER),
    );
    const tasks = scenes
      .filter((scene) => !sceneAssetStatus.get(scene.id)?.blocked)
      .map((scene) => ({
        id: makeQueueId(),
        kind: "scene" as const,
        entityId: scene.id,
        label: scene.title || "Сцена",
        status: "queued" as const,
      }));
    enqueueAssetTasks(tasks);
  }, [graph?.scenes, sceneAssetStatus, enqueueAssetTasks]);

  const handleImportLibraryCharacter = useCallback(
    async (presetId: string) => {
      if (!projectId) return;
      try {
        const imported = await importCharacterPreset(projectId, presetId);
        setProjectCharacters((prev) => {
          if (prev.find((item) => item.id === imported.id)) return prev;
          return [imported, ...prev];
        });
        setAssetsError(null);
      } catch (error: any) {
        console.error("Failed to import character", error);
        setAssetsError(error?.message || "Не удалось импортировать персонажа.");
      }
    },
    [projectId],
  );

  const handleImportLibraryLocation = useCallback(
    async (locationId: string) => {
      if (!projectId) return;
      try {
        const imported = await importLocation(projectId, locationId);
        setProjectLocations((prev) => {
          if (prev.find((item) => item.id === imported.id)) return prev;
          return [imported, ...prev];
        });
        setAssetsError(null);
      } catch (error: any) {
        console.error("Failed to import location", error);
        setAssetsError(error?.message || "Не удалось импортировать локацию.");
      }
    },
    [projectId],
  );

  useEffect(() => {
    if (assetQueuePaused) return;
    const running = assetQueue.find((task) => task.status === "running");
    if (running) return;
    const next = assetQueue.find((task) => task.status === "queued");
    if (!next) return;

    const updateTask = (patch: Partial<AssetQueueItem>) => {
      setAssetQueue((prev) =>
        prev.map((task) =>
          task.id === next.id
            ? {
                ...task,
                ...patch,
              }
            : task,
        ),
      );
    };

    const normalizeJobProgress = (value: unknown): number | null => {
      if (typeof value !== "number" || Number.isNaN(value)) return null;
      if (value <= 0) return 0;
      if (value <= 1) return Math.round(value * 100);
      if (value >= 100) return 100;
      return Math.round(value);
    };

    const runSceneQueueTask = async () => {
      const scene = (graph?.scenes || []).find((item) => item.id === next.entityId) || null;
      let mutableContext =
        scene && scene.context && typeof scene.context === "object"
          ? ({ ...(scene.context as Record<string, unknown>) } as Record<string, unknown>)
          : null;
      const rawSlides = Array.isArray(scene?.context?.sequence?.slides)
        ? scene?.context?.sequence?.slides
        : [];
      const slideTargets = rawSlides
        .map((slide, idx) => {
          if (!slide || typeof slide !== "object") return null;
          const idRaw = (slide as { id?: unknown }).id;
          const id = typeof idRaw === "string" ? idRaw.trim() : "";
          if (!id) return null;
          const titleRaw = (slide as { title?: unknown }).title;
          const title = typeof titleRaw === "string" ? titleRaw.trim() : "";
          const imageUrlRaw = (slide as { image_url?: unknown }).image_url;
          const hasImage = typeof imageUrlRaw === "string" && imageUrlRaw.trim().length > 0;
          return {
            id,
            label: title || `Слайд ${idx + 1}`,
            hasImage,
          };
        })
        .filter((item): item is { id: string; label: string; hasImage: boolean } => Boolean(item));

      const pendingSlideTargets = slideTargets.filter((slide) => !slide.hasImage);
      if (slideTargets.length > 0 && pendingSlideTargets.length === 0) {
        updateTask({
          status: "done",
          progress: 100,
          stage: `Слайды: ${slideTargets.length}/${slideTargets.length} (уже готовы)`,
          error: null,
        });
        if (selectedScene?.id === next.entityId) {
          await loadSceneAssets(next.entityId);
        }
        return;
      }

      const targetsToRun = pendingSlideTargets.length > 0 ? pendingSlideTargets : slideTargets;
      const totalRuns = targetsToRun.length > 0 ? targetsToRun.length : 1;
      let lastJobId: string | null = null;

      const persistSlideResult = async (slideId: string, finalJob: any) => {
        const variants = Array.isArray(finalJob?.variants) ? finalJob.variants : [];
        if (variants.length === 0) return;
        const first = variants[0];
        const firstUrl = typeof first?.url === "string" ? first.url.trim() : "";
        if (!firstUrl) return;

        const baseContext =
          mutableContext && typeof mutableContext === "object"
            ? mutableContext
            : {};
        const sequence =
          baseContext.sequence && typeof baseContext.sequence === "object"
            ? ({ ...(baseContext.sequence as Record<string, unknown>) } as Record<string, unknown>)
            : {};
        const slides = Array.isArray(sequence.slides) ? sequence.slides : [];

        let changed = false;
        const nextSlides = slides.map((item) => {
          if (!item || typeof item !== "object") return item;
          const current = item as Record<string, unknown>;
          if (String(current.id || "") !== slideId) return item;

          const nextVariants = variants
            .map((variant: any) => {
              const vid = typeof variant?.id === "string" ? variant.id : "";
              const vurl = typeof variant?.url === "string" ? variant.url : "";
              if (!vid || !vurl) return null;
              return {
                id: vid,
                url: vurl,
                thumbnail_url:
                  typeof variant?.thumbnail_url === "string" ? variant.thumbnail_url : null,
              };
            })
            .filter(Boolean);

          changed = true;
          return {
            ...current,
            image_url: firstUrl,
            image_variant_id: typeof first?.id === "string" ? first.id : "",
            variants: nextVariants,
          };
        });

        if (!changed) return;

        const nextContext: Record<string, unknown> = {
          ...baseContext,
          sequence: {
            ...sequence,
            slides: nextSlides,
          },
        };
        const updatedScene = await updateScene(next.entityId, { context: nextContext });
        mutableContext =
          updatedScene.context && typeof updatedScene.context === "object"
            ? ({ ...(updatedScene.context as Record<string, unknown>) } as Record<string, unknown>)
            : nextContext;

        setGraph((prev) =>
          prev
            ? {
                ...prev,
                scenes: prev.scenes.map((item) => (item.id === updatedScene.id ? updatedScene : item)),
              }
            : prev,
        );
        if (selectedScene?.id === next.entityId) {
          setSelectedScene(updatedScene);
        }
      };

      for (let idx = 0; idx < totalRuns; idx += 1) {
        const slide = targetsToRun[idx] || null;
        const stagePrefix = slide ? `Слайд ${idx + 1}/${totalRuns}` : "Сцена";
        updateTask({
          stage: slide ? `${stagePrefix}: ${slide.label}` : "Сцена: подготовка",
          progress: Math.round((idx / totalRuns) * 100),
          error: null,
        });

        const created = await generateSceneImage(next.entityId, {
          use_prompt_engine: true,
          num_variants: 1,
          auto_approve: true,
          ...(slide ? { slide_id: slide.id } : {}),
        });

        lastJobId = created.id;
        updateTask({
          jobId: created.id,
          stage: `${stagePrefix}: ${created.stage || "в очереди"}`,
        });

        const finalJob = await waitForGenerationJob(created.id, {
          intervalMs: 2000,
          maxAttempts: 600,
          onUpdate: (updated) => {
            const normalized = normalizeJobProgress(updated.progress);
            const aggregateProgress =
              normalized === null
                ? Math.round((idx / totalRuns) * 100)
                : Math.round(((idx + normalized / 100) / totalRuns) * 100);
            updateTask({
              status: "running",
              stage: `${stagePrefix}: ${updated.stage || "рендеринг"}`,
              progress: Math.max(0, Math.min(99, aggregateProgress)),
              error: updated.error ?? null,
            });
          },
        });
        if (finalJob.status !== "done") {
          const status = finalJob.status || "unknown";
          throw new Error(
            finalJob.error || `${stagePrefix}: генерация завершилась со статусом ${status}.`,
          );
        }
        if (slide) {
          await persistSlideResult(slide.id, finalJob);
        }
      }

      updateTask({
        status: "done",
        progress: 100,
        stage:
          slideTargets.length > 0
            ? `Слайды: ${slideTargets.length}/${slideTargets.length}`
            : "Сцена: готово",
        error: null,
        jobId: lastJobId,
      });

      if (selectedScene?.id === next.entityId) {
        await loadSceneAssets(next.entityId);
      }
    };

    const run = async () => {
      updateTask({ status: "running", error: null });
      try {
        if (next.kind === "scene") {
          await runSceneQueueTask();
          return;
        }

        let job: { id: string; status: string } | null = null;
        if (next.kind === "character") {
          job = await createAssetGenerationJob({
            task_type: "character_sheet",
            entity_type: "character",
            entity_id: next.entityId,
            project_id: projectId ?? undefined,
            payload: isCreativeMode ? { kinds: [...CREATIVE_CHARACTER_REFERENCE_KINDS] } : undefined,
          });
        } else if (next.kind === "location") {
          job = await createAssetGenerationJob({
            task_type: "location_sheet",
            entity_type: "location",
            entity_id: next.entityId,
            project_id: projectId ?? undefined,
          });
        }

        if (!job) return;

        updateTask({ jobId: job?.id ?? null, status: "running" });

        const finalJob = await waitForGenerationJob(job.id, {
          intervalMs: 2000,
          maxAttempts: 600,
          onUpdate: (updated) => {
            updateTask({
              status: "running",
              stage: updated.stage ?? null,
              progress: updated.progress ?? null,
              error: updated.error ?? null,
            });
          },
        });

        const isDone = finalJob.status === "done";
        updateTask({
          status: isDone ? "done" : "failed",
          stage: finalJob.stage ?? null,
          progress: finalJob.progress ?? null,
          error: finalJob.error ?? null,
        });

        if (isDone) {
          if (next.kind === "character") {
            await refreshCharacter(next.entityId);
          } else if (next.kind === "location") {
            await refreshLocation(next.entityId);
          } else if (next.kind === "scene" && selectedScene?.id === next.entityId) {
            await loadSceneAssets(next.entityId);
          }
        }
      } catch (error: any) {
        updateTask({ status: "failed", error: error?.message || "Ошибка генерации" });
      }
    };

    run();
  }, [
    assetQueue,
    assetQueuePaused,
    isCreativeMode,
    projectId,
    refreshCharacter,
    refreshLocation,
    graph?.scenes,
    selectedScene?.id,
  ]);

  const openCharacterEdit = useCallback((character: CharacterPreset) => {
    setAssetEdit({
      kind: "character",
      item: character,
      draft: {
        name: character.name || "",
        description: character.description || "",
        appearance_prompt: character.appearance_prompt || "",
        negative_prompt: character.negative_prompt || "",
        style_tags: (character.style_tags || []).join(", "),
        voice_profile: character.voice_profile || "",
        motivation: character.motivation || "",
        legal_status: character.legal_status || "",
      },
    });
  }, []);

  const openLocationEdit = useCallback((location: Location) => {
    setAssetEdit({
      kind: "location",
      item: location,
      draft: {
        name: location.name || "",
        description: location.description || "",
        visual_reference: location.visual_reference || "",
        negative_prompt: location.negative_prompt || "",
        tags: Array.isArray(location.tags) ? location.tags.join(", ") : "",
      },
    });
  }, []);

  const handleAssetEditSave = useCallback(async () => {
    if (!assetEdit) return;
    setAssetEditSaving(true);
    try {
      if (assetEdit.kind === "character") {
        const payload: Partial<CharacterPreset> = {
          name: assetEdit.draft.name.trim(),
          description: assetEdit.draft.description.trim() || null,
          appearance_prompt: assetEdit.draft.appearance_prompt.trim() || null,
          negative_prompt: assetEdit.draft.negative_prompt.trim() || null,
          style_tags: assetEdit.draft.style_tags
            ? assetEdit.draft.style_tags.split(",").map((item) => item.trim()).filter(Boolean)
            : null,
          voice_profile: assetEdit.draft.voice_profile.trim() || null,
          motivation: assetEdit.draft.motivation.trim() || null,
          legal_status: assetEdit.draft.legal_status.trim() || null,
        };
        const needsUnsafe = Boolean(assetEdit.item.source_preset_id);
        const updated = await updateCharacterPreset(
          assetEdit.item.id,
          payload,
          needsUnsafe ? { unsafe: true } : undefined,
        );
        setProjectCharacters((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      } else if (assetEdit.kind === "location") {
        const payload: Partial<Location> = {
          name: assetEdit.draft.name.trim(),
          description: assetEdit.draft.description.trim() || null,
          visual_reference: assetEdit.draft.visual_reference.trim() || null,
          negative_prompt: assetEdit.draft.negative_prompt.trim() || null,
          tags: assetEdit.draft.tags
            ? assetEdit.draft.tags.split(",").map((item) => item.trim()).filter(Boolean)
            : null,
        };
        const updated = await updateLocation(assetEdit.item.id, payload);
        setProjectLocations((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      }
      setAssetEdit(null);
    } catch (error: any) {
      console.error("Failed to save asset", error);
      setAssetsError(error?.message || "Не удалось сохранить ассет.");
    } finally {
      setAssetEditSaving(false);
    }
  }, [assetEdit]);

  const openCharacterAIFill = useCallback((character: CharacterPreset) => {
    setAiFillModal({
      title: `Персонаж: ${character.name}`,
      formType: "character_asset",
      fields: CHARACTER_ASSET_FIELDS,
      currentValues: {
        name: character.name,
        description: character.description,
        appearance_prompt: character.appearance_prompt,
        negative_prompt: character.negative_prompt,
        style_tags: character.style_tags || [],
        voice_profile: character.voice_profile,
        motivation: character.motivation,
        legal_status: character.legal_status,
      },
      context: character.description ? `Описание: ${character.description}` : undefined,
      onApply: async (values) => {
        const payload: Partial<CharacterPreset> = {
          name: typeof values.name === "string" ? values.name : character.name,
          description: typeof values.description === "string" ? values.description : character.description,
          appearance_prompt:
            typeof values.appearance_prompt === "string" ? values.appearance_prompt : character.appearance_prompt,
          negative_prompt:
            typeof values.negative_prompt === "string" ? values.negative_prompt : character.negative_prompt,
          style_tags: Array.isArray(values.style_tags)
            ? values.style_tags.map((item) => String(item).trim()).filter(Boolean)
            : character.style_tags || [],
          voice_profile:
            typeof values.voice_profile === "string" ? values.voice_profile : character.voice_profile,
          motivation: typeof values.motivation === "string" ? values.motivation : character.motivation,
          legal_status: typeof values.legal_status === "string" ? values.legal_status : character.legal_status,
        };
        try {
          const needsUnsafe = Boolean(character.source_preset_id);
          const updated = await updateCharacterPreset(
            character.id,
            payload,
            needsUnsafe ? { unsafe: true } : undefined,
          );
          setProjectCharacters((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
          if (assetEdit?.kind === "character" && assetEdit.item.id === updated.id) {
            openCharacterEdit(updated);
          }
        } catch (error: any) {
          console.error("Failed to apply AI fill to character", error);
          setAssetsError(error?.message || "Не удалось обновить персонажа через AI.");
        }
      },
    });
  }, [assetEdit, openCharacterEdit]);

  const openLocationAIFill = useCallback((location: Location) => {
    setAiFillModal({
      title: `Локация: ${location.name}`,
      formType: "location_asset",
      fields: LOCATION_ASSET_FIELDS,
      currentValues: {
        name: location.name,
        description: location.description,
        visual_reference: location.visual_reference,
        negative_prompt: location.negative_prompt,
        tags: location.tags || [],
      },
      context: location.description ? `Описание: ${location.description}` : undefined,
      onApply: async (values) => {
        const payload: Partial<Location> = {
          name: typeof values.name === "string" ? values.name : location.name,
          description: typeof values.description === "string" ? values.description : location.description,
          visual_reference:
            typeof values.visual_reference === "string" ? values.visual_reference : location.visual_reference,
          negative_prompt:
            typeof values.negative_prompt === "string" ? values.negative_prompt : location.negative_prompt,
          tags: Array.isArray(values.tags)
            ? values.tags.map((item) => String(item).trim()).filter(Boolean)
            : location.tags || [],
        };
        try {
          const updated = await updateLocation(location.id, payload);
          setProjectLocations((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
          if (assetEdit?.kind === "location" && assetEdit.item.id === updated.id) {
            openLocationEdit(updated);
          }
        } catch (error: any) {
          console.error("Failed to apply AI fill to location", error);
          setAssetsError(error?.message || "Не удалось обновить локацию через AI.");
        }
      },
    });
  }, [assetEdit, openLocationEdit]);

  const updateAssetDraft = useCallback((patch: Record<string, string>) => {
    setAssetEdit((prev) => {
      if (!prev) return prev;
      return { ...prev, draft: { ...prev.draft, ...patch } } as AssetEditState;
    });
  }, []);

  function handleMoveScene(sceneId: string, direction: -1 | 1) {
    if (!graph) return;
    const ordered = orderedScenes.map((scene, idx) => ({
      scene,
      order: scene.order_index ?? idx + 1,
    }));
    const index = ordered.findIndex((item) => item.scene.id === sceneId);
    const swapIndex = index + direction;
    if (index < 0 || swapIndex < 0 || swapIndex >= ordered.length) return;
    const current = ordered[index];
    const swap = ordered[swapIndex];
    setReordering(true);
    Promise.all([
        updateScene(current.scene.id, { order_index: swap.order }),
        updateScene(swap.scene.id, { order_index: current.order }),
      ]).then(([updatedCurrent, updatedSwap]) => {
      setGraph((prev) =>
        prev
          ? {
              ...prev,
              scenes: prev.scenes.map((sc) => {
                if (sc.id === updatedCurrent.id) return updatedCurrent;
                if (sc.id === updatedSwap.id) return updatedSwap;
                return sc;
              }),
            }
          : prev,
      );
      if (selectedScene?.id === updatedCurrent.id) setSelectedScene(updatedCurrent);
      if (selectedScene?.id === updatedSwap.id) setSelectedScene(updatedSwap);
    }).catch(error => {
      console.error("Failed to reorder scene", error);
    }).finally(() => {
      setReordering(false);
    });
  }

  function handleAddChoice() {
    if (!graphId || !selectedScene || !choiceForm.targetId) return;
    const label = choiceForm.label.trim() || "Продолжить";
    const value = choiceForm.value.trim();
    const condition = choiceForm.condition.trim();
    const metadata = value ? { choice_value: value } : null;
    createEdge(graphId, {
      from_scene_id: selectedScene.id,
      to_scene_id: choiceForm.targetId,
      choice_label: label,
      condition: condition || null,
      edge_metadata: metadata,
    })
      .then((newEdge) => {
        setEdges((eds) => [...eds, toFlowEdge(newEdge, { persisted: true })]);
        setGraph((prev) =>
          prev ? { ...prev, edges: [...(prev.edges || []), newEdge] } : prev,
        );
        setChoiceForm({
          label: selectedScene.scene_type === "decision" ? "Выбор" : "Продолжить",
          targetId: "",
          value: "",
          condition: "",
        });
      })
      .catch((error) => {
        console.error("Failed to add choice", error);
      });
  }

  function handleEdgeSave(edge: Edge) {
    const draft = edgeDrafts[edge.id];
    if (!draft) return;
    
    const nextMetadata = { ...(edge.edge_metadata || {}) };
    const value = draft.value.trim();
    if (value) {
      nextMetadata.choice_value = value;
    } else {
      delete nextMetadata.choice_value;
    }
    
    updateEdge(edge.id, {
      choice_label: draft.label.trim() || "Продолжить",
      condition: draft.condition.trim() || null,
      edge_metadata: Object.keys(nextMetadata).length ? nextMetadata : null,
    }).then(updated => {
      setGraph((prev) =>
        prev
          ? {
              ...prev,
              edges: prev.edges.map((e) => (e.id === updated.id ? updated : e)),
            }
          : prev,
      );
      setEdges((eds) =>
        eds.map((e) =>
          e.id === updated.id
            ? toFlowEdge(updated, {
                persisted: true,
              })
            : e,
        ),
      );
    }).catch(error => {
      console.error("Failed to update choice", error);
    });
  }

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!graphId || !connection.source || !connection.target) return;
      
      const choiceLabel = window.prompt("Метка перехода", "Далее") ?? "Далее";
      createEdge(graphId, {
        from_scene_id: connection.source,
        to_scene_id: connection.target,
        choice_label: choiceLabel,
      }).then(newEdge => {
        const flowEdge = toFlowEdge(newEdge, { persisted: true });
        setEdges((eds) => addEdge(flowEdge, eds));
        setGraph((prev) =>
          prev ? { ...prev, edges: [...(prev.edges || []), newEdge] } : prev,
        );
      }).catch(error => {
        console.error("Failed to create edge", error);
      });
    },
    [graphId, setEdges, toFlowEdge],
  );

  function handleAddChild(type: "story" | "decision") {
    if (!graphId || !selectedScene) return;
    const title = window.prompt(type === "decision" ? "Название узла выбора" : "Название сцены");
    if (!title?.trim()) return;
    createScene(graphId, {
      title,
      content: "Опишите, что происходит в этой сцене.",
      scene_type: type,
    })
      .then((scene) => {
        const label =
          window.prompt("Метка перехода", type === "decision" ? "Выбор" : "Продолжить") ??
          "Продолжить";
        return createEdge(graphId, {
          from_scene_id: selectedScene.id,
          to_scene_id: scene.id,
          choice_label: label,
        }).then((newEdge) => ({ scene, newEdge }));
      })
      .then(({ scene, newEdge }) => {
        setGraph((prev) =>
          prev
            ? {
                ...prev,
                scenes: [...prev.scenes, scene],
                edges: [...prev.edges, newEdge],
              }
            : prev,
        );
        setSelectedScene(scene);
        loadSceneAssets(scene.id).catch((error) => {
          console.error("Failed to load scene assets", error);
        });
        trackEvent("scene_created_child", { parent: selectedScene.id, child: scene.id });
      })
      .catch((error) => {
        console.error("Failed to add child scene", error);
      });
  }

  function handleGenerate() {
    if (!selectedScene) return;
    if (selectedSceneAssetStatus?.blocked) {
      setAssetsError(selectedSceneAssetStatus.reason || "Сцена заблокирована для генерации.");
      return;
    }
    generateSceneImage(selectedScene.id, { use_prompt_engine: true, num_variants: 1 })
      .then((job) => {
        setJobId(job.id);
        setJobStatus(job.status);
        upsertJob(job);
        trackEvent("generation_started", { sceneId: selectedScene.id, jobId: job.id });
      })
      .catch((error) => {
        console.error("Failed to generate images", error);
      });
  }

  function handleValidate() {
    if (!graphId) return;
    setValidating(true);
    validateGraph(graphId)
      .then((report) => {
        setValidationReport(report);
      })
      .catch((error) => {
        console.error("Failed to validate graph", error);
      })
      .finally(() => {
        setValidating(false);
      });
  }

  async function handlePersistAutoEdges() {
    if (!graphId || autoDerivedEdges.length === 0) return;
    setPersistingAutoEdges(true);
    try {
      const results = await Promise.allSettled(
        autoDerivedEdges.map((edge) =>
          createEdge(graphId, {
            from_scene_id: edge.from_scene_id,
            to_scene_id: edge.to_scene_id,
            choice_label: edge.choice_label || "Далее",
            condition: edge.condition || null,
            edge_metadata: edge.edge_metadata,
          }),
        ),
      );
      const created: Edge[] = [];
      let failed = 0;
      results.forEach((result) => {
        if (result.status === "fulfilled") {
          created.push(result.value);
        } else {
          failed += 1;
          console.error("Failed to persist auto edge", result.reason);
        }
      });
      if (created.length > 0) {
        setGraph((prev) =>
          prev
            ? {
                ...prev,
                edges: [...(prev.edges || []), ...created],
              }
            : prev,
        );
      }
      if (failed > 0) {
        setAssetsError(`Не удалось сохранить ${failed} из ${autoDerivedEdges.length} авто-связей.`);
      } else {
        setAssetsError(null);
      }
    } finally {
      setPersistingAutoEdges(false);
    }
  }

  const sceneOptions = useMemo(() => graph?.scenes || [], [graph]);
  const nodeTypes = useMemo(() => ({ scene: SceneNodeCard }), []);

  const orderedScenes = useMemo(() => {
    const scenes = [...sceneOptions];
    scenes.sort(
      (a, b) =>
        (a.order_index ?? Number.MAX_SAFE_INTEGER) - (b.order_index ?? Number.MAX_SAFE_INTEGER),
    );
    return scenes;
  }, [sceneOptions]);

  const sceneAssets = useMemo(
    () =>
      orderedScenes.map((scene) => {
        const status = sceneAssetStatus.get(scene.id);
        return {
          scene,
          blocked: status?.blocked ?? false,
          reason: status?.reason ?? "",
        };
      }),
    [orderedScenes, sceneAssetStatus],
  );

  const queuedTasks = useMemo(() => assetQueue.filter((task) => task.status === "queued"), [assetQueue]);
  const runningTask = useMemo(() => assetQueue.find((task) => task.status === "running") || null, [assetQueue]);
  const completedTasks = useMemo(
    () => assetQueue.filter((task) => task.status === "done" || task.status === "failed"),
    [assetQueue],
  );
  const failedTasks = useMemo(
    () => completedTasks.filter((task) => task.status === "failed"),
    [completedTasks],
  );
  const missingCharacterAssets = useMemo(() => characterAssets.filter((item) => !item.ready), [characterAssets]);
  const missingLocationAssets = useMemo(() => locationAssets.filter((item) => !item.ready), [locationAssets]);
  const blockedSceneAssets = useMemo(() => sceneAssets.filter((item) => item.blocked), [sceneAssets]);
  const readySceneAssets = useMemo(() => sceneAssets.filter((item) => !item.blocked), [sceneAssets]);

  const orderedSceneIndex = useMemo(
    () => new Map(orderedScenes.map((scene, idx) => [scene.id, idx])),
    [orderedScenes],
  );
  const defaultPlaySceneId = selectedScene?.id || graph?.root_scene_id || orderedScenes[0]?.id || null;

  const openQuestPreview = useCallback(
    (sceneId?: string | null) => {
      const nextSceneId = sceneId || defaultPlaySceneId;
      if (!nextSceneId) return;
      setQuestPreviewStartSceneId(nextSceneId);
      setQuestPreviewOpen(true);
      trackEvent("editor_play_preview_opened", { graphId, sceneId: nextSceneId });
    },
    [defaultPlaySceneId, graphId],
  );

  const filteredScenes = useMemo(() => {
    return orderedScenes.filter((scene) => {
      if (sceneFilter !== "all" && scene.scene_type !== sceneFilter) return false;
      if (!searchQuery.trim()) return true;
      const query = searchQuery.toLowerCase();
      return (
        scene.title.toLowerCase().includes(query) ||
        scene.content.toLowerCase().includes(query) ||
        (scene.synopsis || "").toLowerCase().includes(query)
      );
    });
  }, [orderedScenes, sceneFilter, searchQuery]);

  const outgoingEdges = useMemo(() => {
    if (!graph || !selectedScene) return [];
    return graph.edges.filter((edge) => edge.from_scene_id === selectedScene.id);
  }, [graph, selectedScene]);

  const autoOutgoingEdges = useMemo(() => {
    if (!selectedScene) return [];
    return autoDerivedEdges.filter((edge) => edge.from_scene_id === selectedScene.id);
  }, [autoDerivedEdges, selectedScene?.id]);

  const choiceTargets = useMemo(
    () => orderedScenes.filter((scene) => scene.id !== selectedScene?.id),
    [orderedScenes, selectedScene?.id],
  );

  const approvedImageUrl = useMemo(
    () => images.find((img) => img.is_approved)?.url || images[0]?.url || "",
    [images],
  );

  const jobStatusLabel = useMemo(() => {
    if (!jobStatus) return null;
    if (jobStatus === "queued") return "Ожидание в очереди";
    if (jobStatus === "running") return "Рендеринг";
    if (jobStatus === "done") return "Готово";
    if (jobStatus === "failed") return "Ошибка";
    return jobStatus;
  }, [jobStatus]);

  useEffect(() => {
    if (!selectedScene) {
      setEdgeDrafts({});
      return;
    }
    const next: Record<string, { label: string; value: string; condition: string }> = {};
    outgoingEdges.forEach((edge) => {
      next[edge.id] = {
        label: edge.choice_label || "Продолжить",
        value: getEdgeChoiceValue(edge),
        condition: edge.condition || "",
      };
    });
    setEdgeDrafts(next);
  }, [getEdgeChoiceValue, outgoingEdges, selectedScene?.id]);

  const validationSummary = useMemo(() => {
    if (!validationReport) return { error: 0, warning: 0, info: 0 };
    return validationReport.issues.reduce(
      (acc, issue) => {
        if (issue.severity === "error") acc.error += 1;
        else if (issue.severity === "warning") acc.warning += 1;
        else acc.info += 1;
        return acc;
      },
      { error: 0, warning: 0, info: 0 },
    );
  }, [validationReport]);

  const choiceKeyLabel = selectedScene?.context?.sequence?.choice_key?.trim() || "last_choice";
  const visibleEdgeCount = (graph?.edges.length || 0) + autoDerivedEdges.length;

  if (loading) return <div className="graph-loading">Загрузка графа...</div>;
  if (!graph) return <div className="graph-loading">Граф не найден</div>;

  return (
    <div className="graph-shell">
      <button
        className="graph-side-toggle-floating"
        onClick={() => setSideCollapsed((prev) => !prev)}
        aria-label={sideCollapsed ? "Показать боковую панель" : "Скрыть боковую панель"}
        title={sideCollapsed ? "Показать боковую" : "Скрыть боковую"}
      >
        <span className="graph-side-toggle-icon">{sideCollapsed ? ">" : "<"}</span>
        <span className="graph-side-toggle-label">
          {sideCollapsed ? "Показать боковую" : "Скрыть боковую"}
        </span>
      </button>
      <div className="graph-hero">
        <div>
          <button className="graph-back" onClick={() => navigate(`/projects/${projectId}`)}>
            ← Назад к проекту
          </button>
          <h1>{graph.title}</h1>
          <p>{graph.description || "Постройте граф сюжета и держите каждую ветку согласованной."}</p>
        </div>
          <div className="graph-hero-actions">
            <div className="graph-view-toggle">
              <button
                className={`graph-toggle ${viewMode === "writer" ? "active" : ""}`}
                onClick={() => setViewMode("writer")}
            >Редактор</button>
              <button
                className={`graph-toggle ${viewMode === "graph" ? "active" : ""}`}
                onClick={() => setViewMode("graph")}
              >Граф</button>
            </div>
            <button
              className="secondary"
              onClick={() => navigate(`/projects/${projectId}/graphs/${graph.id}/draft-runner`)}
            >
              Черновой прогон
            </button>
            <button
              className="primary"
              onClick={() => openQuestPreview()}
              disabled={!defaultPlaySceneId}
            >
              Играть
            </button>
            <div className="graph-stat">
              <strong>{graph.scenes.length}</strong>
              <span>Сцены</span>
            </div>
          <div className="graph-stat">
            <strong>{visibleEdgeCount}</strong>
            <span>Связи</span>
            {autoDerivedEdges.length > 0 ? <small>авто: {autoDerivedEdges.length}</small> : null}
          </div>
          {viewMode === "graph" && (
            <>
              <button
                className="secondary"
                onClick={() => buildFlow(graph.scenes, graph.edges, { autoLayout: true, ignoreSaved: true })}
              >Авто-раскладка</button>
              {autoDerivedEdges.length > 0 ? (
                <button
                  className="secondary"
                  onClick={() => {
                    void handlePersistAutoEdges();
                  }}
                  disabled={persistingAutoEdges}
                >
                  {persistingAutoEdges ? "Сохранение..." : `Зафиксировать связи (${autoDerivedEdges.length})`}
                </button>
              ) : null}
              <button className="secondary" onClick={() => flowInstance?.fitView({ padding: 0.2 })}>Подогнать вид</button>
            </>
          )}
          <button className="primary" onClick={handleValidate} disabled={validating}>
            {validating ? "Валидация..." : "Запустить валидацию"}
          </button>
        </div>
      </div>
      {viewMode === "writer" ? (
        <div className={`writer-layout ${sideCollapsed ? "collapsed" : ""}`}>
          <div className="writer-left-column">
          <div className="writer-outline" style={{ display: 'flex', flexDirection: 'column', gap: '16px', justifyContent: 'flex-start', alignContent: 'flex-start' }}>
            <div className="writer-panel" style={{ background: 'rgba(15, 23, 42, 0.78)', border: '1px solid rgba(148, 163, 184, 0.25)', borderRadius: '16px', padding: '16px', overflow: 'hidden' }}>
              <div className="writer-panel-header">
                <div>
                  <h2>Структура</h2>
                  <p className="muted">Пишите последовательно, затем ветвитесь при необходимости.</p>
                </div>
                <span className="writer-pill">{filteredScenes.length} сцен</span>
              </div>
              <input
                className="writer-input"
                placeholder="Поиск сцен"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
              <div className="writer-filter">
                <button
                  className={`writer-filter-btn ${sceneFilter === "all" ? "active" : ""}`}
                  onClick={() => setSceneFilter("all")}
                >Все</button>
                <button
                  className={`writer-filter-btn ${sceneFilter === "story" ? "active" : ""}`}
                  onClick={() => setSceneFilter("story")}
                >История</button>
                <button
                  className={`writer-filter-btn ${sceneFilter === "decision" ? "active" : ""}`}
                  onClick={() => setSceneFilter("decision")}
                >Выборы</button>
              </div>
              <div className="writer-list">
                {filteredScenes.map((scene, idx) => {
                  const preview = (scene.synopsis || scene.content || "").slice(0, 120);
                  const orderIndex = orderedSceneIndex.get(scene.id) ?? idx;
                  const displayOrder = scene.order_index ?? orderIndex + 1;
                  return (
                    <div
                      key={scene.id}
                      className={`writer-item ${selectedScene?.id === scene.id ? "selected" : ""}`}
                      role="button"
                      tabIndex={0}
                      onClick={() => {
                        setSelectedScene(scene);
                        void loadSceneAssets(scene.id);
                      }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          setSelectedScene(scene);
                          void loadSceneAssets(scene.id);
                        }
                      }}
                    >
                      <div className="writer-item-header">
                        <div className="writer-item-title">
                          <span className="writer-index">{displayOrder}</span>
                          <strong>{scene.title}</strong>
                        </div>
                        <span className={`writer-badge ${scene.scene_type}`}>{scene.scene_type}</span>
                      </div>
                      <div className="writer-item-meta">
                        {scene.location?.name || "Нет локации"}
                      </div>
                      <p>{preview}</p>
                      <div className="writer-item-actions">
                        <button
                          type="button"
                          className="ghost"
                          disabled={reordering || orderIndex <= 0}
                          onClick={(event) => {
                            event.stopPropagation();
                            handleMoveScene(scene.id, -1);
                          }}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          className="ghost"
                          disabled={reordering || orderIndex === orderedScenes.length - 1}
                          onClick={(event) => {
                            event.stopPropagation();
                            handleMoveScene(scene.id, 1);
                          }}
                        >
                          ↓
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="writer-panel">
              <div className="writer-panel-header">
                <h2>Новая сцена</h2>
                <span className="writer-pill">Добавить</span>
              </div>
              <div className="writer-form">
                <label className="writer-field">
                  <span>Заголовок</span>
                  <input
                    className="writer-input"
                    placeholder="Название сцены"
                    value={sceneForm.title}
                    onChange={(event) => setSceneForm({ ...sceneForm, title: event.target.value })}
                  />
                </label>
                <label className="writer-field">
                  <span>Синопсис</span>
                  <textarea
                    className="writer-textarea"
                    placeholder="Краткое описание"
                    rows={2}
                    value={sceneForm.synopsis}
                    onChange={(event) => setSceneForm({ ...sceneForm, synopsis: event.target.value })}
                  />
                </label>
                <label className="writer-field">
                  <span>Содержание</span>
                  <textarea
                    className="writer-textarea"
                    placeholder="Что происходит в этой сцене?"
                    rows={4}
                    value={sceneForm.content}
                    onChange={(event) => setSceneForm({ ...sceneForm, content: event.target.value })}
                  />
                </label>
                <div className="writer-radio">
                  <label>
                    <input
                      type="radio"
                      checked={sceneForm.scene_type === "story"}
                      onChange={() => setSceneForm({ ...sceneForm, scene_type: "story" })}
                    />История</label>
                  <label>
                    <input
                      type="radio"
                      checked={sceneForm.scene_type === "decision"}
                      onChange={() => setSceneForm({ ...sceneForm, scene_type: "decision" })}
                    />Решение</label>
                </div>
                <div className="writer-actions">
                  <button className="secondary" type="button" onClick={() => openSceneAIFill("new")}>AI заполнение</button>
                  <button onClick={handleCreateScene} disabled={creatingScene} className="primary">
                    {creatingScene ? "Создание..." : "Создать сцену"}
                  </button>
                </div>
              </div>
            </div>

            <div className="writer-panel">
              <div className="writer-panel-header">
                <h2>Валидация</h2>
                <span className="writer-pill">Контроль качества</span>
              </div>
              {validationReport ? (
                <div className="graph-validation">
                  <div className="graph-validation-summary">
                    <span className={`graph-pill ${validationSummary.error ? "danger" : ""}`}>
                      Ошибки {validationSummary.error}
                    </span>
                    <span className={`graph-pill ${validationSummary.warning ? "warn" : ""}`}>
                      Предупреждения {validationSummary.warning}
                    </span>
                    <span className="graph-pill">Инфо {validationSummary.info}</span>
                  </div>
                  <div className="graph-validation-list">
                    {validationReport.issues.length === 0 ? (
                      <div className="muted">Проблем не найдено.</div>
                    ) : (
                      validationReport.issues.slice(0, 5).map((issue, idx) => (
                        <div key={`${issue.code}-${idx}`} className={`graph-issue ${issue.severity}`}>
                          <strong>{issue.code}</strong>
                          <span>{issue.message}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ) : (
                <div className="muted">Запустите валидацию, чтобы увидеть проблемы логики сюжета.</div>
              )}
            </div>
          </div>

          <div className="writer-inspector" style={{ display: 'flex', flexDirection: 'column', gap: '16px', justifyContent: 'flex-start', alignContent: 'flex-start' }}>
            <div className="writer-panel asset-panel">
              <div className="writer-panel-header">
                <h2>Ассеты</h2>
                <span className="writer-pill">
                  {projectCharacters.length + projectLocations.length + orderedScenes.length}
                </span>
              </div>

              {assetsLoading ? (
                <div className="muted">Загрузка ассетов...</div>
              ) : null}
              {assetsError ? <div className="asset-error">{assetsError}</div> : null}
              {libraryError ? <div className="asset-error">{libraryError}</div> : null}
              <label className="asset-toggle">
                <input
                  type="checkbox"
                  checked={useLibraryAssets}
                  onChange={(event) => setUseLibraryAssets(event.target.checked)}
                />
                Показывать библиотеку
              </label>

              <div className="asset-queue">
                <div className="asset-queue-header">
                  <strong>Очередь генерации</strong>
                  <div className="asset-queue-summary">
                    <span className="writer-pill">{queuedTasks.length} в очереди</span>
                    <span className="writer-pill">завершено {completedTasks.length}</span>
                    <span className="writer-pill">ошибки {failedTasks.length}</span>
                  </div>
                </div>
                <div className="asset-queue-actions">
                  <button
                    className="secondary"
                    onClick={() => setAssetQueuePaused((prev) => !prev)}
                  >
                    {assetQueuePaused ? "Продолжить" : "Пауза"}
                  </button>
                  <button
                    className="secondary"
                    onClick={() => setAssetQueue((prev) => prev.filter((task) => task.status === "running"))}
                    disabled={queuedTasks.length === 0}
                  >
                    Очистить очередь
                  </button>
                </div>
                {runningTask ? (
                  <div className="asset-queue-active">
                    <div>
                      <strong>{runningTask.label}</strong>
                      <span className="asset-status running">
                        {runningTask.stage || "Выполняется"}
                      </span>
                    </div>
                    {typeof runningTask.progress === "number" ? (
                      <span className="asset-progress">{runningTask.progress}%</span>
                    ) : null}
                  </div>
                ) : (
                  <div className="muted">Нет активных задач.</div>
                )}
                {queuedTasks.length > 0 && (
                  <div className="asset-queue-list">
                    {queuedTasks.map((task) => (
                      <div key={task.id} className="asset-queue-item">
                        <span>{task.label}</span>
                        <span className="asset-status queued">в очереди</span>
                      </div>
                    ))}
                  </div>
                )}
                {completedTasks.length > 0 && (
                  <div className="asset-queue-completed">
                    <div className="asset-queue-subtitle">Последние завершённые</div>
                    {completedTasks.slice(0, 8).map((task) => (
                      <div key={task.id} className="asset-queue-item completed">
                        <div className="asset-queue-item-main">
                          <span>{task.label}</span>
                          <span className={`asset-status ${task.status === "done" ? "done" : "failed"}`}>
                            {task.status === "done" ? "готово" : "ошибка"}
                          </span>
                        </div>
                        {task.error ? (
                          <div className="asset-queue-error">{formatAssetError(task.error)}</div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="asset-group">
                <div className="asset-group-header">
                  <h3>Персонажи</h3>
                  <span className="writer-pill">{projectCharacters.length}</span>
                </div>
                <div className="asset-group-actions">
                  <button
                    className="secondary"
                    onClick={enqueueMissingCharacters}
                    disabled={missingCharacterAssets.length === 0}
                  >
                    Сгенерировать отсутствующие ({missingCharacterAssets.length})
                  </button>
                </div>
                <div className="asset-list">
                  {characterAssets.length === 0 ? (
                    <div className="muted">Нет персонажей в проекте.</div>
                  ) : (
                    characterAssets.map(({ character, ready, missing }) => {
                      const previewUrl = getAssetUrl(
                        character.preview_thumbnail_url || character.preview_image_url,
                      );
                      const statusText = ready ? "готово" : `нет: ${missing.join(", ")}`;
                      return (
                        <div key={character.id} className={`asset-item ${ready ? "ready" : "missing"}`}>
                          <div className={`asset-item-preview ${previewUrl ? "" : "placeholder"}`}>
                            {previewUrl ? (
                              <img src={previewUrl} alt={character.name || "Персонаж"} />
                            ) : (
                              <span>{(character.name || "?").slice(0, 1).toUpperCase()}</span>
                            )}
                            <div className="asset-item-overlay-top">
                              <span
                                className={`asset-status asset-status-chip ${ready ? "ready" : "missing"}`}
                                title={statusText}
                              >
                                {statusText}
                              </span>
                            </div>
                            <div className="asset-item-overlay-bottom">
                              <strong className="asset-item-title">{character.name || "Без имени"}</strong>
                              <div className="asset-item-actions">
                                <button
                                  className="asset-icon-btn"
                                  onClick={() => openCharacterEdit(character)}
                                  aria-label="Правка персонажа"
                                  title="Правка"
                                >
                                  <AssetActionIcon name="edit" />
                                </button>
                                <button
                                  className="asset-icon-btn"
                                  onClick={() => openCharacterAIFill(character)}
                                  aria-label="AI заполнение персонажа"
                                  title="AI заполнение"
                                >
                                  <AssetActionIcon name="ai" />
                                </button>
                                <button
                                  className="asset-icon-btn queue"
                                  onClick={() => enqueueCharacterTask(character)}
                                  aria-label="Добавить персонажа в очередь"
                                  title="В очередь"
                                >
                                  <AssetActionIcon name="queue" />
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
                {useLibraryAssets && (
                  <div className="asset-library">
                    <div className="asset-library-header">
                      <span className="muted">Библиотека</span>
                      <span className="writer-pill">{libraryCharacterOptions.length}</span>
                    </div>
                    {libraryLoading ? (
                      <div className="muted">Загрузка библиотеки...</div>
                    ) : libraryCharacterOptions.length === 0 ? (
                      <div className="muted">Нет новых персонажей для импорта.</div>
                      ) : (
                        <div className="asset-list">
                          {libraryCharacterOptions.map((character) => {
                            const previewUrl = getAssetUrl(
                              character.preview_thumbnail_url || character.preview_image_url,
                            );
                            return (
                              <div key={character.id} className="asset-item">
                                <div className={`asset-item-preview ${previewUrl ? "" : "placeholder"}`}>
                                  {previewUrl ? (
                                    <img src={previewUrl} alt={character.name || "Персонаж из библиотеки"} />
                                  ) : (
                                    <span>{(character.name || "?").slice(0, 1).toUpperCase()}</span>
                                  )}
                                  <div className="asset-item-overlay-top">
                                    <span className="asset-status asset-status-chip library">в библиотеке</span>
                                  </div>
                                  <div className="asset-item-overlay-bottom">
                                    <strong className="asset-item-title">{character.name || "Без имени"}</strong>
                                    <div className="asset-item-actions">
                                      <button
                                        className="asset-icon-btn import"
                                        onClick={() => handleImportLibraryCharacter(character.id)}
                                        aria-label="Импортировать персонажа"
                                        title="Импортировать"
                                      >
                                        <AssetActionIcon name="import" />
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                  </div>
                )}
              </div>

              <div className="asset-group">
                <div className="asset-group-header">
                  <h3>Локации</h3>
                  <span className="writer-pill">{projectLocations.length}</span>
                </div>
                <div className="asset-group-actions">
                  <button
                    className="secondary"
                    onClick={enqueueMissingLocations}
                    disabled={missingLocationAssets.length === 0}
                  >
                    Сгенерировать отсутствующие ({missingLocationAssets.length})
                  </button>
                </div>
                <div className="asset-list">
                  {locationAssets.length === 0 ? (
                    <div className="muted">Нет локаций в проекте.</div>
                  ) : (
                    locationAssets.map(({ location, ready, missing }) => {
                      const previewUrl = getAssetUrl(
                        location.preview_thumbnail_url || location.preview_image_url,
                      );
                      const statusText = ready ? (isCreativeMode ? "по контексту" : "готово") : `нет: ${missing.join(", ")}`;
                      return (
                        <div key={location.id} className={`asset-item ${ready ? "ready" : "missing"}`}>
                          <div className={`asset-item-preview ${previewUrl ? "" : "placeholder"}`}>
                            {previewUrl ? (
                              <img src={previewUrl} alt={location.name || "Локация"} />
                            ) : (
                              <span>{(location.name || "?").slice(0, 1).toUpperCase()}</span>
                            )}
                            <div className="asset-item-overlay-top">
                              <span
                                className={`asset-status asset-status-chip ${ready ? "ready" : "missing"}`}
                                title={statusText}
                              >
                                {statusText}
                              </span>
                            </div>
                            <div className="asset-item-overlay-bottom">
                              <strong className="asset-item-title">{location.name || "Без имени"}</strong>
                              <div className="asset-item-actions">
                                <button
                                  className="asset-icon-btn"
                                  onClick={() => openLocationEdit(location)}
                                  aria-label="Правка локации"
                                  title="Правка"
                                >
                                  <AssetActionIcon name="edit" />
                                </button>
                                <button
                                  className="asset-icon-btn"
                                  onClick={() => openLocationAIFill(location)}
                                  aria-label="AI заполнение локации"
                                  title="AI заполнение"
                                >
                                  <AssetActionIcon name="ai" />
                                </button>
                                <button
                                  className="asset-icon-btn queue"
                                  onClick={() => enqueueLocationTask(location)}
                                  aria-label="Добавить локацию в очередь"
                                  title="В очередь"
                                >
                                  <AssetActionIcon name="queue" />
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
                {useLibraryAssets && (
                  <div className="asset-library">
                    <div className="asset-library-header">
                      <span className="muted">Библиотека</span>
                      <span className="writer-pill">{libraryLocationOptions.length}</span>
                    </div>
                    {libraryLoading ? (
                      <div className="muted">Загрузка библиотеки...</div>
                    ) : libraryLocationOptions.length === 0 ? (
                      <div className="muted">Нет новых локаций для импорта.</div>
                      ) : (
                        <div className="asset-list">
                          {libraryLocationOptions.map((location) => {
                            const previewUrl = getAssetUrl(
                              location.preview_thumbnail_url || location.preview_image_url,
                            );
                            return (
                              <div key={location.id} className="asset-item">
                                <div className={`asset-item-preview ${previewUrl ? "" : "placeholder"}`}>
                                  {previewUrl ? (
                                    <img src={previewUrl} alt={location.name || "Локация из библиотеки"} />
                                  ) : (
                                    <span>{(location.name || "?").slice(0, 1).toUpperCase()}</span>
                                  )}
                                  <div className="asset-item-overlay-top">
                                    <span className="asset-status asset-status-chip library">в библиотеке</span>
                                  </div>
                                  <div className="asset-item-overlay-bottom">
                                    <strong className="asset-item-title">{location.name || "Без имени"}</strong>
                                    <div className="asset-item-actions">
                                      <button
                                        className="asset-icon-btn import"
                                        onClick={() => handleImportLibraryLocation(location.id)}
                                        aria-label="Импортировать локацию"
                                        title="Импортировать"
                                      >
                                        <AssetActionIcon name="import" />
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                  </div>
                )}
              </div>

              <div className="asset-group">
                <div className="asset-group-header">
                  <h3>Сцены</h3>
                  <div className="asset-queue-summary">
                    <span className="writer-pill">
                      готово {readySceneAssets.length} / {orderedScenes.length}
                    </span>
                    <span className="writer-pill">заблокировано {blockedSceneAssets.length}</span>
                  </div>
                </div>
                <div className="asset-group-actions">
                  <button
                    className="secondary"
                    onClick={enqueueReadyScenes}
                    disabled={readySceneAssets.length === 0}
                  >
                    Сгенерировать готовые ({readySceneAssets.length})
                  </button>
                </div>
                <div className="asset-list">
                  {sceneAssets.length === 0 ? (
                    <div className="muted">Нет сцен.</div>
                  ) : (
                    sceneAssets.map(({ scene, blocked, reason }) => (
                      <div key={scene.id} className={`asset-item ${blocked ? "blocked" : "ready"}`}>
                        <div className="asset-item-preview placeholder">
                          <span>{(scene.title || "?").slice(0, 1).toUpperCase()}</span>
                          <div className="asset-item-overlay-top">
                            <span className={`asset-status asset-status-chip ${blocked ? "blocked" : "ready"}`}>
                              {blocked ? "заблокировано" : "готово"}
                            </span>
                          </div>
                          <div className="asset-item-overlay-bottom">
                            <strong className="asset-item-title">{scene.title || "Без названия"}</strong>
                            <div className="asset-item-actions">
                              <button
                                className="asset-icon-btn"
                                onClick={() => {
                                  setSelectedScene(scene);
                                  void loadSceneAssets(scene.id);
                                }}
                                aria-label="Открыть сцену"
                                title="Открыть"
                              >
                                <AssetActionIcon name="open" />
                              </button>
                              <button
                                className="asset-icon-btn queue"
                                onClick={() => enqueueSceneTask(scene)}
                                disabled={blocked}
                                aria-label="Добавить сцену в очередь"
                                title="В очередь"
                              >
                                <AssetActionIcon name="queue" />
                              </button>
                            </div>
                          </div>
                        </div>
                        {blocked && reason ? <div className="asset-item-reason">{reason}</div> : null}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            {selectedScene ? (
              <>
                <div className="writer-panel writer-panel-scroll">
                  <SceneEditorPanel
                    scene={selectedScene}
                    projectId={projectId}
                    showWritingFields={false}
                    onSceneUpdated={(scene) => {
                      setSelectedScene(scene);
                      setGraph((prev) =>
                        prev
                          ? {
                              ...prev,
                              scenes: prev.scenes.map((sc) => (sc.id === scene.id ? scene : sc)),
                            }
                          : prev,
                      );
                    }}
                    onImagesUpdated={setImages}
                  />
                </div>

                <div className="writer-panel">
                  <div className="writer-panel-header">
                    <h2>Варианты изображений</h2>
                    <span className="writer-pill">{images.length}</span>
                  </div>
                  {images.length === 0 ? (
                    <div className="muted">Изображений пока нет.</div>
                  ) : (
                    <div
                      className="graph-image-grid"
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))",
                        gap: "10px",
                        maxHeight: "400px",
                        overflowY: "auto",
                        overflowX: "hidden",
                        width: "100%",
                        boxSizing: "border-box",
                      }}
                    >
                      {images.map((img) => (
                        <div
                          key={img.id}
                          className={`graph-image-card ${img.is_approved ? "approved" : ""}`}
                          style={{
                            position: "relative",
                            borderRadius: "10px",
                            overflow: "hidden",
                            border: img.is_approved ? "2px solid #22c55e" : "2px solid transparent",
                            background: "rgba(15, 23, 42, 0.5)",
                            width: "100%",
                            maxWidth: "100%",
                            boxSizing: "border-box",
                          }}
                        >
                          <img
                            src={img.url}
                            alt="вариант"
                            style={{
                              cursor: "zoom-in",
                              width: "100%",
                              maxWidth: "100%",
                              height: "80px",
                              objectFit: "cover",
                              display: "block",
                            }}
                            onClick={() => setLightboxUrl(img.url)}
                          />
                          <div className="graph-image-footer">
                            <span>{img.created_at?.slice(0, 10)}</span>
                            {selectedScene && (
                              <div className="graph-image-actions">
                                <button
                                  className={img.is_approved ? "graph-approved" : "graph-approve"}
                                  onClick={() => {
                                    try {
                                      approveSceneImage(selectedScene.id, img.id)
                                        .then((updated) => {
                                          setImages((prev) =>
                                            prev.map((v) => ({
                                              ...v,
                                              is_approved: v.id === updated.id,
                                            })),
                                          );
                                          trackEvent("image_approved", {
                                            sceneId: selectedScene.id,
                                            variantId: img.id,
                                          });
                                        })
                                        .catch((error) => {
                                          console.error("Failed to approve image", error);
                                        });
                                    } catch (err) {
                                      console.error("Failed to approve image", err);
                                    }
                                  }}
                                  title={img.is_approved ? "Утверждено" : "Утвердить"}
                                  aria-label={img.is_approved ? "Утверждено" : "Утвердить"}
                                >
                                  ✓
                                </button>
                                <button
                                  className="graph-delete"
                                  onClick={() => {
                                    try {
                                      deleteSceneImage(selectedScene.id, img.id)
                                        .then(() => {
                                          setImages((prev) => prev.filter((v) => v.id !== img.id));
                                          trackEvent("image_deleted", {
                                            sceneId: selectedScene.id,
                                            variantId: img.id,
                                          });
                                        })
                                        .catch((error) => {
                                          console.error("Failed to delete image", error);
                                        });
                                    } catch (err) {
                                      console.error("Failed to delete image", err);
                                    }
                                  }}
                                  title="Удалить"
                                  aria-label="Удалить"
                                >
                                  ✕
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="writer-panel">
                <div className="muted">Выберите сцену, чтобы увидеть производственные детали.</div>
              </div>
            )}
          </div>
          </div>

          <section className="writer-editor" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {selectedScene ? (
              <>
                <div className="writer-panel writer-panel-primary">
                  <div className="writer-panel-header">
                    <div>
                      <h2>Сцена</h2>
                      <p className="muted">
                        {isCreativeMode
                          ? "Творческая разработка: локации по описанию слайда, фиксируем только рефы персонажей."
                          : "Сосредоточьтесь на тексте сцены. Производственные настройки справа."}
                      </p>
                    </div>
                    <div className="writer-panel-actions">
                      <button
                        className="secondary"
                        onClick={handleGenerate}
                        disabled={Boolean(selectedSceneAssetStatus?.blocked)}
                        title={selectedSceneAssetStatus?.blocked ? selectedSceneAssetStatus.reason : undefined}
                      >
                        Рендер кадра
                      </button>
                      <button className="secondary" onClick={() => openQuestPreview(selectedScene.id)}>
                        Играть с этой сцены
                      </button>
                      <button className="secondary" type="button" onClick={() => openSceneAIFill("edit")}>AI заполнение</button>
                      <button className="primary" onClick={handleWriterSave} disabled={writerSaving}>
                        {writerSaving ? "Сохранение..." : "Сохранить сцену"}
                      </button>
                    </div>
                  </div>
                  {selectedSceneAssetStatus?.blocked && (
                    <div className="asset-blocked">
                      Генерация заблокирована: {selectedSceneAssetStatus.reason}
                    </div>
                  )}
                  <div className="writer-form" style={{ display: 'flex', flexDirection: 'column', gap: '14px', width: '100%' }}>
                    <label className="writer-field" style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '100%' }}>
                      <span>Заголовок</span>
                      <input
                        className="writer-input"
                        style={{ display: 'block', width: '100%', boxSizing: 'border-box', padding: '10px 12px', borderRadius: '10px' }}
                        value={writerForm.title}
                        onChange={(event) => setWriterForm({ ...writerForm, title: event.target.value })}
                      />
                    </label>
                    <label className="writer-field" style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '100%' }}>
                      <span>Тип сцены</span>
                      <select
                        className="writer-select"
                        style={{ display: 'block', width: '100%', boxSizing: 'border-box', padding: '10px 12px', borderRadius: '10px' }}
                        value={writerForm.scene_type}
                        onChange={(event) => {
                          const value = event.target.value as "story" | "decision";
                          setWriterForm({ ...writerForm, scene_type: value });
                          setChoiceForm((prev) => ({
                            ...prev,
                            label: value === "decision" ? "Выбор" : prev.label,
                          }));
                        }}
                      >
                        <option value="story">История</option>
                        <option value="decision">Решение</option>
                      </select>
                    </label>
                    <label className="writer-field" style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '100%' }}>
                      <span>Синопсис</span>
                      <textarea
                        rows={3}
                        className="writer-textarea"
                        style={{ display: 'block', width: '100%', boxSizing: 'border-box', padding: '10px 12px', borderRadius: '10px', resize: 'vertical', minHeight: '80px' }}
                        value={writerForm.synopsis}
                        onChange={(event) => setWriterForm({ ...writerForm, synopsis: event.target.value })}
                      />
                    </label>
                    <label className="writer-field" style={{ display: 'flex', flexDirection: 'column', gap: '6px', width: '100%' }}>
                      <span>Содержание</span>
                      <textarea
                        rows={10}
                        className="writer-textarea writer-textarea-long"
                        style={{ display: 'block', width: '100%', boxSizing: 'border-box', padding: '10px 12px', borderRadius: '10px', resize: 'vertical', minHeight: '180px' }}
                        value={writerForm.content}
                        onChange={(event) => setWriterForm({ ...writerForm, content: event.target.value })}
                      />
                    </label>
                    <div className="writer-meta">
                      <span>Локация: {selectedScene.location?.name || "Не установлено"}</span>
                      <span>Персонажи: {sceneCharacters.length}</span>
                    </div>
                  </div>
                </div>

                <SceneSequenceEditor
                  scene={selectedScene}
                  projectId={projectId}
                  projectCharacters={projectCharacters}
                  creativeMode={isCreativeMode}
                  sideCollapsed={sideCollapsed}
                  orderedScenes={orderedScenes}
                  onNavigateScene={(sceneId) => {
                    const target = orderedScenes.find((item) => item.id === sceneId);
                    if (!target) return;
                    setSelectedScene(target);
                    void loadSceneAssets(target.id);
                  }}
                  images={images}
                  sceneCharacters={sceneCharacters}
                  approvedImageUrl={approvedImageUrl}
                  onSave={handleSequenceSave}
                  saving={sequenceSaving}
                  onPreviewImage={(url) => setLightboxUrl(url)}
                  generationDisabled={Boolean(selectedSceneAssetStatus?.blocked)}
                  generationDisabledReason={selectedSceneAssetStatus?.reason}
                />

                <div className="writer-panel">
                  <div className="writer-panel-header">
                    <div>
                      <h2>Ветки</h2>
                      <p className="muted">Свяжите эту сцену со следующими вехами.</p>
                    </div>
                    <span className="writer-pill">
                      {outgoingEdges.length + autoOutgoingEdges.length} связей
                      {autoOutgoingEdges.length > 0 ? ` (авто: ${autoOutgoingEdges.length})` : ""}
                    </span>
                  </div>
                  <div className="writer-choice-note muted">
                    Ключ сессии: {choiceKeyLabel}. Условия поддерживают <code>key=value</code>, <code>key!=value</code>,{" "}
                    <code>key</code>, <code>!key</code>.
                  </div>
                  {autoOutgoingEdges.length > 0 ? (
                    <div className="writer-choice-note">
                      Для этой сцены есть авто-связи по порядку сцен. Сохраните их, если хотите закрепить переходы в графе.
                      <button
                        className="secondary"
                        type="button"
                        onClick={() => {
                          void handlePersistAutoEdges();
                        }}
                        disabled={persistingAutoEdges}
                        style={{ marginLeft: 8 }}
                      >
                        {persistingAutoEdges ? "Сохранение..." : "Сохранить авто-связи"}
                      </button>
                    </div>
                  ) : null}
                  {outgoingEdges.length === 0 ? (
                    <div className="muted">Переходов пока нет.</div>
                  ) : (
                    <div className="writer-choice-list">
                      {outgoingEdges.map((edge) => {
                        const target = orderedScenes.find((scene) => scene.id === edge.to_scene_id);
                        const draft = edgeDrafts[edge.id] || {
                          label: edge.choice_label || "Продолжить",
                          value: getEdgeChoiceValue(edge),
                          condition: edge.condition || "",
                        };
                        return (
                          <div key={edge.id} className="writer-choice-card">
                            <div className="writer-choice-head">
                              <strong>{draft.label || "Продолжить"}</strong>
                              <span>→ {target?.title || "Неизвестная сцена"}</span>
                            </div>
                            <div className="writer-choice-fields">
                              <label className="writer-field">
                                <span>Метка</span>
                                <input
                                  className="writer-input"
                                  value={draft.label}
                                  onChange={(event) =>
                                    setEdgeDrafts((prev) => ({
                                      ...prev,
                                      [edge.id]: { ...draft, label: event.target.value },
                                    }))
                                  }
                                />
                              </label>
                              <label className="writer-field">
                                <span>Значение</span>
                                <input
                                  className="writer-input"
                                  value={draft.value}
                                  onChange={(event) =>
                                    setEdgeDrafts((prev) => ({
                                      ...prev,
                                      [edge.id]: { ...draft, value: event.target.value },
                                    }))
                                  }
                                  placeholder="например, виновен"
                                />
                              </label>
                              <label className="writer-field">
                                <span>Условие</span>
                                <input
                                  className="writer-input"
                                  value={draft.condition}
                                  onChange={(event) =>
                                    setEdgeDrafts((prev) => ({
                                      ...prev,
                                      [edge.id]: { ...draft, condition: event.target.value },
                                    }))
                                  }
                                  placeholder="verdict=виновен"
                                />
                              </label>
                              <button className="secondary" type="button" onClick={() => handleEdgeSave(edge)}>Обновить выбор</button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  <div className="writer-choice-form">
                    <label className="writer-field">
                      <span>Метка выбора</span>
                      <input
                        className="writer-input"
                        value={choiceForm.label}
                        onChange={(event) => setChoiceForm({ ...choiceForm, label: event.target.value })}
                        placeholder="Продолжить"
                      />
                    </label>
                    <label className="writer-field">
                      <span>Значение выбора</span>
                      <input
                        className="writer-input"
                        value={choiceForm.value}
                        onChange={(event) => setChoiceForm({ ...choiceForm, value: event.target.value })}
                        placeholder="Сохранено в сессии"
                      />
                    </label>
                    <label className="writer-field">
                      <span>Условие</span>
                      <input
                        className="writer-input"
                        value={choiceForm.condition}
                        onChange={(event) => setChoiceForm({ ...choiceForm, condition: event.target.value })}
                        placeholder="verdict=виновен"
                      />
                    </label>
                    <label className="writer-field">
                      <span>Целевая сцена</span>
                      <select
                        className="writer-select"
                        value={choiceForm.targetId}
                        onChange={(event) => setChoiceForm({ ...choiceForm, targetId: event.target.value })}
                      >
                        <option value="">Выбрать сцену</option>
                        {choiceTargets.map((scene) => (
                          <option key={scene.id} value={scene.id}>
                            {scene.title}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button className="secondary" onClick={handleAddChoice} disabled={!choiceForm.targetId}>Добавить выбор</button>
                  </div>
                </div>
              </>
            ) : (
              <div className="writer-panel">
                <div className="muted">Выберите или создайте сцену, чтобы начать писать.</div>
              </div>
            )}
          </section>

        </div>
      ) : (
        <div className={`graph-layout ${sideCollapsed ? "collapsed" : ""}`}>
          <aside className="graph-sidebar">
          <div className="graph-panel">
            <div className="graph-panel-header">
              <h2>Структура</h2>
              <span className="graph-pill">{filteredScenes.length} узлов</span>
            </div>
            <input
              className="graph-input"
              placeholder="Поиск сцен"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            <div className="graph-filter">
              <button
                className={`graph-filter-btn ${sceneFilter === "all" ? "active" : ""}`}
                onClick={() => setSceneFilter("all")}
              >Все</button>
              <button
                className={`graph-filter-btn ${sceneFilter === "story" ? "active" : ""}`}
                onClick={() => setSceneFilter("story")}
              >История</button>
              <button
                className={`graph-filter-btn ${sceneFilter === "decision" ? "active" : ""}`}
                onClick={() => setSceneFilter("decision")}
              >Выборы</button>
            </div>
            <div className="graph-list">
              {filteredScenes.map((scene) => {
                const preview = (scene.synopsis || scene.content || "").slice(0, 140);
                return (
                  <button
                    key={scene.id}
                    className={`graph-item ${selectedScene?.id === scene.id ? "selected" : ""}`}
                    onClick={() => {
                      setSelectedScene(scene);
                      void loadSceneAssets(scene.id);
                    }}
                  >
                    <div className="graph-item-header">
                      <strong>{scene.title}</strong>
                      <span className="graph-pill">{scene.scene_type}</span>
                    </div>
                    <div className="graph-item-meta">
                      {scene.location?.name || "Нет локации"}
                    </div>
                    <p>{preview}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="graph-panel">
            <div className="graph-panel-header">
              <h2>Быстрое создание</h2>
              <span className="graph-pill">Новый узел</span>
            </div>
            <div className="graph-form">
              <label className="graph-field">
                <span>Заголовок</span>
                <input
                  className="graph-input"
                  placeholder="Название сцены"
                  value={sceneForm.title}
                  onChange={(event) => setSceneForm({ ...sceneForm, title: event.target.value })}
                />
              </label>
              <label className="graph-field">
                <span>Синопсис</span>
                <textarea
                  className="graph-textarea"
                  placeholder="Краткое описание"
                  rows={2}
                  value={sceneForm.synopsis}
                  onChange={(event) => setSceneForm({ ...sceneForm, synopsis: event.target.value })}
                />
              </label>
              <label className="graph-field">
                <span>Содержание</span>
                <textarea
                  className="graph-textarea"
                  placeholder="Содержание сцены"
                  rows={3}
                  value={sceneForm.content}
                  onChange={(event) => setSceneForm({ ...sceneForm, content: event.target.value })}
                />
              </label>
              <div className="graph-radio">
                <label>
                  <input
                    type="radio"
                    checked={sceneForm.scene_type === "story"}
                    onChange={() => setSceneForm({ ...sceneForm, scene_type: "story" })}
                  />История</label>
                <label>
                  <input
                    type="radio"
                    checked={sceneForm.scene_type === "decision"}
                    onChange={() => setSceneForm({ ...sceneForm, scene_type: "decision" })}
                  />Решение</label>
              </div>
              <div className="graph-actions">
                <button className="secondary" type="button" onClick={() => openSceneAIFill("new")}>AI заполнение</button>
                <button
                  onClick={handleCreateScene}
                  disabled={creatingScene}
                  className="primary"
                >
                  {creatingScene ? "Создание..." : "Создать сцену"}
                </button>
              </div>
            </div>
          </div>

          <div className="graph-panel">
            <div className="graph-panel-header">
              <h2>Валидация</h2>
              <span className="graph-pill">Контроль качества</span>
            </div>
            {validationReport ? (
              <div className="graph-validation">
                <div className="graph-validation-summary">
                  <span className={`graph-pill ${validationSummary.error ? "danger" : ""}`}>
                    Ошибки {validationSummary.error}
                  </span>
                  <span className={`graph-pill ${validationSummary.warning ? "warn" : ""}`}>
                    Предупреждения {validationSummary.warning}
                  </span>
                  <span className="graph-pill">Инфо {validationSummary.info}</span>
                </div>
                <div className="graph-validation-list">
                  {validationReport.issues.length === 0 ? (
                    <div className="muted">Проблем не найдено.</div>
                  ) : (
                    validationReport.issues.slice(0, 5).map((issue, idx) => (
                      <div key={`${issue.code}-${idx}`} className={`graph-issue ${issue.severity}`}>
                        <strong>{issue.code}</strong>
                        <span>{issue.message}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            ) : (
              <div className="muted">Запустите валидацию, чтобы увидеть проблемы логики сюжета.</div>
            )}
          </div>
        </aside>

        <section className="graph-stage">
          <div className="graph-stage-header">
            <div>
              <h2>Карта истории</h2>
              <p className="muted">Перетаскивайте узлы, соединяйте ветки и держите обзор.</p>
            </div>
            <div className="graph-stage-actions">
              <button
                className="secondary"
                onClick={() => buildFlow(graph.scenes, graph.edges, { autoLayout: true, ignoreSaved: true })}
              >
                Перестроить
              </button>
              {autoDerivedEdges.length > 0 ? (
                <button
                  className="secondary"
                  onClick={() => {
                    void handlePersistAutoEdges();
                  }}
                  disabled={persistingAutoEdges}
                  title="Сохранить авто-связи в граф, чтобы они стали обычными переходами"
                >
                  {persistingAutoEdges
                    ? "Сохранение..."
                    : `Сохранить авто-связи (${autoDerivedEdges.length})`}
                </button>
              ) : null}
              <button className="secondary" onClick={() => flowInstance?.fitView({ padding: 0.2 })}>
                Центрировать граф
              </button>
            </div>
          </div>
          <div className="graph-canvas">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              fitView
              nodeTypes={nodeTypes}
              onInit={setFlowInstance}
              onEdgeClick={(_, edge) => {
                const sourceScene = sceneOptions.find((scene) => scene.id === edge.source);
                if (sourceScene) {
                  setSelectedScene(sourceScene);
                  void loadSceneAssets(sourceScene.id);
                }
              }}
              onNodeClick={(_, node) => {
                const scene = sceneOptions.find((s) => s.id === node.id);
                if (scene) {
                  setSelectedScene(scene);
                  void loadSceneAssets(scene.id);
                }
              }}
            >
              <Background />
              <MiniMap />
              <Controls />
            </ReactFlow>
          </div>
        </section>

        <aside className="graph-inspector">
          {selectedScene ? (
            <>
              <div className="graph-panel">
                <div className="graph-panel-header">
                  <div>
                    <h2>{selectedScene.title}</h2>
                    <p className="muted">{selectedScene.location?.name || "Нет локации"}</p>
                  </div>
                  <span className="graph-pill">{selectedScene.scene_type}</span>
                </div>
                <p>{selectedScene.synopsis || selectedScene.content}</p>
                {sceneCharacters.length > 0 && (
                  <div className="graph-inline-list">
                    <span className="graph-label">Персонажи:</span>
                    {sceneCharacters.map((c) => (
                      <span key={c.id} className="graph-chip">
                        {c.character_preset_id}
                      </span>
                    ))}
                  </div>
                )}
                {jobStatusLabel && <div className="muted">Генерация: {jobStatusLabel}</div>}
                <div className="graph-actions">
                  <button onClick={() => handleAddChild("story")} className="secondary">
                    Добавить сцену
                  </button>
                  <button onClick={() => handleAddChild("decision")} className="secondary">Добавить выбор</button>
                  <button
                    onClick={handleGenerate}
                    className="primary"
                    disabled={Boolean(selectedSceneAssetStatus?.blocked)}
                    title={selectedSceneAssetStatus?.blocked ? selectedSceneAssetStatus.reason : undefined}
                  >
                    Рендер кадра
                  </button>
                  <button onClick={() => openQuestPreview(selectedScene.id)} className="secondary">
                    Играть с этой сцены
                  </button>
                </div>
              </div>

              <div className="graph-panel graph-panel-scroll">
                <SceneEditorPanel
                  scene={selectedScene}
                  projectId={projectId}
                  onSceneUpdated={(scene) => {
                    setSelectedScene(scene);
                    setGraph((prev) =>
                      prev
                        ? {
                            ...prev,
                            scenes: prev.scenes.map((sc) => (sc.id === scene.id ? scene : sc)),
                          }
                        : prev,
                    );
                  }}
                  onImagesUpdated={setImages}
                />
              </div>

              <div className="graph-panel">
                <div className="graph-panel-header">
                  <h2>Варианты изображений</h2>
                  <span className="graph-pill">{images.length}</span>
                </div>
                {images.length === 0 ? (
                  <div className="muted">Изображений пока нет.</div>
                ) : (
                  <div className="graph-image-grid">
                    {images.map((img) => (
                      <div
                        key={img.id}
                        className={`graph-image-card ${img.is_approved ? "approved" : ""}`}
                      >
                        <img
                          src={img.url}
                          alt="вариант"
                          style={{ cursor: "zoom-in" }}
                          onClick={() => setLightboxUrl(img.url)}
                        />
                        <div className="graph-image-footer">
                          <span>{img.created_at?.slice(0, 10)}</span>
                          {selectedScene && (
                            <div className="graph-image-actions">
                              <button
                                className={img.is_approved ? "graph-approved" : "graph-approve"}
                                onClick={() => {
                                  try {
                                    approveSceneImage(selectedScene.id, img.id).then(updated => {
                                      setImages((prev) =>
                                        prev.map((v) => ({
                                          ...v,
                                          is_approved: v.id === updated.id,
                                        })),
                                      );
                                      trackEvent("image_approved", { sceneId: selectedScene.id, variantId: img.id });
                                    }).catch(error => {
                                      console.error("Failed to approve image", error);
                                    });
                                  } catch (err) {
                                    console.error("Failed to approve image", err);
                                  }
                                }}
                                title={img.is_approved ? "Утверждено" : "Утвердить"}
                                aria-label={img.is_approved ? "Утверждено" : "Утвердить"}
                              >
                                ✓
                              </button>
                              <button
                                className="graph-delete"
                                onClick={() => {
                                  try {
                                    deleteSceneImage(selectedScene.id, img.id).then(() => {
                                      setImages((prev) => prev.filter((v) => v.id !== img.id));
                                      trackEvent("image_deleted", { sceneId: selectedScene.id, variantId: img.id });
                                    }).catch(error => {
                                      console.error("Failed to delete image", error);
                                    });
                                  } catch (err) {
                                    console.error("Failed to delete image", err);
                                  }
                                }}
                                title="Удалить"
                                aria-label="Удалить"
                              >
                                ✕
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="graph-panel">
              <div className="muted">Выберите сцену, чтобы посмотреть детали.</div>
            </div>
          )}
        </aside>
      </div>
      )}

      {questPreviewOpen && questPreviewStartSceneId ? (
        <QuestPreviewModal
          graph={graph}
          startSceneId={questPreviewStartSceneId}
          onClose={() => setQuestPreviewOpen(false)}
          onOpenScene={(sceneId) => {
            const scene = graph.scenes.find((item) => item.id === sceneId);
            if (!scene) return;
            setSelectedScene(scene);
            void loadSceneAssets(scene.id);
          }}
        />
      ) : null}

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

      {assetEdit && (
        <div className="asset-edit-overlay" onClick={() => setAssetEdit(null)}>
          <div className="asset-edit-modal" onClick={(event) => event.stopPropagation()}>
            <div className="asset-edit-header">
              <div>
                <div className="asset-edit-kicker">Редактирование ассета</div>
                <h2>{assetEdit.kind === "character" ? "Персонаж" : "Локация"}</h2>
                <p className="muted">{assetEdit.item.name}</p>
              </div>
              <button className="asset-edit-close" onClick={() => setAssetEdit(null)}>x</button>
            </div>

            <div className="asset-edit-body">
              <label className="writer-field">
                <span>Название</span>
                <input
                  className="writer-input"
                  value={assetEdit.draft.name}
                  onChange={(event) => updateAssetDraft({ name: event.target.value })}
                />
              </label>
              <label className="writer-field">
                <span>Описание</span>
                <textarea
                  className="writer-textarea"
                  rows={4}
                  value={assetEdit.draft.description}
                  onChange={(event) => updateAssetDraft({ description: event.target.value })}
                />
              </label>

              {assetEdit.kind === "character" ? (
                <>
                  <label className="writer-field">
                    <span>Промпт внешности</span>
                    <textarea
                      className="writer-textarea"
                      rows={3}
                      value={assetEdit.draft.appearance_prompt}
                      onChange={(event) => updateAssetDraft({ appearance_prompt: event.target.value })}
                    />
                  </label>
                  <label className="writer-field">
                    <span>Негативный промпт</span>
                    <textarea
                      className="writer-textarea"
                      rows={2}
                      value={assetEdit.draft.negative_prompt}
                      onChange={(event) => updateAssetDraft({ negative_prompt: event.target.value })}
                    />
                  </label>
                  <label className="writer-field">
                    <span>Теги стиля</span>
                    <input
                      className="writer-input"
                      value={assetEdit.draft.style_tags}
                      onChange={(event) => updateAssetDraft({ style_tags: event.target.value })}
                      placeholder="noir, cinematic, realistic"
                    />
                  </label>
                  <label className="writer-field">
                    <span>Голос</span>
                    <input
                      className="writer-input"
                      value={assetEdit.draft.voice_profile}
                      onChange={(event) => updateAssetDraft({ voice_profile: event.target.value })}
                    />
                  </label>
                  <label className="writer-field">
                    <span>Мотивация</span>
                    <input
                      className="writer-input"
                      value={assetEdit.draft.motivation}
                      onChange={(event) => updateAssetDraft({ motivation: event.target.value })}
                    />
                  </label>
                  <label className="writer-field">
                    <span>Правовой статус</span>
                    <input
                      className="writer-input"
                      value={assetEdit.draft.legal_status}
                      onChange={(event) => updateAssetDraft({ legal_status: event.target.value })}
                    />
                  </label>
                </>
              ) : (
                <>
                  <label className="writer-field">
                    <span>Визуальный референс</span>
                    <textarea
                      className="writer-textarea"
                      rows={3}
                      value={assetEdit.draft.visual_reference}
                      onChange={(event) => updateAssetDraft({ visual_reference: event.target.value })}
                    />
                  </label>
                  <label className="writer-field">
                    <span>Негативный промпт</span>
                    <textarea
                      className="writer-textarea"
                      rows={2}
                      value={assetEdit.draft.negative_prompt}
                      onChange={(event) => updateAssetDraft({ negative_prompt: event.target.value })}
                    />
                  </label>
                  <label className="writer-field">
                    <span>Теги</span>
                    <input
                      className="writer-input"
                      value={assetEdit.draft.tags}
                      onChange={(event) => updateAssetDraft({ tags: event.target.value })}
                      placeholder="night, rain, neon"
                    />
                  </label>
                </>
              )}
            </div>

            <div className="asset-edit-actions">
              <button className="secondary" onClick={() => setAssetEdit(null)}>
                Отмена
              </button>
              <button className="primary" onClick={handleAssetEditSave} disabled={assetEditSaving}>
                {assetEditSaving ? "Сохранение..." : "Сохранить"}
              </button>
            </div>
          </div>
        </div>
      )}

      {lightboxUrl ? (
        <ImageLightbox
          url={lightboxUrl}
          title="Сгенерированное изображение"
          subtitle="Кликните вне окна или нажмите Закрыть"
          onClose={() => setLightboxUrl(null)}
        />
      ) : null}
    </div>
  );
}
