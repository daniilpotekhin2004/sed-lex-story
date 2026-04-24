import { useEffect, useMemo, useRef, useState } from "react";
import { generateDescription, generateFormFill, generateVoicePreview } from "../api/ai";
import type { AIFieldSpec } from "../api/ai";
import { getAssetUrl } from "../api/client";
import { listMaterialSets } from "../api/materialSets";
import { createTextualInversion, prepareLoraTraining } from "../api/training";
import type { CharacterPreset, GenerationOverrides, MaterialSet, ReferenceImage } from "../shared/types";
import {
  CHARACTER_REFERENCE_SLOTS,
  POSE_REFERENCE_KINDS,
  REQUIRED_CHARACTER_REFERENCE_KINDS,
  VIEW_REFERENCE_KINDS,
} from "../shared/characterReferences";
import { VOICE_PROFILE_FIELD_DESCRIPTION, VOICE_PROFILE_PLACEHOLDER } from "../shared/voiceProfile";
import AIFillModal from "./AIFillModal";
import AdvancedGenerationSettings from "./AdvancedGenerationSettings";
import { GenerationButton, GenerationStatus } from "./GenerationStatus";
import UploadButton from "./UploadButton";
import {
  formatAssetSourceLabel,
  getCharacterPreviewAssetSource,
  getReferenceAssetSource,
} from "../utils/assetSource";

const RENDER_PRESETS: Record<string, { label: string; tags: string[]; note: string }> = {
  studio: {
    label: "Студия",
    tags: ["studio lighting", "neutral background", "sharp focus"],
    note: "Чистый нейтральный свет для канонических референсов",
  },
  cinematic: {
    label: "Кинематографично",
    tags: ["cinematic lighting", "film still", "shallow depth of field"],
    note: "Киношный свет и глубина",
  },
  documentary: {
    label: "Документально",
    tags: ["natural light", "candid", "documentary photo"],
    note: "Реалистично и сдержанно",
  },
  noir: {
    label: "Нуар",
    tags: ["high contrast", "noir lighting", "dramatic shadows"],
    note: "Графичный контраст и игра теней",
  },
  sketch: {
    label: "Эскиз",
    tags: ["concept sketch", "linework", "monochrome"],
    note: "Быстрое исследование формы",
  },
  illustration: {
    label: "Иллюстрация",
    tags: ["illustration", "clean linework", "stylized render"],
    note: "Контролируемый иллюстративный стиль",
  },
};

const QUALITY_LEVELS = ["low", "medium", "high"] as const;
type RenderQuality = (typeof QUALITY_LEVELS)[number];
const VARIANCE_LEVELS = ["low", "medium", "high"] as const;
type RenderVariance = (typeof VARIANCE_LEVELS)[number];
const QUALITY_LABELS: Record<RenderQuality, string> = {
  low: "Низкое",
  medium: "Среднее",
  high: "Высокое",
};
const VARIANCE_LABELS: Record<RenderVariance, string> = {
  low: "Низкая",
  medium: "Средняя",
  high: "Высокая",
};
type RenderMode = "preview" | "final";
const QWEN_DEFAULT_STEPS = 9;

const QUALITY_PRESETS: Record<
  RenderQuality,
  { steps: number; fidelity: number; geometry: number; texture: number; lighting: number; detail: number }
> = {
  low: { steps: 16, fidelity: 45, geometry: 45, texture: 45, lighting: 45, detail: 45 },
  medium: { steps: 28, fidelity: 60, geometry: 55, texture: 60, lighting: 55, detail: 55 },
  high: { steps: 40, fidelity: 75, geometry: 70, texture: 75, lighting: 70, detail: 75 },
};

const VARIANCE_PRESETS: Record<RenderVariance, { cfg_scale: number; stylization: number; label: string }> = {
  low: { cfg_scale: 9, stylization: 20, label: "Стабильно" },
  medium: { cfg_scale: 7, stylization: 35, label: "Сбалансировано" },
  high: { cfg_scale: 5.5, stylization: 55, label: "Экспериментально" },
};

const REQUIRED_PREVIEW_FIELDS: Array<AIFieldSpec["key"]> = [
  "name",
  "description",
  "role_label",
  "style_outfit",
];
const REQUIRED_FINAL_FIELDS: Array<AIFieldSpec["key"]> = [
  "name",
  "description",
  "role_label",
  "face_age",
  "face_gender",
  "body_build",
  "hair_color",
  "style_outfit",
  "style_palette",
];

const CHARACTER_AI_FIELDS: AIFieldSpec[] = [
  { key: "name", label: "Название", type: "string" },
  { key: "description", label: "Описание", type: "string" },
  {
    key: "character_type",
    label: "Роль",
    type: "string",
    options: ["protagonist", "antagonist", "supporting", "background"],
  },
  { key: "role_label", label: "Ролевой ярлык", type: "string" },
  { key: "face_age", label: "Лицо: возраст", type: "string" },
  { key: "face_gender", label: "Лицо: пол", type: "string" },
  { key: "face_shape", label: "Лицо: форма", type: "string" },
  { key: "face_eyes", label: "Лицо: глаза", type: "string" },
  { key: "face_nose", label: "Лицо: нос", type: "string" },
  { key: "face_lips", label: "Лицо: губы", type: "string" },
  { key: "face_skin", label: "Лицо: кожа", type: "string" },
  { key: "face_expression", label: "Лицо: выражение", type: "string" },
  { key: "body_height", label: "Тело: рост", type: "string" },
  { key: "body_build", label: "Тело: телосложение", type: "string" },
  { key: "body_posture", label: "Тело: осанка", type: "string" },
  { key: "body_proportions", label: "Тело: пропорции", type: "string" },
  { key: "hair_style", label: "Волосы: стиль", type: "string" },
  { key: "hair_color", label: "Волосы: цвет", type: "string" },
  { key: "hair_length", label: "Волосы: длина", type: "string" },
  { key: "hair_facial", label: "Волосы: лицевая растительность", type: "string" },
  { key: "style_outfit", label: "Одежда", type: "string" },
  { key: "style_accessories", label: "Аксессуары", type: "string" },
  { key: "style_palette", label: "Палитра", type: "string" },
  { key: "style_materials", label: "Материалы", type: "string" },
  {
    key: "voice_profile",
    label: "Голосовой профиль",
    type: "string",
    description: VOICE_PROFILE_FIELD_DESCRIPTION,
  },
  { key: "motivation", label: "Мотивация", type: "string" },
  { key: "legal_status", label: "Правовой статус", type: "string" },
  { key: "default_pose", label: "Поза по умолчанию", type: "string" },
  { key: "negative_prompt", label: "Негативный промпт", type: "string" },
  { key: "competencies", label: "Компетенции", type: "array" },
  { key: "artifact_refs", label: "Референсы артефактов", type: "array" },
  { key: "style_tags", label: "Теги стиля", type: "array" },
  { key: "is_public", label: "Публичный пресет", type: "boolean" },
  { key: "render_preset", label: "Пресет рендера", type: "string" },
  { key: "render_fidelity", label: "Точность рендера", type: "number" },
  { key: "render_stylization", label: "Стилизованность рендера", type: "number" },
  { key: "render_geometry", label: "Геометрия рендера", type: "number" },
  { key: "render_texture", label: "Текстуры рендера", type: "number" },
  { key: "render_lighting", label: "Свет рендера", type: "number" },
  { key: "render_detail", label: "Детализация рендера", type: "number" },
  { key: "render_width", label: "Ширина рендера", type: "number" },
  { key: "render_height", label: "Высота рендера", type: "number" },
  { key: "render_steps", label: "Шаги рендера", type: "number" },
  { key: "render_cfg_scale", label: "CFG scale рендера", type: "number" },
  { key: "advanced_prompt", label: "Расширенный промпт", type: "string" },
];

type VisualIdentity = {
  role_label: string;
  lock_mode: string;
  adapter: string;
  lock_strength: number;
  face_ref: string;
  body_ref: string;
  canonical_ref: string;
  extract_face: boolean;
  attach_face: boolean;
};

type VisualFace = {
  age: string;
  gender: string;
  shape: string;
  eyes: string;
  nose: string;
  lips: string;
  skin: string;
  expression: string;
};

type VisualBody = {
  height: string;
  build: string;
  posture: string;
  proportions: string;
};

type VisualHair = {
  style: string;
  color: string;
  length: string;
  facial_hair: string;
};

type VisualStyle = {
  outfit: string;
  accessories: string;
  palette: string;
  materials: string;
};

type VisualRender = {
  preset: string;
  fidelity: number;
  stylization: number;
  geometry: number;
  texture: number;
  lighting: number;
  detail: number;
  width: number;
  height: number;
  steps: number;
  cfg_scale: number;
  seed: number | null;
};

type VisualProfile = {
  identity: VisualIdentity;
  face: VisualFace;
  body: VisualBody;
  hair: VisualHair;
  style: VisualStyle;
  render: VisualRender;
  advanced_prompt: string;
};

type RenderPayload = {
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

const DEFAULT_VISUAL_PROFILE: VisualProfile = {
  identity: {
    role_label: "",
    lock_mode: "none",
    adapter: "",
    lock_strength: 0.6,
    face_ref: "",
    body_ref: "",
    canonical_ref: "",
    extract_face: true,
    attach_face: true,
  },
  face: {
    age: "",
    gender: "",
    shape: "",
    eyes: "",
    nose: "",
    lips: "",
    skin: "",
    expression: "",
  },
  body: {
    height: "",
    build: "",
    posture: "",
    proportions: "",
  },
  hair: {
    style: "",
    color: "",
    length: "",
    facial_hair: "",
  },
  style: {
    outfit: "",
    accessories: "",
    palette: "",
    materials: "",
  },
  render: {
    preset: "studio",
    fidelity: 65,
    stylization: 25,
    geometry: 50,
    texture: 60,
    lighting: 55,
    detail: 55,
    width: 768,
    height: 768,
    steps: QWEN_DEFAULT_STEPS,
    cfg_scale: 7,
    seed: null,
  },
  advanced_prompt: "",
};

const getRecord = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
};

const readString = (record: Record<string, unknown>, key: string, fallback = ""): string => {
  const value = record[key];
  return typeof value === "string" ? value : fallback;
};

const readBoolean = (record: Record<string, unknown>, key: string, fallback = false): boolean => {
  const value = record[key];
  return typeof value === "boolean" ? value : fallback;
};

const readNumber = (record: Record<string, unknown>, key: string, fallback: number): number => {
  const value = record[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
};

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
const VOICE_PREVIEW_FALLBACK_LINE = "Это пример строки для голосового предпросмотра.";
const CYRILLIC_REGEX = /[А-Яа-яЁё]/;

const detectVoiceLanguage = (text: string) => (CYRILLIC_REGEX.test(text) ? "ru-RU" : "en-US");

const parseVoiceProfile = (profile: string) => {
  const normalized = profile.toLowerCase();
  const parts = normalized
    .split(/[;\n]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  const readPart = (label: string) => {
    const match = parts.find((part) => part.startsWith(`${label}:`));
    return match ? match.slice(label.length + 1).trim() : "";
  };
  return {
    normalized,
    persona: readPart("persona"),
    pace: readPart("pace"),
    timbre: readPart("timbre"),
    emotion: readPart("emotion"),
    scenario: readPart("scenario"),
  };
};

const deriveVoiceTuning = (profile: string) => {
  if (!profile.trim()) return { rate: 1, pitch: 1 };
  const parsed = parseVoiceProfile(profile);
  const personaSource = parsed.persona || parsed.normalized;
  const paceSource = parsed.pace || parsed.normalized;
  const timbreSource = parsed.timbre || parsed.normalized;
  const emotionSource = parsed.emotion || parsed.normalized;

  let rate = 1;
  if (paceSource.includes("fast")) rate = 1.18;
  if (paceSource.includes("slow")) rate = 0.85;
  if (emotionSource.includes("enthusiastic") || emotionSource.includes("lively")) rate += 0.05;
  if (emotionSource.includes("calm")) rate -= 0.05;
  if (emotionSource.includes("gentle")) rate -= 0.02;
  if (emotionSource.includes("serious")) rate -= 0.02;

  let pitch = 1;
  if (personaSource.includes("female")) pitch += 0.08;
  if (personaSource.includes("male")) pitch -= 0.08;
  if (personaSource.includes("young")) pitch += 0.06;
  if (personaSource.includes("elderly")) pitch -= 0.08;
  if (personaSource.includes("middle-aged") || personaSource.includes("middle aged")) pitch -= 0.01;
  if (timbreSource.includes("deep")) pitch -= 0.06;
  if (timbreSource.includes("sweet")) pitch += 0.05;
  if (timbreSource.includes("clear")) pitch += 0.02;
  if (timbreSource.includes("raspy")) pitch -= 0.03;
  if (timbreSource.includes("magnetic")) pitch -= 0.01;

  return {
    rate: clamp(rate, 0.7, 1.3),
    pitch: clamp(pitch, 0.7, 1.3),
  };
};

const parseSeed = (value: string): number | null => {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const isEmptyValue = (value: unknown) => {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return value.trim().length === 0;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value as Record<string, unknown>).length === 0;
  return false;
};

const deriveQuality = (steps: number): RenderQuality => {
  if (steps <= QUALITY_PRESETS.low.steps) return "low";
  if (steps <= QUALITY_PRESETS.medium.steps) return "medium";
  return "high";
};

const deriveVariance = (cfgScale: number): RenderVariance => {
  if (cfgScale >= VARIANCE_PRESETS.low.cfg_scale) return "low";
  if (cfgScale >= VARIANCE_PRESETS.medium.cfg_scale) return "medium";
  return "high";
};

const snapResolution = (value: number) => Math.max(256, Math.round(value / 8) * 8);

const resolvePreviewSize = (width: number, height: number) => {
  if (width <= 0 || height <= 0) return { width: 512, height: 512 };
  const ratio = width / height;
  const targetPixels = 512 * 512;
  const previewWidth = snapResolution(Math.sqrt(targetPixels * ratio));
  const previewHeight = snapResolution(previewWidth / ratio);
  return { width: previewWidth, height: previewHeight };
};

const resolveRenderParams = (
  mode: RenderMode,
  quality: RenderQuality,
  variance: RenderVariance,
  baseRender: VisualRender,
) => {
  void quality;
  const variancePreset = VARIANCE_PRESETS[variance];
  const steps = clamp(Math.round(baseRender.steps), QWEN_DEFAULT_STEPS, 80);
  const size = mode === "preview" ? resolvePreviewSize(baseRender.width, baseRender.height) : {
    width: baseRender.width,
    height: baseRender.height,
  };
  return {
    width: size.width,
    height: size.height,
    steps,
    cfg_scale: clamp(variancePreset.cfg_scale, 1, 20),
  };
};

const getSlotSize = (refs: ReferenceImage[], fallback: VisualRender) => {
  for (let i = refs.length - 1; i >= 0; i -= 1) {
    const meta = refs[i]?.meta;
    const width = typeof meta?.width === "number" ? meta.width : null;
    const height = typeof meta?.height === "number" ? meta.height : null;
    if (width && height) {
      return { width, height };
    }
  }
  return { width: fallback.width, height: fallback.height };
};

const getRefKey = (ref: ReferenceImage) => ref.id || ref.url;

const describeScale = (value: number, low: string, mid: string, high: string) => {
  if (value <= 33) return low;
  if (value <= 66) return mid;
  return high;
};

const buildPrompt = (options: {
  name: string;
  visual: VisualProfile;
  defaultPose: string;
  styleTags: string[];
}) => {
  const { name, visual, defaultPose, styleTags } = options;
  const parts: string[] = [];

  if (name.trim()) parts.push(name.trim());
  if (visual.identity.role_label.trim()) parts.push(visual.identity.role_label.trim());

  const faceParts = [
    visual.face.age,
    visual.face.gender,
    visual.face.shape,
    visual.face.eyes,
    visual.face.nose,
    visual.face.lips,
    visual.face.skin,
    visual.face.expression,
  ].filter(Boolean);
  if (faceParts.length) parts.push(faceParts.join(", "));

  const bodyParts = [visual.body.height, visual.body.build, visual.body.posture, visual.body.proportions].filter(Boolean);
  if (bodyParts.length) parts.push(bodyParts.join(", "));

  const hairParts = [visual.hair.style, visual.hair.color, visual.hair.length, visual.hair.facial_hair].filter(Boolean);
  if (hairParts.length) parts.push(hairParts.join(", "));

  const styleParts = [visual.style.outfit, visual.style.accessories, visual.style.palette, visual.style.materials].filter(Boolean);
  if (styleParts.length) parts.push(styleParts.join(", "));

  if (defaultPose.trim()) parts.push(defaultPose.trim());

  const renderTags = RENDER_PRESETS[visual.render.preset]?.tags ?? [];
  parts.push(
    describeScale(visual.render.stylization, "photorealistic", "stylized", "highly stylized"),
    describeScale(visual.render.fidelity, "painterly", "detailed", "hyper-detailed"),
    describeScale(visual.render.geometry, "soft geometry", "balanced geometry", "sharp geometry"),
    describeScale(visual.render.texture, "smooth textures", "rich textures", "hyper-textured"),
    describeScale(visual.render.lighting, "soft lighting", "balanced lighting", "dramatic lighting"),
    describeScale(visual.render.detail, "clean silhouette", "fine details", "intricate detailing"),
  );
  if (renderTags.length) parts.push(renderTags.join(", "));

  if (styleTags.length) parts.push(...styleTags);

  const cleaned = parts.map((part) => part.trim()).filter(Boolean);
  return cleaned.join(", ");
};

const normalizeProfile = (appearanceProfile: Record<string, unknown>): VisualProfile => {
  const visual = getRecord(appearanceProfile.visual_profile);
  const identity = getRecord(visual.identity);
  const face = getRecord(visual.face);
  const body = getRecord(visual.body);
  const hair = getRecord(visual.hair);
  const style = getRecord(visual.style);
  const render = getRecord(visual.render);
  const presetValue = readString(render, "preset", DEFAULT_VISUAL_PROFILE.render.preset);
  const preset = RENDER_PRESETS[presetValue] ? presetValue : DEFAULT_VISUAL_PROFILE.render.preset;

  return {
    identity: {
      role_label: readString(identity, "role_label", DEFAULT_VISUAL_PROFILE.identity.role_label),
      lock_mode: readString(identity, "lock_mode", DEFAULT_VISUAL_PROFILE.identity.lock_mode),
      adapter: readString(identity, "adapter", DEFAULT_VISUAL_PROFILE.identity.adapter),
      lock_strength: clamp(readNumber(identity, "lock_strength", DEFAULT_VISUAL_PROFILE.identity.lock_strength), 0, 1),
      face_ref: readString(identity, "face_ref", DEFAULT_VISUAL_PROFILE.identity.face_ref),
      body_ref: readString(identity, "body_ref", DEFAULT_VISUAL_PROFILE.identity.body_ref),
      canonical_ref: readString(identity, "canonical_ref", DEFAULT_VISUAL_PROFILE.identity.canonical_ref),
      extract_face: readBoolean(identity, "extract_face", DEFAULT_VISUAL_PROFILE.identity.extract_face),
      attach_face: readBoolean(identity, "attach_face", DEFAULT_VISUAL_PROFILE.identity.attach_face),
    },
    face: {
      age: readString(face, "age", DEFAULT_VISUAL_PROFILE.face.age),
      gender: readString(face, "gender", DEFAULT_VISUAL_PROFILE.face.gender),
      shape: readString(face, "shape", DEFAULT_VISUAL_PROFILE.face.shape),
      eyes: readString(face, "eyes", DEFAULT_VISUAL_PROFILE.face.eyes),
      nose: readString(face, "nose", DEFAULT_VISUAL_PROFILE.face.nose),
      lips: readString(face, "lips", DEFAULT_VISUAL_PROFILE.face.lips),
      skin: readString(face, "skin", DEFAULT_VISUAL_PROFILE.face.skin),
      expression: readString(face, "expression", DEFAULT_VISUAL_PROFILE.face.expression),
    },
    body: {
      height: readString(body, "height", DEFAULT_VISUAL_PROFILE.body.height),
      build: readString(body, "build", DEFAULT_VISUAL_PROFILE.body.build),
      posture: readString(body, "posture", DEFAULT_VISUAL_PROFILE.body.posture),
      proportions: readString(body, "proportions", DEFAULT_VISUAL_PROFILE.body.proportions),
    },
    hair: {
      style: readString(hair, "style", DEFAULT_VISUAL_PROFILE.hair.style),
      color: readString(hair, "color", DEFAULT_VISUAL_PROFILE.hair.color),
      length: readString(hair, "length", DEFAULT_VISUAL_PROFILE.hair.length),
      facial_hair: readString(hair, "facial_hair", DEFAULT_VISUAL_PROFILE.hair.facial_hair),
    },
    style: {
      outfit: readString(style, "outfit", DEFAULT_VISUAL_PROFILE.style.outfit),
      accessories: readString(style, "accessories", DEFAULT_VISUAL_PROFILE.style.accessories),
      palette: readString(style, "palette", DEFAULT_VISUAL_PROFILE.style.palette),
      materials: readString(style, "materials", DEFAULT_VISUAL_PROFILE.style.materials),
    },
    render: {
      preset,
      fidelity: clamp(readNumber(render, "fidelity", DEFAULT_VISUAL_PROFILE.render.fidelity), 0, 100),
      stylization: clamp(readNumber(render, "stylization", DEFAULT_VISUAL_PROFILE.render.stylization), 0, 100),
      geometry: clamp(readNumber(render, "geometry", DEFAULT_VISUAL_PROFILE.render.geometry), 0, 100),
      texture: clamp(readNumber(render, "texture", DEFAULT_VISUAL_PROFILE.render.texture), 0, 100),
      lighting: clamp(readNumber(render, "lighting", DEFAULT_VISUAL_PROFILE.render.lighting), 0, 100),
      detail: clamp(readNumber(render, "detail", DEFAULT_VISUAL_PROFILE.render.detail), 0, 100),
      width: clamp(readNumber(render, "width", DEFAULT_VISUAL_PROFILE.render.width), 256, 2048),
      height: clamp(readNumber(render, "height", DEFAULT_VISUAL_PROFILE.render.height), 256, 2048),
      steps: clamp(
        (() => {
          const raw = readNumber(render, "steps", DEFAULT_VISUAL_PROFILE.render.steps);
          return raw === 28 ? QWEN_DEFAULT_STEPS : raw;
        })(),
        QWEN_DEFAULT_STEPS,
        80,
      ),
      cfg_scale: clamp(readNumber(render, "cfg_scale", DEFAULT_VISUAL_PROFILE.render.cfg_scale), 1, 20),
      seed: typeof render.seed === "number" ? render.seed : DEFAULT_VISUAL_PROFILE.render.seed,
    },
    advanced_prompt: readString(visual, "advanced_prompt", DEFAULT_VISUAL_PROFILE.advanced_prompt),
  };
};

const isReferenceImage = (value: unknown): value is ReferenceImage => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return typeof record.url === "string" && typeof record.kind === "string";
};

const ListEditor = ({
  label,
  items,
  onChange,
  placeholder,
}: {
  label: string;
  items: string[];
  onChange: (items: string[]) => void;
  placeholder?: string;
}) => {
  const [draft, setDraft] = useState("");

  const addItem = () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    if (!items.includes(trimmed)) {
      onChange([...items, trimmed]);
    }
    setDraft("");
  };

  const removeItem = (value: string) => {
    onChange(items.filter((item) => item !== value));
  };

  return (
    <div className="cvs-list">
      <label className="cvs-field">
        <span>{label}</span>
        <div className="cvs-list-input">
          <input
            className="cvs-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={placeholder}
          />
          <button className="secondary" type="button" onClick={addItem}>Добавить</button>
        </div>
      </label>
      {items.length > 0 && (
        <div className="cvs-chip-row">
              {items.map((item) => (
                <span key={item} className="cvs-chip">
                  {item}
                  <button type="button" onClick={() => removeItem(item)}>
                    x
                  </button>
                </span>
              ))}
        </div>
      )}
    </div>
  );
};

const SliderField = ({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) => (
  <label className="cvs-field cvs-slider">
    <span>{label}</span>
    <div className="cvs-slider-row">
      <input
        className="cvs-range"
        type="range"
        min={0}
        max={100}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <span className="cvs-slider-value">{value}</span>
    </div>
  </label>
);

export default function CharacterVisualStudio({
  character,
  projectId,
  saving,
  sketching,
  sheeting,
  onSave,
  onPatch,
  onDelete,
  onGenerateSketch,
  onGenerateSheet,
  onRegenerateReference,
  onUploadReference,
  onRender,
  onOpenLightbox,
  allowPublic = true,
  requiredReferenceKinds,
  simplifiedMode = false,
}: {
  character: CharacterPreset | null;
  projectId?: string;
  saving: boolean;
  sketching: boolean;
  sheeting: boolean;
  onSave: (payload: Partial<CharacterPreset>, characterId?: string) => Promise<void>;
  onPatch: (characterId: string, payload: Partial<CharacterPreset>) => Promise<void>;
  onDelete?: (characterId: string) => Promise<void>;
  onGenerateSketch?: (characterId: string) => Promise<void>;
  onGenerateSheet?: (
    characterId: string,
    options?: { overrides?: GenerationOverrides; kinds?: string[] },
  ) => Promise<void>;
  onRegenerateReference?: (
    characterId: string,
    kind: string,
    overrides?: GenerationOverrides,
  ) => Promise<void>;
  onUploadReference?: (
    characterId: string,
    kind: string,
    file: File,
    options?: { setAsPreview?: boolean },
  ) => Promise<void>;
  onRender?: (characterId: string, payload: RenderPayload) => Promise<void>;
  onOpenLightbox?: (payload: { url: string; title?: string; subtitle?: string }) => void;
  allowPublic?: boolean;
  requiredReferenceKinds?: string[];
  simplifiedMode?: boolean;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [characterType, setCharacterType] = useState("supporting");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [defaultPose, setDefaultPose] = useState("");
  const [voiceProfile, setVoiceProfile] = useState("");
  const [motivation, setMotivation] = useState("");
  const [legalStatus, setLegalStatus] = useState("");
  const [competencies, setCompetencies] = useState<string[]>([]);
  const [artifactRefs, setArtifactRefs] = useState<string[]>([]);
  const [styleTags, setStyleTags] = useState<string[]>([]);
  const [embeddings, setEmbeddings] = useState<string[]>([]);
  const [loraModels, setLoraModels] = useState<{ name: string; weight: number }[]>([]);
  const [isPublic, setIsPublic] = useState(false);
  const [materialSets, setMaterialSets] = useState<MaterialSet[]>([]);
  const [materialSetId, setMaterialSetId] = useState("");
  const [embeddingToken, setEmbeddingToken] = useState("");
  const [embeddingInitText, setEmbeddingInitText] = useState("");
  const [embeddingVectors, setEmbeddingVectors] = useState(1);
  const [trainingLabel, setTrainingLabel] = useState("");
  const [trainingCaption, setTrainingCaption] = useState("");
  const [embeddingBusy, setEmbeddingBusy] = useState(false);
  const [trainingBusy, setTrainingBusy] = useState(false);
  const [trainingNote, setTrainingNote] = useState<string | null>(null);

  const [visualProfile, setVisualProfile] = useState<VisualProfile>(DEFAULT_VISUAL_PROFILE);
  const [appearanceProfileBase, setAppearanceProfileBase] = useState<Record<string, unknown>>({});
  const [advancedPromptEnabled, setAdvancedPromptEnabled] = useState(false);
  const [advancedPrompt, setAdvancedPrompt] = useState("");

  const [renderMode, setRenderMode] = useState<RenderMode>("preview");
  const [seedMode, setSeedMode] = useState<"same" | "new">("same");
  const [advisorTab, setAdvisorTab] = useState<"recommend" | "explain">("recommend");
  const [missingFillLoading, setMissingFillLoading] = useState(false);
  const [missingFillError, setMissingFillError] = useState<string | null>(null);
  const [slotRendering, setSlotRendering] = useState<Record<string, boolean>>({});

  const [renderKind, setRenderKind] = useState("variant");
  const [renderLabel, setRenderLabel] = useState("");
  const [renderCount, setRenderCount] = useState(4);
  const [renderPromptOverride, setRenderPromptOverride] = useState("");
  const [renderNegativeOverride, setRenderNegativeOverride] = useState("");
  const [renderSeed, setRenderSeed] = useState("");
  const [showOptionalRefs, setShowOptionalRefs] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [sketchError, setSketchError] = useState<string | null>(null);

  const [advancedGeneration, setAdvancedGeneration] = useState<GenerationOverrides>({
    sampler: null,
    scheduler: null,
    model_id: null,
    vae_id: null,
    loras: [],
    pipeline_profile_id: null,
    pipeline_profile_version: null,
  });

  const [filterKind, setFilterKind] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [uploadingKind, setUploadingKind] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [aiDescriptionLoading, setAiDescriptionLoading] = useState(false);
  const [aiDescriptionError, setAiDescriptionError] = useState<string | null>(null);
  const [aiFillOpen, setAiFillOpen] = useState(false);
  const [voicePreviewText, setVoicePreviewText] = useState("");
  const [voicePreviewError, setVoicePreviewError] = useState<string | null>(null);
  const [voicePreviewLoading, setVoicePreviewLoading] = useState(false);
  const [voicePreviewPlaying, setVoicePreviewPlaying] = useState(false);
  const voicePreviewAudioRef = useRef<HTMLAudioElement | null>(null);
  const voicePreviewUrlRef = useRef<string | null>(null);
  const voicePreviewUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  const [loraDraft, setLoraDraft] = useState({ name: "", weight: 0.7 });

  const openLightboxAsset = (
    assetPath: string | null | undefined,
    subtitle?: string,
    title?: string,
  ) => {
    if (!onOpenLightbox) return;
    const url = getAssetUrl(assetPath);
    if (!url) return;
    onOpenLightbox({ url, title, subtitle });
  };

  const advancedSettingsValue: GenerationOverrides = useMemo(
    () => ({
      width: visualProfile.render.width,
      height: visualProfile.render.height,
      steps: visualProfile.render.steps,
      cfg_scale: visualProfile.render.cfg_scale,
      negative_prompt: renderNegativeOverride.trim() ? renderNegativeOverride.trim() : null,
      sampler: advancedGeneration.sampler ?? null,
      scheduler: advancedGeneration.scheduler ?? null,
      model_id: advancedGeneration.model_id ?? null,
      vae_id: advancedGeneration.vae_id ?? null,
      loras: (advancedGeneration.loras as any) ?? [],
      pipeline_profile_id: advancedGeneration.pipeline_profile_id ?? null,
      pipeline_profile_version: advancedGeneration.pipeline_profile_version ?? null,
      seed: parseSeed(renderSeed),
    }),
    [
      visualProfile.render.width,
      visualProfile.render.height,
      visualProfile.render.steps,
      visualProfile.render.cfg_scale,
      renderNegativeOverride,
      advancedGeneration.sampler,
      advancedGeneration.scheduler,
      advancedGeneration.model_id,
      advancedGeneration.vae_id,
      advancedGeneration.loras,
      advancedGeneration.pipeline_profile_id,
      advancedGeneration.pipeline_profile_version,
      renderSeed,
    ]
  );

  const handleAdvancedSettingsChange = (next: GenerationOverrides) => {
    const width = next.width;
    const height = next.height;
    const steps = next.steps;
    const cfgScale = next.cfg_scale;

    // Apply technical overrides
    setAdvancedGeneration((prev) => ({
      ...prev,
      sampler: next.sampler ?? null,
      scheduler: next.scheduler ?? null,
      model_id: next.model_id ?? null,
      vae_id: next.vae_id ?? null,
      loras: next.loras ?? [],
      pipeline_profile_id: next.pipeline_profile_id ?? null,
      pipeline_profile_version: next.pipeline_profile_version ?? null,
    }));

    // Keep legacy render UI in sync (these are always numbers in the visual profile)
    if (typeof width === "number" && Number.isFinite(width)) {
      setVisualProfile((prev) => ({ ...prev, render: { ...prev.render, width } }));
    }
    if (typeof height === "number" && Number.isFinite(height)) {
      setVisualProfile((prev) => ({ ...prev, render: { ...prev.render, height } }));
    }
    if (typeof steps === "number" && Number.isFinite(steps)) {
      setVisualProfile((prev) => ({ ...prev, render: { ...prev.render, steps } }));
    }
    if (typeof cfgScale === "number" && Number.isFinite(cfgScale)) {
      setVisualProfile((prev) => ({ ...prev, render: { ...prev.render, cfg_scale: cfgScale } }));
    }

    if (typeof next.negative_prompt === "string") {
      setRenderNegativeOverride(next.negative_prompt);
    } else if (next.negative_prompt === null) {
      setRenderNegativeOverride("");
    }

    if (typeof next.seed === "number" && Number.isFinite(next.seed)) {
      setRenderSeed(String(Math.trunc(next.seed)));
    } else if (next.seed === null) {
      // Explicitly cleared
      setRenderSeed("");
    }
  };

  useEffect(() => {
    if (!character) {
      setName("");
      setDescription("");
      setCharacterType("supporting");
      setNegativePrompt("");
      setDefaultPose("");
      setVoiceProfile("");
      setMotivation("");
      setLegalStatus("");
      setCompetencies([]);
      setArtifactRefs([]);
      setStyleTags([]);
      setEmbeddings([]);
      setLoraModels([]);
      setIsPublic(false);
      setMaterialSets([]);
      setMaterialSetId("");
      setEmbeddingToken("");
      setEmbeddingInitText("");
      setEmbeddingVectors(1);
      setTrainingLabel("");
      setTrainingCaption("");
      setEmbeddingBusy(false);
      setTrainingBusy(false);
      setTrainingNote(null);
      setVisualProfile(DEFAULT_VISUAL_PROFILE);
      setAppearanceProfileBase({});
      setAdvancedPromptEnabled(false);
      setAdvancedPrompt("");
      setRenderMode("preview");
      setSeedMode("same");
      setAdvisorTab("recommend");
      setMissingFillLoading(false);
      setMissingFillError(null);
      setSlotRendering({});
      setRenderKind("variant");
      setRenderLabel("");
      setRenderCount(1);
      setRenderPromptOverride("");
      setRenderNegativeOverride("");
      setRenderSeed("");
      setAdvancedGeneration({
        sampler: null,
        scheduler: null,
        model_id: null,
        vae_id: null,
        loras: [],
        pipeline_profile_id: null,
        pipeline_profile_version: null,
      });
      setRendering(false);
      setFilterKind("all");
      setSearchQuery("");
      setIsFullscreen(false);
      setAiDescriptionLoading(false);
      setAiDescriptionError(null);
      setVoicePreviewText("");
      setVoicePreviewError(null);
      setVoicePreviewLoading(false);
      setVoicePreviewPlaying(false);
      stopVoicePreview();
      return;
    }

    setName(character.name || "");
    setDescription(character.description || "");
    setCharacterType(character.character_type || "supporting");
    setNegativePrompt(character.negative_prompt || "");
    setDefaultPose(character.default_pose || "");
    setVoiceProfile(character.voice_profile || "");
    setMotivation(character.motivation || "");
    setLegalStatus(character.legal_status || "");
    setCompetencies(character.competencies || []);
    setArtifactRefs(character.artifact_refs || []);
    setStyleTags(character.style_tags || []);
    setEmbeddings(character.embeddings || []);
    setLoraModels(character.lora_models || []);
    setIsPublic(Boolean(character.is_public));
    setEmbeddingToken(character.anchor_token || "");
    setEmbeddingInitText("");
    setEmbeddingVectors(1);
    setTrainingLabel(character.name ? `${character.name} v1` : "");
    setTrainingCaption("");
    setTrainingNote(null);
    setAiDescriptionLoading(false);
    setAiDescriptionError(null);
    setVoicePreviewText("");
    setVoicePreviewError(null);
    setVoicePreviewLoading(false);
    setVoicePreviewPlaying(false);
    stopVoicePreview();

    const profileBase = getRecord(character.appearance_profile);
    setAppearanceProfileBase(profileBase);
    const normalized = normalizeProfile(profileBase);
    setVisualProfile(normalized);
    setRenderMode("preview");
    setSeedMode("same");
    setAdvisorTab("recommend");
    setMissingFillError(null);
    setSlotRendering({});

    const hasVisualProfile = Boolean(Object.keys(getRecord(profileBase.visual_profile)).length);
    if (hasVisualProfile) {
      setAdvancedPrompt(normalized.advanced_prompt);
      setAdvancedPromptEnabled(Boolean(normalized.advanced_prompt));
    } else {
      setAdvancedPrompt(character.appearance_prompt || "");
      setAdvancedPromptEnabled(Boolean(character.appearance_prompt));
    }
  }, [character?.id]);

  useEffect(() => {
    if (!projectId || !character?.id) {
      setMaterialSets([]);
      setMaterialSetId("");
      return;
    }
    let active = true;
    listMaterialSets(projectId, { asset_type: "character", asset_id: character.id })
      .then((items) => {
        if (!active) return;
        setMaterialSets(items);
        if (!materialSetId && items.length > 0) {
          setMaterialSetId(items[0].id);
        }
      })
      .catch((error) => {
        console.error("Failed to load material sets:", error);
      });
    return () => {
      active = false;
    };
  }, [projectId, character?.id]);

  useEffect(() => {
    if (!isFullscreen) return;
    document.body.classList.add("cvs-lock");
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsFullscreen(false);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => {
      document.body.classList.remove("cvs-lock");
      window.removeEventListener("keydown", handleKey);
    };
  }, [isFullscreen]);

  useEffect(() => {
    return () => {
      cleanupVoicePreviewAudio();
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const computedPrompt = useMemo(
    () =>
      buildPrompt({
        name,
        visual: visualProfile,
        defaultPose,
        styleTags,
      }),
    [name, visualProfile, defaultPose, styleTags],
  );

  const voicePreviewFallbackText = useMemo(() => {
    if (name.trim()) return `Hello, I'm ${name.trim()}.`;
    if (visualProfile.identity.role_label.trim()) {
      return `This is the ${visualProfile.identity.role_label.trim()} speaking.`;
    }
    return VOICE_PREVIEW_FALLBACK_LINE;
  }, [name, visualProfile.identity.role_label]);

  const aiContext = useMemo(() => {
    const parts = [
      name ? `name: ${name}` : null,
      characterType ? `role: ${characterType}` : null,
      visualProfile.identity.role_label ? `role label: ${visualProfile.identity.role_label}` : null,
      description ? `description: ${description}` : null,
      computedPrompt ? `computed prompt: ${computedPrompt}` : null,
      negativePrompt ? `negative prompt: ${negativePrompt}` : null,
      voiceProfile ? `voice: ${voiceProfile}` : null,
      motivation ? `motivation: ${motivation}` : null,
      legalStatus ? `legal status: ${legalStatus}` : null,
      defaultPose ? `default pose: ${defaultPose}` : null,
    ].filter(Boolean);
    return parts.join("\n");
  }, [
    name,
    characterType,
    visualProfile.identity.role_label,
    description,
    computedPrompt,
    negativePrompt,
    voiceProfile,
    motivation,
    legalStatus,
    defaultPose,
  ]);

  const aiCurrentValues = useMemo<Record<string, unknown>>(
    () => ({
      name,
      description,
      character_type: characterType,
      role_label: visualProfile.identity.role_label,
      face_age: visualProfile.face.age,
      face_gender: visualProfile.face.gender,
      face_shape: visualProfile.face.shape,
      face_eyes: visualProfile.face.eyes,
      face_nose: visualProfile.face.nose,
      face_lips: visualProfile.face.lips,
      face_skin: visualProfile.face.skin,
      face_expression: visualProfile.face.expression,
      body_height: visualProfile.body.height,
      body_build: visualProfile.body.build,
      body_posture: visualProfile.body.posture,
      body_proportions: visualProfile.body.proportions,
      hair_style: visualProfile.hair.style,
      hair_color: visualProfile.hair.color,
      hair_length: visualProfile.hair.length,
      hair_facial: visualProfile.hair.facial_hair,
      style_outfit: visualProfile.style.outfit,
      style_accessories: visualProfile.style.accessories,
      style_palette: visualProfile.style.palette,
      style_materials: visualProfile.style.materials,
      voice_profile: voiceProfile,
      motivation,
      legal_status: legalStatus,
      default_pose: defaultPose,
      negative_prompt: negativePrompt,
      competencies,
      artifact_refs: artifactRefs,
      style_tags: styleTags,
      is_public: isPublic,
      render_preset: visualProfile.render.preset,
      render_fidelity: visualProfile.render.fidelity,
      render_stylization: visualProfile.render.stylization,
      render_geometry: visualProfile.render.geometry,
      render_texture: visualProfile.render.texture,
      render_lighting: visualProfile.render.lighting,
      render_detail: visualProfile.render.detail,
      render_width: visualProfile.render.width,
      render_height: visualProfile.render.height,
      render_steps: visualProfile.render.steps,
      render_cfg_scale: visualProfile.render.cfg_scale,
      advanced_prompt: advancedPrompt,
    }),
    [
      name,
      description,
      characterType,
      visualProfile,
      voiceProfile,
      motivation,
      legalStatus,
      defaultPose,
      negativePrompt,
      competencies,
      artifactRefs,
      styleTags,
      isPublic,
      advancedPrompt,
    ],
  );

  const renderQuality = useMemo(
    () => deriveQuality(visualProfile.render.steps),
    [visualProfile.render.steps],
  );
  const renderVariance = useMemo(
    () => deriveVariance(visualProfile.render.cfg_scale),
    [visualProfile.render.cfg_scale],
  );

  const missingFields = useMemo(() => {
    const requiredKeys = renderMode === "preview" ? REQUIRED_PREVIEW_FIELDS : REQUIRED_FINAL_FIELDS;
    const fieldSpecs = requiredKeys
      .map((key) => CHARACTER_AI_FIELDS.find((field) => field.key === key))
      .filter((field): field is AIFieldSpec => Boolean(field));
    return fieldSpecs.filter((field) => isEmptyValue(aiCurrentValues[field.key]));
  }, [aiCurrentValues, renderMode]);

  const referenceImages = useMemo(() => {
    const raw = character?.reference_images || [];
    return raw.filter(isReferenceImage);
  }, [character?.reference_images]);

  const effectiveRequiredReferenceKinds = useMemo(() => {
    if (!requiredReferenceKinds || requiredReferenceKinds.length === 0) {
      return REQUIRED_CHARACTER_REFERENCE_KINDS;
    }
    const validKinds = new Set(CHARACTER_REFERENCE_SLOTS.map((slot) => slot.kind));
    const normalized = requiredReferenceKinds.filter((kind) => validKinds.has(kind));
    return normalized.length > 0 ? normalized : REQUIRED_CHARACTER_REFERENCE_KINDS;
  }, [requiredReferenceKinds]);

  const requiredReferenceSlots = useMemo(
    () => CHARACTER_REFERENCE_SLOTS.filter((slot) => effectiveRequiredReferenceKinds.includes(slot.kind)),
    [effectiveRequiredReferenceKinds],
  );

  const slotReferences = useMemo(() => {
    const map: Record<string, ReferenceImage[]> = {};
    referenceImages.forEach((ref) => {
      if (!map[ref.kind]) {
        map[ref.kind] = [];
      }
      map[ref.kind].push(ref);
    });
    return map;
  }, [referenceImages]);

  const latestSeed = useMemo(() => {
    for (let i = referenceImages.length - 1; i >= 0; i -= 1) {
      const seed = referenceImages[i]?.meta?.seed;
      if (typeof seed === "number" && Number.isFinite(seed)) return seed;
    }
    return null;
  }, [referenceImages]);

  const activeSeed = useMemo(() => parseSeed(renderSeed) ?? latestSeed, [renderSeed, latestSeed]);

  const recentVariants = useMemo(() => {
    const pool = referenceImages.filter((ref) => ["variant", "canonical"].includes(ref.kind));
    return pool.slice(-4).reverse();
  }, [referenceImages]);

  const hasPreview = Boolean(character?.preview_image_url);
  const previewSource = useMemo(() => getCharacterPreviewAssetSource(character), [character]);

  const sketchGeneration = useMemo(
    () => ({
      isGenerating: sketching,
      progress: sketching ? 45 : 0,
      stage: sketching ? "Генерация" : "",
      error: sketchError || undefined,
    }),
    [sketching, sketchError],
  );

  const handleSketchGeneration = async (characterId: string) => {
    if (!onGenerateSketch) return;
    setSketchError(null);
    try {
      await onGenerateSketch(characterId);
    } catch (err: any) {
      setSketchError(err?.message || "Не удалось сгенерировать скетч.");
    }
  };

  const referenceStatus = useMemo(() => {
    const kinds = new Set(referenceImages.map((ref) => ref.kind));
    const requiredSlots = requiredReferenceSlots;
    const optionalSlots = CHARACTER_REFERENCE_SLOTS.filter((slot) => !effectiveRequiredReferenceKinds.includes(slot.kind));
    const missingRequired = requiredSlots.filter((slot) => !kinds.has(slot.kind));
    const missingOptional = optionalSlots.filter((slot) => !kinds.has(slot.kind));
    const missingViews = missingRequired.filter((slot) => VIEW_REFERENCE_KINDS.includes(slot.kind));
    const missingPoses = missingRequired.filter((slot) => POSE_REFERENCE_KINDS.includes(slot.kind));
    return {
      requiredSlots,
      optionalSlots,
      missingRequired,
      missingOptional,
      missingViews,
      missingPoses,
      isComplete: missingRequired.length === 0,
    };
  }, [referenceImages, effectiveRequiredReferenceKinds, requiredReferenceSlots]);

  const requiredKindsForGeneration = useMemo(() => {
    const missingKinds = referenceStatus.missingRequired.map((slot) => slot.kind);
    return missingKinds.length > 0 ? missingKinds : effectiveRequiredReferenceKinds;
  }, [referenceStatus.missingRequired, effectiveRequiredReferenceKinds]);

  const sheetProgress = useMemo(() => {
    const total = referenceStatus.requiredSlots.length;
    const ready = Math.max(0, total - referenceStatus.missingRequired.length);
    return { ready, total };
  }, [referenceStatus]);

  const fullSetProgress = useMemo(() => {
    const total = CHARACTER_REFERENCE_SLOTS.length;
    const ready = Math.max(0, total - referenceStatus.missingRequired.length - referenceStatus.missingOptional.length);
    return { ready, total };
  }, [referenceStatus]);

  const recommendationPlans = useMemo(() => {
    const buildPlan = (
      id: string,
      label: string,
      quality: RenderQuality,
      variance: RenderVariance,
      note: string,
    ) => {
      const params = resolveRenderParams(renderMode, quality, variance, visualProfile.render);
      return {
        id,
        label,
        quality,
        variance,
        note,
        ...params,
      };
    };
    return [
      buildPlan("fast", "Быстро", "low", "high", "Быстрая итерация с максимальной вариативностью."),
      buildPlan("balanced", "Сбалансировано", "medium", "medium", "Стабильные предпросмотры с хорошей детализацией."),
      buildPlan("quality", "Качество", "high", "low", "Упор на финальный рендер."),
    ];
  }, [renderMode, visualProfile.render]);

  const explainText = useMemo(() => {
    const preset = RENDER_PRESETS[visualProfile.render.preset];
    const modeLine = renderMode === "preview"
      ? "Предпросмотр делает упор на скорость, снижая разрешение и количество шагов."
      : "Финальный режим делает упор на разрешение и детализацию.";
    const qualityLine = `Качество: ${QUALITY_LABELS[renderQuality].toLowerCase()} (шаги ${visualProfile.render.steps}).`;
    const variancePreset = VARIANCE_PRESETS[renderVariance];
    const varianceLine = `Вариативность: ${VARIANCE_LABELS[renderVariance].toLowerCase()} (${variancePreset.label.toLowerCase()}, CFG ${visualProfile.render.cfg_scale}).`;
    const goalLine = preset ? `Целевой пресет: ${preset.label} — ${preset.note}` : "";
    return [modeLine, qualityLine, varianceLine, goalLine].filter(Boolean).join(" ");
  }, [renderMode, renderQuality, renderVariance, visualProfile.render]);

  const kindFilters = useMemo(() => {
    const kinds = new Set(referenceImages.map((ref) => ref.kind));
    return ["all", ...Array.from(kinds).sort()];
  }, [referenceImages]);

  const filteredReferences = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return referenceImages.filter((ref) => {
      if (filterKind !== "all" && ref.kind !== filterKind) return false;
      if (!query) return true;
      const label = ref.label || (typeof ref.meta?.label === "string" ? ref.meta.label : "");
      return `${ref.kind} ${label}`.toLowerCase().includes(query);
    });
  }, [referenceImages, filterKind, searchQuery]);

  const faceRef = useMemo(() => {
    if (!visualProfile.identity.face_ref) return null;
    return referenceImages.find((ref) => getRefKey(ref) === visualProfile.identity.face_ref) || null;
  }, [referenceImages, visualProfile.identity.face_ref]);

  const bodyRef = useMemo(() => {
    if (!visualProfile.identity.body_ref) return null;
    return referenceImages.find((ref) => getRefKey(ref) === visualProfile.identity.body_ref) || null;
  }, [referenceImages, visualProfile.identity.body_ref]);

  const canonicalRef = useMemo(() => {
    if (!visualProfile.identity.canonical_ref) return null;
    return referenceImages.find((ref) => getRefKey(ref) === visualProfile.identity.canonical_ref) || null;
  }, [referenceImages, visualProfile.identity.canonical_ref]);

  const missingViewLabels = referenceStatus.missingViews.map((slot) =>
    slot.note ? `${slot.label} (${slot.note})` : slot.label,
  );
  const missingPoseLabels = referenceStatus.missingPoses.map((slot) =>
    slot.note ? `${slot.label} (${slot.note})` : slot.label,
  );
  const missingOptionalLabels = referenceStatus.missingOptional.map((slot) =>
    slot.note ? `${slot.label} (${slot.note})` : slot.label,
  );

  const canSave = Boolean(name.trim()) && Boolean((advancedPromptEnabled ? advancedPrompt : computedPrompt).trim());

  const handleSave = async () => {
    if (!canSave) return;
    const appearancePrompt = advancedPromptEnabled && advancedPrompt.trim() ? advancedPrompt.trim() : computedPrompt;
    const mergedProfile = {
      ...appearanceProfileBase,
      visual_profile: {
        ...visualProfile,
        advanced_prompt: advancedPromptEnabled ? advancedPrompt.trim() : "",
      },
    };

    const payload: Partial<CharacterPreset> = {
      name: name.trim(),
      description: description.trim() ? description.trim() : null,
      character_type: characterType,
      appearance_prompt: appearancePrompt || name.trim(),
      negative_prompt: negativePrompt.trim() ? negativePrompt.trim() : null,
      appearance_profile: mergedProfile,
      lora_models: loraModels.length ? loraModels : null,
      embeddings: embeddings.length ? embeddings : null,
      style_tags: styleTags.length ? styleTags : null,
      default_pose: defaultPose.trim() ? defaultPose.trim() : null,
      voice_profile: voiceProfile.trim() ? voiceProfile.trim() : null,
      motivation: motivation.trim() ? motivation.trim() : null,
      legal_status: legalStatus.trim() ? legalStatus.trim() : null,
      competencies: competencies.length ? competencies : null,
      artifact_refs: artifactRefs.length ? artifactRefs : null,
      is_public: allowPublic ? isPublic : false,
      relationships: character?.relationships || null,
    };

    await onSave(payload, character?.id);
  };

  const applyQuality = (quality: RenderQuality) => {
    const preset = QUALITY_PRESETS[quality];
    setVisualProfile((prev) => ({
      ...prev,
      render: {
        ...prev.render,
        fidelity: preset.fidelity,
        geometry: preset.geometry,
        texture: preset.texture,
        lighting: preset.lighting,
        detail: preset.detail,
      },
    }));
  };

  const applyVariance = (variance: RenderVariance) => {
    const preset = VARIANCE_PRESETS[variance];
    setVisualProfile((prev) => ({
      ...prev,
      render: {
        ...prev.render,
        cfg_scale: preset.cfg_scale,
        stylization: preset.stylization,
      },
    }));
  };

  const handleQuickRender = async (count: number) => {
    if (!character || !onRender) return;
    setRendering(true);
    try {
      const params = resolveRenderParams(renderMode, renderQuality, renderVariance, visualProfile.render);
      let seed: number | null = null;
      if (seedMode === "same") {
        seed = parseSeed(renderSeed) ?? latestSeed;
        if (seed === null) {
          seed = Math.floor(Math.random() * 2 ** 32);
          setRenderSeed(String(seed));
        }
      }
      const payload: RenderPayload = {
        kind: renderMode === "final" ? "canonical" : "variant",
        label: `${renderMode}-${visualProfile.render.preset}`,
        count,
        width: params.width,
        height: params.height,
        steps: params.steps,
        cfg_scale: params.cfg_scale,
        seed,
        sampler: advancedGeneration.sampler || undefined,
        scheduler: advancedGeneration.scheduler || undefined,
        model_id: advancedGeneration.model_id || undefined,
        vae_id: advancedGeneration.vae_id || undefined,
        loras: advancedGeneration.loras && advancedGeneration.loras.length ? advancedGeneration.loras : undefined,
        pipeline_profile_id: advancedGeneration.pipeline_profile_id || undefined,
        pipeline_profile_version:
          advancedGeneration.pipeline_profile_version === null || advancedGeneration.pipeline_profile_version === undefined
            ? undefined
            : advancedGeneration.pipeline_profile_version,
      };
      await onRender(character.id, payload);
    } finally {
      setRendering(false);
    }
  };

  const handleAutofillMissing = async () => {
    if (missingFields.length === 0) return;
    setMissingFillLoading(true);
    setMissingFillError(null);
    try {
      const response = await generateFormFill({
        form_type: "character_visual_studio",
        fields: missingFields,
        current_values: aiCurrentValues,
        context: aiContext,
        detail_level: "standard",
        fill_only_empty: true,
      });
      if (response.values) {
        handleApplyAIFill(response.values);
      }
    } catch (err: any) {
      setMissingFillError(err?.message || "Не удалось заполнить недостающие поля.");
    } finally {
      setMissingFillLoading(false);
    }
  };

  const handleAcceptVariant = async (ref: ReferenceImage) => {
    if (!character) return;
    if (renderMode === "final") {
      await handleSetCanonical(ref);
      return;
    }
    await onPatch(character.id, {
      preview_image_url: ref.url,
      preview_thumbnail_url: ref.thumb_url || ref.url,
    });
  };

  const handleRegenerateSlot = async (kind: string, label?: string) => {
    if (!character || !onRegenerateReference) return;
    setSlotRendering((prev) => ({ ...prev, [kind]: true }));
    try {
      const slotRefs = slotReferences[kind] || [];
      const slotSize = getSlotSize(slotRefs, visualProfile.render);
      const params = resolveRenderParams("final", renderQuality, renderVariance, visualProfile.render);
      const overrides: GenerationOverrides = {
        width: slotSize.width,
        height: slotSize.height,
        steps: params.steps,
        cfg_scale: params.cfg_scale,
        sampler: advancedGeneration.sampler || undefined,
        scheduler: advancedGeneration.scheduler || undefined,
        model_id: advancedGeneration.model_id || undefined,
        vae_id: advancedGeneration.vae_id || undefined,
        loras: advancedGeneration.loras && advancedGeneration.loras.length ? advancedGeneration.loras : undefined,
        pipeline_profile_id: advancedGeneration.pipeline_profile_id || undefined,
        pipeline_profile_version:
          advancedGeneration.pipeline_profile_version === null || advancedGeneration.pipeline_profile_version === undefined
            ? undefined
            : advancedGeneration.pipeline_profile_version,
      };
      await onRegenerateReference(character.id, kind, overrides);
    } finally {
      setSlotRendering((prev) => ({ ...prev, [kind]: false }));
    }
  };

  const handleUploadReference = async (kind: string, file: File, setAsPreview = false) => {
    if (!character || !onUploadReference) return;
    setUploadingKind(kind);
    try {
      await onUploadReference(character.id, kind, file, { setAsPreview });
    } finally {
      setUploadingKind((current) => (current === kind ? null : current));
    }
  };

  const handleRender = async () => {
    if (!character || !onRender) return;
    setRendering(true);
    try {
      const payload: RenderPayload = {
        kind: renderKind,
        label: renderLabel.trim() || undefined,
        count: renderCount,
        prompt_override: renderPromptOverride.trim() || undefined,
        negative_prompt: renderNegativeOverride.trim() || undefined,
        width: visualProfile.render.width,
        height: visualProfile.render.height,
        steps: visualProfile.render.steps,
        cfg_scale: visualProfile.render.cfg_scale,
        seed: parseSeed(renderSeed),
        sampler: advancedGeneration.sampler || undefined,
        scheduler: advancedGeneration.scheduler || undefined,
        model_id: advancedGeneration.model_id || undefined,
        vae_id: advancedGeneration.vae_id || undefined,
        loras: advancedGeneration.loras && advancedGeneration.loras.length ? advancedGeneration.loras : undefined,
        pipeline_profile_id: advancedGeneration.pipeline_profile_id || undefined,
        pipeline_profile_version:
          advancedGeneration.pipeline_profile_version === null || advancedGeneration.pipeline_profile_version === undefined
            ? undefined
            : advancedGeneration.pipeline_profile_version,
      };
      await onRender(character.id, payload);
    } finally {
      setRendering(false);
    }
  };

  const handleCreateEmbedding = async () => {
    if (!character || !embeddingToken.trim()) return;
    setEmbeddingBusy(true);
    setTrainingNote(null);
    try {
      await createTextualInversion({
        token: embeddingToken.trim(),
        character_id: character.id,
        init_text: embeddingInitText.trim() || undefined,
        num_vectors: embeddingVectors,
        overwrite: false,
      });
      if (!embeddings.includes(embeddingToken.trim())) {
        setEmbeddings([...embeddings, embeddingToken.trim()]);
      }
      setTrainingNote("Текстовая инверсия создана. При необходимости обновите эмбеддинги в SD.");
    } catch (error: any) {
      setTrainingNote(error?.response?.data?.detail || "Не удалось создать текстовую инверсию.");
    } finally {
      setEmbeddingBusy(false);
    }
  };

  const handlePrepareLora = async () => {
    if (!character || !materialSetId || !embeddingToken.trim()) return;
    setTrainingBusy(true);
    setTrainingNote(null);
    try {
      const result = await prepareLoraTraining({
        material_set_id: materialSetId,
        token: embeddingToken.trim(),
        label: trainingLabel.trim() || undefined,
        caption: trainingCaption.trim() || undefined,
        character_id: character.id,
      });
      setTrainingNote(`Обучающий набор подготовлен: ${result.dataset_path}.`);
    } catch (error: any) {
      setTrainingNote(error?.response?.data?.detail || "Не удалось подготовить обучающий набор LoRA.");
    } finally {
      setTrainingBusy(false);
    }
  };

  const handleGenerateDescription = async () => {
    if (!name.trim()) return;
    setAiDescriptionLoading(true);
    setAiDescriptionError(null);
    try {
      const visualPrompt = advancedPromptEnabled && advancedPrompt.trim() ? advancedPrompt.trim() : computedPrompt;
      const contextParts = [
        visualProfile.identity.role_label ? `role label: ${visualProfile.identity.role_label}` : null,
        characterType ? `character type: ${characterType}` : null,
        visualPrompt ? `visual prompt: ${visualPrompt}` : null,
        voiceProfile ? `voice: ${voiceProfile}` : null,
        motivation ? `motivation: ${motivation}` : null,
        legalStatus ? `legal status: ${legalStatus}` : null,
        defaultPose ? `default pose: ${defaultPose}` : null,
      ].filter(Boolean);
      const response = await generateDescription({
        entity_type: "character",
        name: name.trim(),
        context: contextParts.join("\n"),
      });
      setDescription(response.description || "");
    } catch (err: any) {
      setAiDescriptionError(err?.message || "Не удалось сгенерировать описание.");
    } finally {
      setAiDescriptionLoading(false);
    }
  };

  const cleanupVoicePreviewAudio = () => {
    if (voicePreviewAudioRef.current) {
      voicePreviewAudioRef.current.pause();
      voicePreviewAudioRef.current = null;
    }
    if (voicePreviewUrlRef.current) {
      URL.revokeObjectURL(voicePreviewUrlRef.current);
      voicePreviewUrlRef.current = null;
    }
  };

  const stopVoicePreview = () => {
    cleanupVoicePreviewAudio();
    if (voicePreviewUtteranceRef.current && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      voicePreviewUtteranceRef.current = null;
    }
    setVoicePreviewPlaying(false);
  };

  const previewWithSpeechSynthesis = (text: string, profile: string) => {
    if (!("speechSynthesis" in window)) return false;
    const utterance = new SpeechSynthesisUtterance(text);
    const tuning = deriveVoiceTuning(profile);
    utterance.rate = tuning.rate;
    utterance.pitch = tuning.pitch;
    utterance.lang = detectVoiceLanguage(text);
    utterance.onend = () => {
      voicePreviewUtteranceRef.current = null;
      setVoicePreviewPlaying(false);
    };
    utterance.onerror = () => {
      voicePreviewUtteranceRef.current = null;
      setVoicePreviewPlaying(false);
    };
    voicePreviewUtteranceRef.current = utterance;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
    setVoicePreviewPlaying(true);
    return true;
  };

  const handleVoicePreview = async () => {
    if (voicePreviewLoading) return;
    if (voicePreviewPlaying) {
      stopVoicePreview();
      return;
    }
    setVoicePreviewError(null);
    const profile = voiceProfile.trim();
    if (!profile) {
      setVoicePreviewError("Добавьте голосовой профиль для предпросмотра.");
      return;
    }
    const line = (voicePreviewText.trim() || voicePreviewFallbackText).trim();
    if (!line) {
      setVoicePreviewError("Добавьте строку для предпросмотра.");
      return;
    }
    stopVoicePreview();
    setVoicePreviewLoading(true);
    try {
      const response = await generateVoicePreview({
        text: line,
        voice_profile: profile,
        language: detectVoiceLanguage(line),
      });
      const contentType = response.contentType || "audio/mpeg";
      const blob = new Blob([response.data], { type: contentType });
      const url = URL.createObjectURL(blob);
      voicePreviewUrlRef.current = url;
      const audio = new Audio(url);
      voicePreviewAudioRef.current = audio;
      audio.onended = () => {
        cleanupVoicePreviewAudio();
        setVoicePreviewPlaying(false);
      };
      audio.onerror = () => {
        cleanupVoicePreviewAudio();
        setVoicePreviewPlaying(false);
      };
      await audio.play();
      setVoicePreviewPlaying(true);
    } catch (err: any) {
      const usedFallback = previewWithSpeechSynthesis(line, profile);
      if (!usedFallback) {
        setVoicePreviewError(err?.message || "Не удалось сделать предпросмотр голоса.");
      }
    } finally {
      setVoicePreviewLoading(false);
    }
  };

  const toStringValue = (value: unknown) => (typeof value === "string" ? value : null);
  const toNumberValue = (value: unknown) =>
    typeof value === "number" && Number.isFinite(value) ? value : null;
  const toBooleanValue = (value: unknown) => (typeof value === "boolean" ? value : null);
  const toListValue = (value: unknown) => {
    if (Array.isArray(value)) {
      return value.map((item) => String(item).trim()).filter(Boolean);
    }
    if (typeof value === "string") {
      return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    }
    return null;
  };

  const handleApplyAIFill = (values: Record<string, unknown>) => {
    const nextVisual = {
      ...visualProfile,
      identity: { ...visualProfile.identity },
      face: { ...visualProfile.face },
      body: { ...visualProfile.body },
      hair: { ...visualProfile.hair },
      style: { ...visualProfile.style },
      render: { ...visualProfile.render },
    };

    const nameValue = toStringValue(values.name);
    if (nameValue !== null) setName(nameValue);
    const descValue = toStringValue(values.description);
    if (descValue !== null) setDescription(descValue);
    const typeValue = toStringValue(values.character_type);
    if (typeValue !== null) setCharacterType(typeValue);
    const roleLabel = toStringValue(values.role_label);
    if (roleLabel !== null) nextVisual.identity.role_label = roleLabel;

    const faceAge = toStringValue(values.face_age);
    if (faceAge !== null) nextVisual.face.age = faceAge;
    const faceGender = toStringValue(values.face_gender);
    if (faceGender !== null) nextVisual.face.gender = faceGender;
    const faceShape = toStringValue(values.face_shape);
    if (faceShape !== null) nextVisual.face.shape = faceShape;
    const faceEyes = toStringValue(values.face_eyes);
    if (faceEyes !== null) nextVisual.face.eyes = faceEyes;
    const faceNose = toStringValue(values.face_nose);
    if (faceNose !== null) nextVisual.face.nose = faceNose;
    const faceLips = toStringValue(values.face_lips);
    if (faceLips !== null) nextVisual.face.lips = faceLips;
    const faceSkin = toStringValue(values.face_skin);
    if (faceSkin !== null) nextVisual.face.skin = faceSkin;
    const faceExpression = toStringValue(values.face_expression);
    if (faceExpression !== null) nextVisual.face.expression = faceExpression;

    const bodyHeight = toStringValue(values.body_height);
    if (bodyHeight !== null) nextVisual.body.height = bodyHeight;
    const bodyBuild = toStringValue(values.body_build);
    if (bodyBuild !== null) nextVisual.body.build = bodyBuild;
    const bodyPosture = toStringValue(values.body_posture);
    if (bodyPosture !== null) nextVisual.body.posture = bodyPosture;
    const bodyProportions = toStringValue(values.body_proportions);
    if (bodyProportions !== null) nextVisual.body.proportions = bodyProportions;

    const hairStyle = toStringValue(values.hair_style);
    if (hairStyle !== null) nextVisual.hair.style = hairStyle;
    const hairColor = toStringValue(values.hair_color);
    if (hairColor !== null) nextVisual.hair.color = hairColor;
    const hairLength = toStringValue(values.hair_length);
    if (hairLength !== null) nextVisual.hair.length = hairLength;
    const hairFacial = toStringValue(values.hair_facial);
    if (hairFacial !== null) nextVisual.hair.facial_hair = hairFacial;

    const outfit = toStringValue(values.style_outfit);
    if (outfit !== null) nextVisual.style.outfit = outfit;
    const accessories = toStringValue(values.style_accessories);
    if (accessories !== null) nextVisual.style.accessories = accessories;
    const palette = toStringValue(values.style_palette);
    if (palette !== null) nextVisual.style.palette = palette;
    const materials = toStringValue(values.style_materials);
    if (materials !== null) nextVisual.style.materials = materials;

    const voiceValue = toStringValue(values.voice_profile);
    if (voiceValue !== null) setVoiceProfile(voiceValue);
    const motivationValue = toStringValue(values.motivation);
    if (motivationValue !== null) setMotivation(motivationValue);
    const legalValue = toStringValue(values.legal_status);
    if (legalValue !== null) setLegalStatus(legalValue);
    const poseValue = toStringValue(values.default_pose);
    if (poseValue !== null) setDefaultPose(poseValue);
    const negativeValue = toStringValue(values.negative_prompt);
    if (negativeValue !== null) setNegativePrompt(negativeValue);

    const competenciesValue = toListValue(values.competencies);
    if (competenciesValue !== null) setCompetencies(competenciesValue);
    const artifactValue = toListValue(values.artifact_refs);
    if (artifactValue !== null) setArtifactRefs(artifactValue);
    const styleTagsValue = toListValue(values.style_tags);
    if (styleTagsValue !== null) setStyleTags(styleTagsValue);

    const publicValue = toBooleanValue(values.is_public);
    if (publicValue !== null) setIsPublic(publicValue);

    const renderPreset = toStringValue(values.render_preset);
    if (renderPreset && RENDER_PRESETS[renderPreset]) {
      nextVisual.render.preset = renderPreset;
    }

    const renderFidelity = toNumberValue(values.render_fidelity);
    if (renderFidelity !== null) nextVisual.render.fidelity = clamp(renderFidelity, 0, 100);
    const renderStylization = toNumberValue(values.render_stylization);
    if (renderStylization !== null) nextVisual.render.stylization = clamp(renderStylization, 0, 100);
    const renderGeometry = toNumberValue(values.render_geometry);
    if (renderGeometry !== null) nextVisual.render.geometry = clamp(renderGeometry, 0, 100);
    const renderTexture = toNumberValue(values.render_texture);
    if (renderTexture !== null) nextVisual.render.texture = clamp(renderTexture, 0, 100);
    const renderLighting = toNumberValue(values.render_lighting);
    if (renderLighting !== null) nextVisual.render.lighting = clamp(renderLighting, 0, 100);
    const renderDetail = toNumberValue(values.render_detail);
    if (renderDetail !== null) nextVisual.render.detail = clamp(renderDetail, 0, 100);
    const renderWidth = toNumberValue(values.render_width);
    if (renderWidth !== null) nextVisual.render.width = clamp(renderWidth, 256, 2048);
    const renderHeight = toNumberValue(values.render_height);
    if (renderHeight !== null) nextVisual.render.height = clamp(renderHeight, 256, 2048);
    const renderSteps = toNumberValue(values.render_steps);
    if (renderSteps !== null) nextVisual.render.steps = clamp(renderSteps, QWEN_DEFAULT_STEPS, 80);
    const renderCfg = toNumberValue(values.render_cfg_scale);
    if (renderCfg !== null) nextVisual.render.cfg_scale = clamp(renderCfg, 1, 20);

    const advancedValue = toStringValue(values.advanced_prompt);
    if (advancedValue !== null) {
      setAdvancedPrompt(advancedValue);
      setAdvancedPromptEnabled(Boolean(advancedValue.trim()));
    }

    setVisualProfile(nextVisual);
  };
  const handleSetCanonical = async (ref: ReferenceImage) => {
    if (!character) return;
    const key = getRefKey(ref);
    setVisualProfile((prev) => ({
      ...prev,
      identity: {
        ...prev.identity,
        canonical_ref: key,
      },
    }));

    const updatedRefs = referenceImages.map((item) => {
      if (getRefKey(item) === key) {
        return { ...item, kind: "canonical" };
      }
      if (item.kind === "canonical") {
        return { ...item, kind: "variant" };
      }
      return item;
    });

    await onPatch(character.id, {
      reference_images: updatedRefs,
      preview_image_url: ref.url,
      preview_thumbnail_url: ref.thumb_url || ref.url,
    });
  };

  const pickPreviewRef = (refs: ReferenceImage[]) => {
    const preferred = ["canonical", "portrait", "profile", "full_front", "full_side", "full_back"];
    for (const kind of preferred) {
      const match = refs.find((item) => item.kind === kind);
      if (match) return match;
    }
    return refs[0] || null;
  };

  const isPreviewMatch = (ref: ReferenceImage) => {
    if (!character) return false;
    const previewUrl = character.preview_image_url || "";
    const previewThumb = character.preview_thumbnail_url || "";
    return [ref.url, ref.thumb_url || ""].some((value) => value && (value === previewUrl || value === previewThumb));
  };

  const handleRemoveReference = async (ref: ReferenceImage) => {
    if (!character) return;
    const key = getRefKey(ref);
    const updatedRefs = referenceImages.filter((item) => getRefKey(item) !== key);

    setVisualProfile((prev) => ({
      ...prev,
      identity: {
        ...prev.identity,
        face_ref: prev.identity.face_ref === key ? "" : prev.identity.face_ref,
        body_ref: prev.identity.body_ref === key ? "" : prev.identity.body_ref,
        canonical_ref: prev.identity.canonical_ref === key ? "" : prev.identity.canonical_ref,
      },
    }));

    const payload: Partial<CharacterPreset> = { reference_images: updatedRefs };
    if (isPreviewMatch(ref)) {
      const fallback = pickPreviewRef(updatedRefs);
      payload.preview_image_url = fallback?.url ?? null;
      payload.preview_thumbnail_url = fallback?.thumb_url ?? fallback?.url ?? null;
    }

    await onPatch(character.id, payload);
  };

  const handleClearPreview = async () => {
    if (!character) return;
    await onPatch(character.id, { preview_image_url: null, preview_thumbnail_url: null });
  };

  const handlePickIdentityRef = (ref: ReferenceImage, field: "face_ref" | "body_ref" | "canonical_ref") => {
    const key = getRefKey(ref);
    setVisualProfile((prev) => ({
      ...prev,
      identity: {
        ...prev.identity,
        [field]: key,
      },
    }));
  };

  const addLoraModel = () => {
    const nameValue = loraDraft.name.trim();
    if (!nameValue) return;
    if (loraModels.some((item) => item.name === nameValue)) {
      setLoraDraft({ name: "", weight: loraDraft.weight });
      return;
    }
    setLoraModels([...loraModels, { name: nameValue, weight: clamp(loraDraft.weight, 0, 2) }]);
    setLoraDraft({ name: "", weight: loraDraft.weight });
  };

  const removeLoraModel = (nameValue: string) => {
    setLoraModels(loraModels.filter((item) => item.name !== nameValue));
  };

  return (
    <div className={`cvs-shell ${isFullscreen ? "fullscreen" : ""}`}>
      <div className="cvs-header">
        <div>
          <div className="cvs-kicker">Визуальная студия персонажа</div>
          <h2>{character ? "Редактировать персонажа" : "Создать персонажа"}</h2>
          <p className="muted">Редактирование с упором на предпросмотр и подсказками.</p>
        </div>
        <div className="cvs-actions">
          <button className="ghost" type="button" onClick={() => setIsFullscreen((prev) => !prev)}>
            {isFullscreen ? "Выйти из полноэкранного" : "Полноэкранный"}
          </button>
          <button className="ghost" type="button" onClick={() => setAiFillOpen(true)}>AI заполнение</button>
          <button className="primary" onClick={handleSave} disabled={!canSave || saving}>
            {saving ? "Сохранение..." : character ? "Сохранить" : "Создать"}
          </button>
          {character && onDelete && (
            <button className="danger ghost" onClick={() => onDelete(character.id)}>Удалить ассет</button>
          )}
        </div>
      </div>

      <div className="cvs-overview">
        <div className="cvs-card">
          <div className="cvs-card-header">
            <strong>Предпросмотр</strong>
            {character?.anchor_token && (
              <div className="cvs-anchor">
                Тег: <code>{character.anchor_token}</code>
                <button
                  className="ghost"
                  type="button"
                  onClick={() => navigator.clipboard.writeText(character.anchor_token || "")}
                >Копировать</button>
              </div>
            )}
          </div>
          <div className="cvs-preview">
            {character?.preview_image_url ? (
              <img
                src={getAssetUrl(character.preview_image_url)}
                alt={character.name}
                onClick={() => openLightboxAsset(character.preview_image_url, "Предпросмотр", character.name)}
                style={{ cursor: onOpenLightbox ? "zoom-in" : "default" }}
              />
            ) : (
              <div className="cvs-preview-placeholder">Предпросмотра пока нет</div>
            )}
            {previewSource ? (
              <div className="cvs-chip-row" style={{ marginTop: 8 }}>
                <span className="cvs-chip">{formatAssetSourceLabel(previewSource)}</span>
              </div>
            ) : null}
            <div className="cvs-preview-actions">
              {onGenerateSketch && (
                <GenerationButton
                  onClick={() => character && handleSketchGeneration(character.id)}
                  isGenerating={sketchGeneration.isGenerating}
                  disabled={!character}
                  className="secondary"
                  stage={sketchGeneration.stage}
                >
                  {hasPreview ? "Перегенерировать скетч" : "Сгенерировать скетч"}
                </GenerationButton>
              )}
              {onUploadReference && (
                <UploadButton
                  className="secondary"
                  disabled={!character}
                  busy={uploadingKind === "portrait"}
                  label={hasPreview ? "Загрузить вместо скетча" : "Загрузить портрет"}
                  onSelect={(file) => handleUploadReference("portrait", file, true)}
                />
              )}
              <GenerationStatus
                isGenerating={sketchGeneration.isGenerating}
                progress={sketchGeneration.progress}
                stage={sketchGeneration.stage}
                error={sketchGeneration.error}
              />
              {onGenerateSheet && (
                <button
                  className="secondary"
                  type="button"
                  disabled={!character || sheeting || !hasPreview}
                  onClick={() =>
                    character &&
                    onGenerateSheet(character.id, {
                      overrides: {
                        // Don't override slot sizes for sheets
                        width: null,
                        height: null,
                        steps: visualProfile.render.steps,
                        cfg_scale: visualProfile.render.cfg_scale,
                        negative_prompt: renderNegativeOverride.trim() ? renderNegativeOverride.trim() : null,
                        sampler: advancedGeneration.sampler ?? null,
                        scheduler: advancedGeneration.scheduler ?? null,
                        model_id: advancedGeneration.model_id ?? null,
                        vae_id: advancedGeneration.vae_id ?? null,
                        loras: advancedGeneration.loras ?? [],
                        pipeline_profile_id: advancedGeneration.pipeline_profile_id ?? null,
                        pipeline_profile_version: advancedGeneration.pipeline_profile_version ?? null,
                        seed: parseSeed(renderSeed),
                      },
                      kinds: requiredKindsForGeneration,
                    })
                  }
                >
                  {sheeting
                    ? "Генерация..."
                    : referenceImages.length
                    ? "Перегенерировать обязательный набор"
                    : "Сгенерировать обязательный набор"}
                </button>
              )}
              {hasPreview && (
                <button className="danger ghost" type="button" onClick={handleClearPreview}>
                  Удалить предпросмотр
                </button>
              )}
            </div>
            {!hasPreview && <div className="muted">Сгенерируйте скетч, чтобы открыть обязательный набор.</div>}
          </div>
        </div>

        <div className="cvs-card">
          <div className="cvs-card-header">
            <strong>Идентичность</strong>
          </div>
          <div className="cvs-grid">
            <label className="cvs-field">
              <span>Название</span>
              <input className="cvs-input" value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="cvs-field">
              <span>Роль</span>
              <select
                className="cvs-select"
                value={characterType}
                onChange={(event) => setCharacterType(event.target.value)}
              >
                <option value="protagonist">Протагонист</option>
                <option value="antagonist">Антагонист</option>
                <option value="supporting">Второстепенный</option>
                <option value="background">Фон</option>
              </select>
            </label>
            <label className="cvs-field">
              <span>Ролевой ярлык</span>
              <input
                className="cvs-input"
                value={visualProfile.identity.role_label}
                onChange={(event) =>
                  setVisualProfile((prev) => ({
                    ...prev,
                    identity: { ...prev.identity, role_label: event.target.value },
                  }))
                }
                placeholder="судья, прокурор, свидетель"
              />
            </label>
            <label className="cvs-field">
              <span className="cvs-field-header">
                <span>Описание</span>
                <button
                  className="ghost"
                  type="button"
                  onClick={handleGenerateDescription}
                  disabled={!name.trim() || aiDescriptionLoading}
                >
                  {aiDescriptionLoading ? "Генерация..." : "Спросить AI"}
                </button>
              </span>
              <textarea
                className="cvs-textarea"
                rows={3}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
              {aiDescriptionError && <span className="cvs-error">{aiDescriptionError}</span>}
            </label>
          </div>
        </div>
      </div>

      {!simplifiedMode && (
      <section className="cvs-section cvs-preview-workflow">
        <div className="cvs-section-header">
          <h3>Рабочий процесс предпросмотра</h3>
          <span className="muted">Используйте предпросмотр для быстрых итераций, а финал — для выдачи.</span>
        </div>
        <div className="cvs-grid">
          <div className="cvs-field">
            <span>Режим</span>
            <div className="cvs-pill-group">
              <button
                className={`cvs-pill ${renderMode === "preview" ? "active" : ""}`}
                type="button"
                onClick={() => setRenderMode("preview")}
              >Предпросмотр</button>
              <button
                className={`cvs-pill ${renderMode === "final" ? "active" : ""}`}
                type="button"
                onClick={() => setRenderMode("final")}
              >
                Финал
              </button>
            </div>
          </div>
          <label className="cvs-field">
            <span>Цель</span>
            <select
              className="cvs-select"
              value={visualProfile.render.preset}
              onChange={(event) =>
                setVisualProfile((prev) => ({
                  ...prev,
                  render: { ...prev.render, preset: event.target.value },
                }))
              }
            >
              {Object.entries(RENDER_PRESETS).map(([value, preset]) => (
                <option key={value} value={value}>
                  {preset.label}
                </option>
              ))}
            </select>
            <span className="muted">{RENDER_PRESETS[visualProfile.render.preset]?.note}</span>
          </label>
          <div className="cvs-field">
            <span>Качество</span>
            <div className="cvs-pill-group">
              {QUALITY_LEVELS.map((level) => (
                <button
                  key={level}
                  className={`cvs-pill ${renderQuality === level ? "active" : ""}`}
                  type="button"
                  onClick={() => applyQuality(level)}
                >
                  {QUALITY_LABELS[level]}
                </button>
              ))}
            </div>
          </div>
          <div className="cvs-field">
            <span>Вариативность</span>
            <div className="cvs-pill-group">
              {VARIANCE_LEVELS.map((level) => (
                <button
                  key={level}
                  className={`cvs-pill ${renderVariance === level ? "active" : ""}`}
                  type="button"
                  onClick={() => applyVariance(level)}
                >
                  {VARIANCE_LABELS[level]}
                </button>
              ))}
            </div>
            <span className="muted">{VARIANCE_PRESETS[renderVariance].label}</span>
          </div>
          <label className="cvs-field">
            <span>Режим seed</span>
            <select
              className="cvs-select"
              value={seedMode}
              onChange={(event) => setSeedMode(event.target.value as "same" | "new")}
            >
              <option value="same">Один и тот же seed</option>
              <option value="new">Новый seed</option>
            </select>
            {seedMode === "same" && typeof activeSeed === "number" && (
              <span className="muted">Seed: {activeSeed}</span>
            )}
          </label>
        </div>
        <div className="cvs-actions">
          <button
            className="primary"
            disabled={!character || rendering}
            onClick={() => handleQuickRender(1)}
          >
            {rendering
              ? "Рендер..."
              : renderMode === "preview"
              ? hasPreview
                ? "Перегенерировать предпросмотр"
                : "Сгенерировать предпросмотр"
              : "Финальный рендер"}
          </button>
          <button
            className="secondary"
            disabled={!character || rendering}
            onClick={() => handleQuickRender(4)}
          >
            4 варианта
          </button>
        </div>
        {missingFields.length > 0 && (
          <div className="cvs-missing">
            <div className="cvs-missing-header">
              <div>
                <strong>Не хватает данных</strong>
                <div className="muted">
                  Требуется для {renderMode === "preview" ? "предпросмотра" : "финального рендера"}.
                </div>
              </div>
              <div className="cvs-missing-actions">
                <button className="secondary" type="button" onClick={() => setAiFillOpen(true)}>
                  Предложить варианты
                </button>
                <button
                  className="primary"
                  type="button"
                  onClick={handleAutofillMissing}
                  disabled={missingFillLoading}
                >
                  {missingFillLoading ? "Заполнение..." : "Автозаполнение"}
                </button>
              </div>
            </div>
            <ul className="cvs-missing-list">
              {missingFields.map((field) => (
                <li key={field.key}>{field.label || field.key}</li>
              ))}
            </ul>
            {missingFillError && <div className="cvs-error">{missingFillError}</div>}
          </div>
        )}
        <div className="cvs-variant-grid">
          {recentVariants.length === 0 ? (
            <div className="muted">Вариантов пока нет. Сгенерируйте для сравнения.</div>
          ) : (
            recentVariants.map((ref) => (
              <div key={getRefKey(ref)} className="cvs-variant-card">
                <img
                  src={getAssetUrl(ref.thumb_url || ref.url)}
                  alt={ref.label || ref.kind}
                  onClick={() => openLightboxAsset(ref.url, ref.label || ref.kind, character?.name)}
                />
                <div className="cvs-variant-meta">
                  <strong>{ref.label || ref.kind}</strong>
                  {typeof ref.meta?.seed === "number" && <span className="muted">Seed: {ref.meta.seed}</span>}
                </div>
                <div className="cvs-variant-actions">
                  <button className="secondary" type="button" onClick={() => handleAcceptVariant(ref)}>
                    Принять
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>
      )}

      <section className="cvs-section">
        <div className="cvs-section-header">
          <h3>{simplifiedMode ? "Базовые референсы" : "Обязательный набор"}</h3>
          <span className="muted">
            {simplifiedMode
              ? "Портрет, полный рост и ракурс 45° для стабильной генерации."
              : "Портрет + базовые ракурсы полного роста для всего редактора."}
          </span>
        </div>
        <div className="cvs-reference-status">
          <div className="cvs-reference-status-header">
            <div>
              <strong>Пакет референсов</strong>
              <div className="muted">
                {simplifiedMode
                  ? "Достаточно базового набора. Остальные виды необязательны."
                  : "Сначала обязательный набор, затем при необходимости полный."}
              </div>
            </div>
            <div className="cvs-chip-row">
              {referenceStatus.isComplete ? (
                <span className="cvs-chip">Готово</span>
              ) : (
                <>
                  {referenceStatus.missingViews.length > 0 && <span className="cvs-chip">Нет ракурсов</span>}
                  {referenceStatus.missingPoses.length > 0 && <span className="cvs-chip">Нет поз</span>}
                </>
              )}
            </div>
          </div>
          {!referenceStatus.isComplete && (
            <div className="muted">
              {missingViewLabels.length > 0 && `Ракурсы: ${missingViewLabels.join(", ")}.`}{" "}
              {missingPoseLabels.length > 0 && `Позы: ${missingPoseLabels.join(", ")}.`}
            </div>
          )}
          {referenceStatus.missingOptional.length > 0 && (
            <div className="muted">
              Дополнительно: {missingOptionalLabels.join(", ")}.
            </div>
          )}
          {onGenerateSheet && (
            <div className="cvs-reference-status-actions">
              <button
                className="secondary"
                disabled={!character || sheeting || !hasPreview}
                onClick={() =>
                  character &&
                  onGenerateSheet(character.id, {
                    overrides: {
                      width: null,
                      height: null,
                      steps: visualProfile.render.steps,
                      cfg_scale: visualProfile.render.cfg_scale,
                      negative_prompt: renderNegativeOverride.trim() ? renderNegativeOverride.trim() : null,
                      sampler: advancedGeneration.sampler ?? null,
                      scheduler: advancedGeneration.scheduler ?? null,
                      model_id: advancedGeneration.model_id ?? null,
                      vae_id: advancedGeneration.vae_id ?? null,
                      loras: advancedGeneration.loras ?? [],
                      pipeline_profile_id: advancedGeneration.pipeline_profile_id ?? null,
                      pipeline_profile_version: advancedGeneration.pipeline_profile_version ?? null,
                      seed: parseSeed(renderSeed),
                    },
                    kinds: requiredKindsForGeneration,
                  })
                }
              >
                {sheeting
                  ? `Генерация... (${sheetProgress.ready}/${sheetProgress.total})`
                  : "Сгенерировать обязательный набор"}
              </button>
              {!simplifiedMode && (
                <button
                  className="ghost"
                  disabled={!character || sheeting || !hasPreview}
                  onClick={() =>
                    character &&
                    onGenerateSheet(character.id, {
                      overrides: {
                        width: null,
                        height: null,
                        steps: visualProfile.render.steps,
                        cfg_scale: visualProfile.render.cfg_scale,
                        negative_prompt: renderNegativeOverride.trim() ? renderNegativeOverride.trim() : null,
                        sampler: advancedGeneration.sampler ?? null,
                        scheduler: advancedGeneration.scheduler ?? null,
                        model_id: advancedGeneration.model_id ?? null,
                        vae_id: advancedGeneration.vae_id ?? null,
                        loras: advancedGeneration.loras ?? [],
                        pipeline_profile_id: advancedGeneration.pipeline_profile_id ?? null,
                        pipeline_profile_version: advancedGeneration.pipeline_profile_version ?? null,
                        seed: parseSeed(renderSeed),
                      },
                      kinds: CHARACTER_REFERENCE_SLOTS.map((slot) => slot.kind),
                    })
                  }
                >
                  {sheeting
                    ? `Генерация... (${fullSetProgress.ready}/${fullSetProgress.total})`
                    : "Сгенерировать полный набор"}
                </button>
              )}
              {!hasPreview && <span className="muted">Сначала сгенерируйте скетч.</span>}
            </div>
          )}
        </div>
        <div className="cvs-reference-grid">
          {referenceStatus.requiredSlots.map((slot) => {
            const slotRefs = slotReferences[slot.kind] || [];
            const activeRef = slotRefs[slotRefs.length - 1];
            const busy = Boolean(slotRendering[slot.kind]);
            return (
              <div key={slot.kind} className="cvs-reference-card">
                <div className="cvs-reference-card-header">
                  <div className="cvs-reference-card-title">
                    <span>{slot.label}</span>
                    {slot.note && <span className="muted">{slot.note}</span>}
                  </div>
                  <div className="cvs-reference-card-actions">
                    <button
                      className="ghost"
                      type="button"
                      disabled={!character || busy || !onRegenerateReference}
                      onClick={() => handleRegenerateSlot(slot.kind, slot.label)}
                    >
                      {busy ? "Генерация..." : "Сгенерировать"}
                    </button>
                    {onUploadReference && (
                      <UploadButton
                        className="ghost"
                        disabled={!character}
                        busy={uploadingKind === slot.kind}
                        label="Загрузить"
                        onSelect={(file) => handleUploadReference(slot.kind, file, slot.kind === "portrait")}
                      />
                    )}
                    {activeRef && (
                      <button
                        className="danger ghost"
                        type="button"
                        disabled={!character}
                        onClick={() => handleRemoveReference(activeRef)}
                      >Удалить</button>
                    )}
                  </div>
                </div>
                {activeRef ? (
                  <>
                    <img
                      src={getAssetUrl(activeRef.thumb_url || activeRef.url)}
                      alt={slot.label}
                      onClick={() => openLightboxAsset(activeRef.url, slot.label, character?.name)}
                    />
                    <div className="cvs-chip-row" style={{ marginTop: 8 }}>
                      <span className="cvs-chip">{formatAssetSourceLabel(getReferenceAssetSource(activeRef))}</span>
                    </div>
                  </>
                ) : (
                  <div className="cvs-reference-placeholder">Нет изображения</div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {!simplifiedMode && referenceStatus.optionalSlots.length > 0 && (
        <section className="cvs-section">
          <div className="cvs-section-header">
            <h3>Дополнительные виды</h3>
            <button
              className="ghost"
              type="button"
              onClick={() => setShowOptionalRefs((prev) => !prev)}
            >
              {showOptionalRefs ? "Скрыть" : "Показать"}
            </button>
          </div>
          {showOptionalRefs && (
            <div className="cvs-reference-grid">
              {referenceStatus.optionalSlots.map((slot) => {
                const slotRefs = slotReferences[slot.kind] || [];
                const activeRef = slotRefs[slotRefs.length - 1];
                const busy = Boolean(slotRendering[slot.kind]);
                return (
                  <div key={slot.kind} className="cvs-reference-card">
                    <div className="cvs-reference-card-header">
                      <div className="cvs-reference-card-title">
                        <span>{slot.label}</span>
                        {slot.note && <span className="muted">{slot.note}</span>}
                      </div>
                      <div className="cvs-reference-card-actions">
                        <button
                          className="ghost"
                          type="button"
                          disabled={!character || busy || !onRegenerateReference}
                          onClick={() => handleRegenerateSlot(slot.kind, slot.label)}
                        >
                          {busy ? "Генерация..." : "Сгенерировать"}
                        </button>
                        {onUploadReference && (
                          <UploadButton
                            className="ghost"
                            disabled={!character}
                            busy={uploadingKind === slot.kind}
                            label="Загрузить"
                            onSelect={(file) => handleUploadReference(slot.kind, file)}
                          />
                        )}
                        {activeRef && (
                          <button
                            className="danger ghost"
                            type="button"
                            disabled={!character}
                            onClick={() => handleRemoveReference(activeRef)}
                          >Удалить</button>
                        )}
                      </div>
                    </div>
                    {activeRef ? (
                      <>
                        <img
                          src={getAssetUrl(activeRef.thumb_url || activeRef.url)}
                          alt={slot.label}
                          onClick={() => openLightboxAsset(activeRef.url, slot.label, character?.name)}
                        />
                        <div className="cvs-chip-row" style={{ marginTop: 8 }}>
                          <span className="cvs-chip">{formatAssetSourceLabel(getReferenceAssetSource(activeRef))}</span>
                        </div>
                      </>
                    ) : (
                      <div className="cvs-reference-placeholder">Нет изображения</div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {!simplifiedMode && (
      <>
      <section className="cvs-section cvs-advisor">
        <div className="cvs-section-header">
          <h3>Recommendations</h3>
          <span className="muted">Локальные пресеты, когда внешние рекомендации недоступны.</span>
        </div>
        <div className="cvs-advisor-tabs">
          <button
            className={`cvs-pill ${advisorTab === "recommend" ? "active" : ""}`}
            type="button"
            onClick={() => setAdvisorTab("recommend")}
          >
            Рекомендовать план
          </button>
          <button
            className={`cvs-pill ${advisorTab === "explain" ? "active" : ""}`}
            type="button"
            onClick={() => setAdvisorTab("explain")}
          >
            Пояснить
          </button>
        </div>
        {advisorTab === "recommend" ? (
          <div className="cvs-advisor-grid">
            {recommendationPlans.map((plan) => (
              <div key={plan.id} className="cvs-advisor-card">
                <strong>{plan.label}</strong>
                <span className="muted">{plan.note}</span>
                <div className="cvs-advisor-meta">
                  <span>Качество: {QUALITY_LABELS[plan.quality]}</span>
                  <span>Вариативность: {VARIANCE_LABELS[plan.variance]}</span>
                  <span>
                    {plan.width}×{plan.height} · {plan.steps} шагов · CFG {plan.cfg_scale}
                  </span>
                </div>
                <button
                  className="secondary"
                  type="button"
                  onClick={() => {
                    applyQuality(plan.quality);
                    applyVariance(plan.variance);
                  }}
                >
                  Применить план
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="cvs-advisor-explain muted">{explainText}</div>
        )}
      </section>

      <details className="cvs-advanced">
        <summary>Расширенные настройки</summary>
        <div className="cvs-advanced-body">
          <section className="cvs-section">
            <div className="cvs-section-header">
              <h3>Пресеты генерации</h3>
              <span className="muted">LoRA / сэмплер / переопределения модели + сохранённые пресеты.</span>
            </div>

            <AdvancedGenerationSettings
              title="Переопределения рендера"
              value={advancedSettingsValue}
              onChange={handleAdvancedSettingsChange}
              showResolution={false}
              showCfgSteps={false}
              showNegative={false}
              showSeed={false}
              showPipelineProfile={true}
            />
          </section>

      <section className="cvs-section">
        <div className="cvs-section-header">
          <h3>Блокировка идентичности</h3>
          <span className="muted">Фиксация референсов лица/тела для консистентного рендера.</span>
        </div>
        <div className="cvs-grid">
          <label className="cvs-field">
            <span>Режим фиксации</span>
            <select
              className="cvs-select"
              value={visualProfile.identity.lock_mode}
              onChange={(event) =>
                setVisualProfile((prev) => ({
                  ...prev,
                  identity: { ...prev.identity, lock_mode: event.target.value },
                }))
              }
            >
              <option value="none">Нет</option>
              <option value="face">Лицо</option>
              <option value="body">Тело</option>
              <option value="face+body">Лицо + Тело</option>
              <option value="adapter">Адаптер</option>
              <option value="lora">LoRA</option>
            </select>
          </label>
          <label className="cvs-field">
            <span>Адаптер / модель</span>
            <input
              className="cvs-input"
              value={visualProfile.identity.adapter}
              onChange={(event) =>
                setVisualProfile((prev) => ({
                  ...prev,
                  identity: { ...prev.identity, adapter: event.target.value },
                }))
              }
              placeholder="ip-adapter-face, identity-lora"
            />
          </label>
          <label className="cvs-field cvs-slider">
            <span>Сила фиксации</span>
            <div className="cvs-slider-row">
              <input
                className="cvs-range"
                type="range"
                min={0}
                max={100}
                value={Math.round(visualProfile.identity.lock_strength * 100)}
                onChange={(event) =>
                  setVisualProfile((prev) => ({
                    ...prev,
                    identity: { ...prev.identity, lock_strength: Number(event.target.value) / 100 },
                  }))
                }
              />
              <span className="cvs-slider-value">{Math.round(visualProfile.identity.lock_strength * 100)}</span>
            </div>
          </label>
          <label className="cvs-field cvs-checkbox">
            <input
              type="checkbox"
              checked={visualProfile.identity.extract_face}
              onChange={(event) =>
                setVisualProfile((prev) => ({
                  ...prev,
                  identity: { ...prev.identity, extract_face: event.target.checked },
                }))
              }
            />
            <span>Извлекать лицо из референса</span>
          </label>
          <label className="cvs-field cvs-checkbox">
            <input
              type="checkbox"
              checked={visualProfile.identity.attach_face}
              onChange={(event) =>
                setVisualProfile((prev) => ({
                  ...prev,
                  identity: { ...prev.identity, attach_face: event.target.checked },
                }))
              }
            />
            <span>Прикреплять лицо к референсу тела</span>
          </label>
        </div>
        <div className="cvs-reference-strip">
          <div className="cvs-reference-item">
            <span className="muted">Референс лица</span>
            {faceRef ? (
              <img src={getAssetUrl(faceRef.thumb_url || faceRef.url)} alt="Референс лица" />
            ) : (
              <div className="cvs-reference-placeholder">Нет</div>
            )}
          </div>
          <div className="cvs-reference-item">
            <span className="muted">Референс тела</span>
            {bodyRef ? (
              <img src={getAssetUrl(bodyRef.thumb_url || bodyRef.url)} alt="Референс тела" />
            ) : (
              <div className="cvs-reference-placeholder">Нет</div>
            )}
          </div>
          <div className="cvs-reference-item">
            <span className="muted">Канонический</span>
            {canonicalRef ? (
              <img src={getAssetUrl(canonicalRef.thumb_url || canonicalRef.url)} alt="Канонический референс" />
            ) : (
              <div className="cvs-reference-placeholder">Нет</div>
            )}
          </div>
        </div>
      </section>

      <section className="cvs-section">
        <div className="cvs-section-header">
          <h3>Геометрия и точность</h3>
          <span className="muted">Настройте баланс рендера для консистентности.</span>
        </div>
        <div className="cvs-grid cvs-slider-grid">
          <SliderField
            label="Точность"
            value={visualProfile.render.fidelity}
            onChange={(value) =>
              setVisualProfile((prev) => ({ ...prev, render: { ...prev.render, fidelity: value } }))
            }
          />
          <SliderField
            label="Стилизация"
            value={visualProfile.render.stylization}
            onChange={(value) =>
              setVisualProfile((prev) => ({ ...prev, render: { ...prev.render, stylization: value } }))
            }
          />
          <SliderField
            label="Геометрия"
            value={visualProfile.render.geometry}
            onChange={(value) =>
              setVisualProfile((prev) => ({ ...prev, render: { ...prev.render, geometry: value } }))
            }
          />
          <SliderField
            label="Текстуры"
            value={visualProfile.render.texture}
            onChange={(value) =>
              setVisualProfile((prev) => ({ ...prev, render: { ...prev.render, texture: value } }))
            }
          />
          <SliderField
            label="Свет"
            value={visualProfile.render.lighting}
            onChange={(value) =>
              setVisualProfile((prev) => ({ ...prev, render: { ...prev.render, lighting: value } }))
            }
          />
          <SliderField
            label="Детализация"
            value={visualProfile.render.detail}
            onChange={(value) =>
              setVisualProfile((prev) => ({ ...prev, render: { ...prev.render, detail: value } }))
            }
          />
        </div>
      </section>

      <section className="cvs-section">
        <div className="cvs-section-header">
          <h3>Профиль лица и тела</h3>
          <span className="muted">Структурированное описание для сборки промпта.</span>
        </div>
        <div className="cvs-grid">
          <label className="cvs-field">
            <span>Возраст / этап жизни</span>
            <input
              className="cvs-input"
              value={visualProfile.face.age}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, face: { ...prev.face, age: event.target.value } }))
              }
              placeholder="около 30–35"
            />
          </label>
          <label className="cvs-field">
            <span>Пол / гендер</span>
            <input
              className="cvs-input"
              value={visualProfile.face.gender}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, face: { ...prev.face, gender: event.target.value } }))
              }
              placeholder="женственный, мужественный"
            />
          </label>
          <label className="cvs-field">
            <span>Форма лица</span>
            <input
              className="cvs-input"
              value={visualProfile.face.shape}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, face: { ...prev.face, shape: event.target.value } }))
              }
              placeholder="овальное лицо, чёткая линия челюсти"
            />
          </label>
          <label className="cvs-field">
            <span>Глаза</span>
            <input
              className="cvs-input"
              value={visualProfile.face.eyes}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, face: { ...prev.face, eyes: event.target.value } }))
              }
              placeholder="зелёные глаза, тяжёлые веки"
            />
          </label>
          <label className="cvs-field">
            <span>Нос</span>
            <input
              className="cvs-input"
              value={visualProfile.face.nose}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, face: { ...prev.face, nose: event.target.value } }))
              }
              placeholder="прямой нос"
            />
          </label>
          <label className="cvs-field">
            <span>Губы</span>
            <input
              className="cvs-input"
              value={visualProfile.face.lips}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, face: { ...prev.face, lips: event.target.value } }))
              }
              placeholder="тонкие губы"
            />
          </label>
          <label className="cvs-field">
            <span>Кожа</span>
            <input
              className="cvs-input"
              value={visualProfile.face.skin}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, face: { ...prev.face, skin: event.target.value } }))
              }
              placeholder="тёплый тон кожи, веснушки"
            />
          </label>
          <label className="cvs-field">
            <span>Базовое выражение</span>
            <input
              className="cvs-input"
              value={visualProfile.face.expression}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, face: { ...prev.face, expression: event.target.value } }))
              }
              placeholder="спокойный, собранный"
            />
          </label>
          <label className="cvs-field">
            <span>Рост / масштаб</span>
            <input
              className="cvs-input"
              value={visualProfile.body.height}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, body: { ...prev.body, height: event.target.value } }))
              }
              placeholder="высокий, средний рост"
            />
          </label>
          <label className="cvs-field">
            <span>Телосложение</span>
            <input
              className="cvs-input"
              value={visualProfile.body.build}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, body: { ...prev.body, build: event.target.value } }))
              }
              placeholder="атлетичное, худощавое"
            />
          </label>
          <label className="cvs-field">
            <span>Осанка</span>
            <input
              className="cvs-input"
              value={visualProfile.body.posture}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, body: { ...prev.body, posture: event.target.value } }))
              }
              placeholder="прямая осанка"
            />
          </label>
          <label className="cvs-field">
            <span>Пропорции</span>
            <input
              className="cvs-input"
              value={visualProfile.body.proportions}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, body: { ...prev.body, proportions: event.target.value } }))
              }
              placeholder="длинные ноги, широкие плечи"
            />
          </label>
        </div>
      </section>

      <section className="cvs-section">
        <div className="cvs-section-header">
          <h3>Волосы и гардероб</h3>
          <span className="muted">Одежда, палитра и материалы.</span>
        </div>
        <div className="cvs-grid">
          <label className="cvs-field">
            <span>Стиль волос</span>
            <input
              className="cvs-input"
              value={visualProfile.hair.style}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, hair: { ...prev.hair, style: event.target.value } }))
              }
              placeholder="короткое каре"
            />
          </label>
          <label className="cvs-field">
            <span>Цвет волос</span>
            <input
              className="cvs-input"
              value={visualProfile.hair.color}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, hair: { ...prev.hair, color: event.target.value } }))
              }
              placeholder="тёмно-каштановый"
            />
          </label>
          <label className="cvs-field">
            <span>Длина волос</span>
            <input
              className="cvs-input"
              value={visualProfile.hair.length}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, hair: { ...prev.hair, length: event.target.value } }))
              }
              placeholder="до плеч"
            />
          </label>
          <label className="cvs-field">
            <span>Лицевая растительность</span>
            <input
              className="cvs-input"
              value={visualProfile.hair.facial_hair}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, hair: { ...prev.hair, facial_hair: event.target.value } }))
              }
              placeholder="аккуратно подстриженная борода"
            />
          </label>
          <label className="cvs-field">
            <span>Одежда</span>
            <input
              className="cvs-input"
              value={visualProfile.style.outfit}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, style: { ...prev.style, outfit: event.target.value } }))
              }
              placeholder="судебный костюм, мантия"
            />
          </label>
          <label className="cvs-field">
            <span>Аксессуары</span>
            <input
              className="cvs-input"
              value={visualProfile.style.accessories}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, style: { ...prev.style, accessories: event.target.value } }))
              }
              placeholder="очки, наручные часы"
            />
          </label>
          <label className="cvs-field">
            <span>Палитра</span>
            <input
              className="cvs-input"
              value={visualProfile.style.palette}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, style: { ...prev.style, palette: event.target.value } }))
              }
              placeholder="тёмно-синий костюм, белая рубашка"
            />
          </label>
          <label className="cvs-field">
            <span>Материалы</span>
            <input
              className="cvs-input"
              value={visualProfile.style.materials}
              onChange={(event) =>
                setVisualProfile((prev) => ({ ...prev, style: { ...prev.style, materials: event.target.value } }))
              }
              placeholder="шерсть, кожа"
            />
          </label>
        </div>
      </section>

      <section className="cvs-section">
        <div className="cvs-section-header">
          <h3>Нарратив и поведение</h3>
          <span className="muted">Поля только для истории, используются авторами и диалоговыми инструментами.</span>
        </div>
        <div className="cvs-grid">
          <label className="cvs-field">
            <span className="cvs-field-header">
              <span>Голосовой профиль</span>
              <button
                className="ghost"
                type="button"
                onClick={handleVoicePreview}
                disabled={voicePreviewLoading || (!voiceProfile.trim() && !voicePreviewPlaying)}
              >
                {voicePreviewLoading ? "Предпросмотр..." : voicePreviewPlaying ? "Остановить" : "Предпросмотр"}
              </button>
            </span>
            <input
              className="cvs-input"
              value={voiceProfile}
              onChange={(event) => setVoiceProfile(event.target.value)}
              placeholder={VOICE_PROFILE_PLACEHOLDER}
            />
          </label>
          <label className="cvs-field">
            <span>Строка предпросмотра</span>
            <input
              className="cvs-input"
              value={voicePreviewText}
              onChange={(event) => setVoicePreviewText(event.target.value)}
              placeholder={voicePreviewFallbackText}
            />
            {voicePreviewError && <span className="cvs-error">{voicePreviewError}</span>}
          </label>
          <label className="cvs-field">
            <span>Мотивация</span>
            <input
              className="cvs-input"
              value={motivation}
              onChange={(event) => setMotivation(event.target.value)}
              placeholder="защищать институт"
            />
          </label>
          <label className="cvs-field">
            <span>Правовой статус</span>
            <input
              className="cvs-input"
              value={legalStatus}
              onChange={(event) => setLegalStatus(event.target.value)}
              placeholder="судья, свидетель"
            />
          </label>
          <label className="cvs-field">
            <span>Поза по умолчанию</span>
            <input
              className="cvs-input"
              value={defaultPose}
              onChange={(event) => setDefaultPose(event.target.value)}
              placeholder="стоит, руки сложены"
            />
          </label>
          {allowPublic ? (
            <label className="cvs-field cvs-checkbox">
              <input type="checkbox" checked={isPublic} onChange={(event) => setIsPublic(event.target.checked)} />
              <span>Публичный пресет</span>
            </label>
          ) : null}
        </div>
        <div className="cvs-grid">
          <ListEditor
            label="Компетенции"
            items={competencies}
            onChange={setCompetencies}
            placeholder="расследование, эмпатия"
          />
          <ListEditor
            label="Референсы артефактов"
            items={artifactRefs}
            onChange={setArtifactRefs}
            placeholder="id-артефакта"
          />
        </div>
      </section>

      <section className="cvs-section">
        <div className="cvs-section-header">
          <h3>Конвейер рендера</h3>
          <span className="muted">Значения по умолчанию для референсов и предпросмотров.</span>
        </div>
        <div className="cvs-grid">
          <label className="cvs-field">
            <span>Пресет</span>
            <select
              className="cvs-select"
              value={visualProfile.render.preset}
              onChange={(event) =>
                setVisualProfile((prev) => ({
                  ...prev,
                  render: { ...prev.render, preset: event.target.value },
                }))
              }
            >
              {Object.entries(RENDER_PRESETS).map(([value, preset]) => (
                <option key={value} value={value}>
                  {preset.label}
                </option>
              ))}
            </select>
            <span className="muted">{RENDER_PRESETS[visualProfile.render.preset]?.note}</span>
          </label>
          <label className="cvs-field">
            <span>Ширина</span>
            <input
              className="cvs-input"
              type="number"
              min={256}
              max={2048}
              value={visualProfile.render.width}
              onChange={(event) =>
                setVisualProfile((prev) => ({
                  ...prev,
                  render: { ...prev.render, width: clamp(Number(event.target.value || 0), 256, 2048) },
                }))
              }
            />
          </label>
          <label className="cvs-field">
            <span>Высота</span>
            <input
              className="cvs-input"
              type="number"
              min={256}
              max={2048}
              value={visualProfile.render.height}
              onChange={(event) =>
                setVisualProfile((prev) => ({
                  ...prev,
                  render: { ...prev.render, height: clamp(Number(event.target.value || 0), 256, 2048) },
                }))
              }
            />
          </label>
          <label className="cvs-field">
            <span>Шаги</span>
            <input
              className="cvs-input"
              type="number"
              min={QWEN_DEFAULT_STEPS}
              max={80}
              value={visualProfile.render.steps}
              onChange={(event) =>
                setVisualProfile((prev) => ({
                  ...prev,
                  render: { ...prev.render, steps: clamp(Number(event.target.value || 0), QWEN_DEFAULT_STEPS, 80) },
                }))
              }
            />
          </label>
          <label className="cvs-field">
            <span>CFG scale</span>
            <input
              className="cvs-input"
              type="number"
              min={1}
              max={20}
              step={0.5}
              value={visualProfile.render.cfg_scale}
              onChange={(event) =>
                setVisualProfile((prev) => ({
                  ...prev,
                  render: { ...prev.render, cfg_scale: clamp(Number(event.target.value || 0), 1, 20) },
                }))
              }
            />
          </label>
          <label className="cvs-field">
            <span>Негативный промпт</span>
            <textarea
              className="cvs-textarea"
              rows={2}
              value={negativePrompt}
              onChange={(event) => setNegativePrompt(event.target.value)}
              placeholder="без лишних людей, без размытия"
            />
          </label>
        </div>
        <div className="cvs-grid">
          <ListEditor
            label="Теги стиля"
            items={styleTags}
            onChange={setStyleTags}
            placeholder="реалистично, кинематографично"
          />
          <ListEditor label="Эмбеддинги" items={embeddings} onChange={setEmbeddings} placeholder="токен embedding" />
        </div>
        <div className="cvs-grid">
          <div className="cvs-field">
            <span>Модели LoRA</span>
            <div className="cvs-list-input">
              <input
                className="cvs-input"
                value={loraDraft.name}
                onChange={(event) => setLoraDraft({ ...loraDraft, name: event.target.value })}
                placeholder="lora_name"
              />
              <input
                className="cvs-input cvs-input-small"
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={loraDraft.weight}
                onChange={(event) => setLoraDraft({ ...loraDraft, weight: Number(event.target.value) })}
              />
              <button className="secondary" type="button" onClick={addLoraModel}>Добавить</button>
            </div>
            {loraModels.length > 0 && (
              <div className="cvs-chip-row">
                {loraModels.map((model) => (
                  <span key={model.name} className="cvs-chip">
                    {model.name} ({model.weight})
                    <button type="button" onClick={() => removeLoraModel(model.name)}>
                      x
                    </button>
                  </span>
                ))}
            </div>
          )}
        </div>
      </div>
        <div className="cvs-grid">
          <label className="cvs-field cvs-checkbox">
            <input
              type="checkbox"
              checked={advancedPromptEnabled}
              onChange={(event) => setAdvancedPromptEnabled(event.target.checked)}
            />
            <span>Использовать расширенный промпт</span>
          </label>
          {advancedPromptEnabled && (
            <label className="cvs-field">
              <span>Расширенный промпт</span>
              <textarea
                className="cvs-textarea"
                rows={3}
                value={advancedPrompt}
                onChange={(event) => setAdvancedPrompt(event.target.value)}
              />
            </label>
          )}
          <label className="cvs-field">
            <span>Предпросмотр вычисленного промпта</span>
            <textarea className="cvs-textarea" rows={3} value={computedPrompt} readOnly />
          </label>
        </div>
      </section>

      <section className="cvs-section">
        <div className="cvs-section-header">
          <h3>Обучение и модели идентичности</h3>
          <span className="muted">Подготовка датасетов LoRA и токенов текстовой инверсии.</span>
        </div>
        <div className="cvs-grid">
          <label className="cvs-field">
            <span>Токен embedding</span>
            <input
              className="cvs-input"
              value={embeddingToken}
              onChange={(event) => setEmbeddingToken(event.target.value)}
              placeholder="wlchar_token"
            />
          </label>
          <label className="cvs-field">
            <span>Начальный текст (необязательно)</span>
            <input
              className="cvs-input"
              value={embeddingInitText}
              onChange={(event) => setEmbeddingInitText(event.target.value)}
              placeholder="краткое описание"
            />
          </label>
          <label className="cvs-field">
            <span>Векторов на токен</span>
            <input
              className="cvs-input"
              type="number"
              min={1}
              max={64}
              value={embeddingVectors}
              onChange={(event) => setEmbeddingVectors(clamp(Number(event.target.value || 1), 1, 64))}
            />
          </label>
          <div className="cvs-field">
            <span>Текстовая инверсия</span>
            <button
              className="secondary"
              type="button"
              disabled={!character || !embeddingToken.trim() || embeddingBusy}
              onClick={handleCreateEmbedding}
            >
              {embeddingBusy ? "Создание..." : "Создать текстовую инверсию"}
            </button>
          </div>
        </div>
        <div className="cvs-grid">
          <label className="cvs-field">
            <span>Набор материалов</span>
            <select
              className="cvs-select"
              value={materialSetId}
              onChange={(event) => setMaterialSetId(event.target.value)}
              disabled={!projectId}
            >
              <option value="">Выберите набор материалов</option>
              {materialSets.map((set) => (
                <option key={set.id} value={set.id}>
                  {set.label}
                </option>
              ))}
            </select>
            {!projectId && <span className="muted">Импортируйте персонажа в проект, чтобы использовать наборы материалов.</span>}
          </label>
          <label className="cvs-field">
            <span>Метка LoRA</span>
            <input
              className="cvs-input"
              value={trainingLabel}
              onChange={(event) => setTrainingLabel(event.target.value)}
              placeholder="Персонаж v1"
            />
          </label>
          <label className="cvs-field">
            <span>Суффикс подписи</span>
            <input
              className="cvs-input"
              value={trainingCaption}
              onChange={(event) => setTrainingCaption(event.target.value)}
              placeholder="зал суда, официальная мантия"
            />
          </label>
          <div className="cvs-field">
            <span>Датасет LoRA</span>
            <button
              className="secondary"
              type="button"
              disabled={!character || !materialSetId || !embeddingToken.trim() || trainingBusy}
              onClick={handlePrepareLora}
            >
              {trainingBusy ? "Подготовка..." : "Подготовить обучающий набор LoRA"}
            </button>
          </div>
        </div>
        {trainingNote && <div className="muted">{trainingNote}</div>}
      </section>

      <section className="cvs-section">
        <div className="cvs-section-header">
          <h3>Представления</h3>
          <span className="muted">Канонические и вариативные рендеры для сравнения.</span>
        </div>
        <div className="cvs-grid">
          <label className="cvs-field">
            <span>Тип</span>
            <select className="cvs-select" value={renderKind} onChange={(event) => setRenderKind(event.target.value)}>
              <option value="canonical">Канонический</option>
              <option value="variant">Вариант</option>
              <option value="expression">Выражение</option>
              <option value="turnaround">Разворот</option>
              <option value="face">Лицо</option>
              <option value="body">Тело</option>
            </select>
          </label>
          <label className="cvs-field">
            <span>Метка</span>
            <input
              className="cvs-input"
              value={renderLabel}
              onChange={(event) => setRenderLabel(event.target.value)}
              placeholder="злой, зал суда"
            />
          </label>
          <label className="cvs-field">
            <span>Количество</span>
            <input
              className="cvs-input"
              type="number"
              min={1}
              max={6}
              value={renderCount}
              onChange={(event) => setRenderCount(clamp(Number(event.target.value || 1), 1, 6))}
            />
          </label>
          <label className="cvs-field">
            <span>Seed (необязательно)</span>
            <input
              className="cvs-input"
              value={renderSeed}
              onChange={(event) => setRenderSeed(event.target.value)}
              placeholder="оставьте пустым для случайного"
            />
          </label>
          <label className="cvs-field">
            <span>Переопределение промпта</span>
            <textarea
              className="cvs-textarea"
              rows={2}
              value={renderPromptOverride}
              onChange={(event) => setRenderPromptOverride(event.target.value)}
            />
          </label>
          <label className="cvs-field">
            <span>Переопределение негатива</span>
            <textarea
              className="cvs-textarea"
              rows={2}
              value={renderNegativeOverride}
              onChange={(event) => setRenderNegativeOverride(event.target.value)}
            />
          </label>
        </div>
        <div className="cvs-actions">
          <button className="primary" disabled={!character || rendering} onClick={handleRender}>
            {rendering ? "Рендер..." : "Сгенерировать представление"}
          </button>
        </div>

        <div className="cvs-library-controls">
          <label className="cvs-field">
            <span>Фильтр</span>
            <select className="cvs-select" value={filterKind} onChange={(event) => setFilterKind(event.target.value)}>
              {kindFilters.map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </label>
          <label className="cvs-field">
            <span>Поиск</span>
            <input
              className="cvs-input"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="метка или тип"
            />
          </label>
        </div>

        <div className="cvs-library-grid">
          {filteredReferences.length === 0 ? (
            <div className="muted">Представлений пока нет.</div>
          ) : (
            filteredReferences.map((ref) => (
              <div key={getRefKey(ref)} className="cvs-library-card">
                <img
                  src={getAssetUrl(ref.thumb_url || ref.url)}
                  alt={ref.label || ref.kind}
                  onClick={() => openLightboxAsset(ref.url, ref.label || ref.kind, character?.name)}
                />
                <div className="cvs-library-meta">
                  <strong>{ref.label || ref.kind}</strong>
                  <span className="muted">{ref.kind}</span>
                </div>
                <div className="cvs-library-actions">
                  <button className="ghost" type="button" onClick={() => handlePickIdentityRef(ref, "face_ref")}>Лицо</button>
                  <button className="ghost" type="button" onClick={() => handlePickIdentityRef(ref, "body_ref")}>Тело</button>
                  <button className="ghost" type="button" onClick={() => handlePickIdentityRef(ref, "canonical_ref")}>Отметить</button>
                  <button className="secondary" type="button" onClick={() => handleSetCanonical(ref)}>
                    Канонический
                  </button>
                  <button className="danger ghost" type="button" onClick={() => handleRemoveReference(ref)}>Удалить</button>
                </div>
                {typeof ref.meta?.seed === "number" && (
                  <div className="cvs-library-meta muted">Seed: {ref.meta.seed}</div>
                )}
              </div>
            ))
          )}
        </div>
      </section>
        </div>
      </details>
      </>
      )}
      {aiFillOpen && (
        <AIFillModal
          title="Форма персонажа"
          formType="character_visual_studio"
          fields={CHARACTER_AI_FIELDS.map((field) =>
            field.key === "render_preset"
              ? { ...field, options: Object.keys(RENDER_PRESETS) }
              : field,
          )}
          currentValues={aiCurrentValues}
          context={aiContext}
          onApply={handleApplyAIFill}
          onClose={() => setAiFillOpen(false)}
        />
      )}
    </div>
  );
}
