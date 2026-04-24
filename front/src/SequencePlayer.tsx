import { useState } from "react";
import { generateDescription } from "../api/ai";
import type { AIFieldSpec } from "../api/ai";
import AIFillModal from "./AIFillModal";
import { VOICE_PROFILE_FIELD_DESCRIPTION, VOICE_PROFILE_PLACEHOLDER } from "../shared/voiceProfile";
import "./QuickCreateModal.css";

type EntityType = "character" | "location";

interface QuickCreateModalProps {
  type: EntityType;
  onClose: () => void;
  onCreate: (data: QuickCreateData, generateSketch: boolean) => Promise<void>;
}

export interface QuickCreateData {
  name: string;
  description: string;
  // Character-specific
  character_type?: string;
  appearance_prompt?: string;
  voice_profile?: string;
  // Location-specific
  visual_reference?: string;
  tags?: string[];
}

const CHARACTER_TEMPLATES = [
  {
    label: "Судья",
    prompt: "судья в мантии, строгое лицо, зал суда",
    voice: "Persona: Male, Middle-aged. Pace: slow. Timbre: deep. Emotion: serious. Scenario: news.",
  },
  {
    label: "Адвокат",
    prompt: "адвокат в костюме, уверенный взгляд, папка с документами",
    voice: "Persona: Female, Middle-aged. Pace: moderate. Timbre: clear. Emotion: calm. Scenario: storytelling.",
  },
  {
    label: "Следователь",
    prompt: "следователь, внимательный взгляд, блокнот",
    voice: "Persona: Male, Young. Pace: moderate. Timbre: clear. Emotion: serious. Scenario: classroom.",
  },
  {
    label: "Свидетель",
    prompt: "обычный человек, нервный взгляд, руки сложены",
    voice: "Persona: Female, Young. Pace: slow. Timbre: raspy. Emotion: gentle. Scenario: storytelling.",
  },
  {
    label: "Подозреваемый",
    prompt: "человек в напряжении, опущенный взгляд",
    voice: "Persona: Male, Young. Pace: fast. Timbre: magnetic. Emotion: lively. Scenario: sales.",
  },
];

const LOCATION_TEMPLATES = [
  { label: "Зал суда", ref: "зал суда, высокие потолки, деревянные скамьи, трибуна судьи", tags: ["суд", "драма"] },
  { label: "Кабинет", ref: "офис, стол с документами, книжные полки, окно", tags: ["офис", "работа"] },
  { label: "Допросная", ref: "допросная комната, стол, два стула, лампа, зеркало", tags: ["полиция", "допрос"] },
  { label: "Улица", ref: "городская улица, здания, прохожие, вечер", tags: ["город", "улица"] },
  { label: "Квартира", ref: "жилая комната, диван, телевизор, обычная обстановка", tags: ["дом", "быт"] },
];

const CHARACTER_FILL_FIELDS: AIFieldSpec[] = [
  { key: "name", label: "Название", type: "string" },
  { key: "description", label: "Описание", type: "string" },
  {
    key: "character_type",
    label: "Роль",
    type: "string",
    options: ["protagonist", "antagonist", "supporting", "background"],
  },
  { key: "appearance_prompt", label: "Промпт внешности", type: "string" },
  {
    key: "voice_profile",
    label: "Голосовой профиль",
    type: "string",
    description: VOICE_PROFILE_FIELD_DESCRIPTION,
  },
];

const LOCATION_FILL_FIELDS: AIFieldSpec[] = [
  { key: "name", label: "Название", type: "string" },
  { key: "description", label: "Описание", type: "string" },
  { key: "visual_reference", label: "Визуальный референс", type: "string" },
  { key: "tags", label: "Теги", type: "array" },
];

export default function QuickCreateModal({ type, onClose, onCreate }: QuickCreateModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [characterType, setCharacterType] = useState("supporting");
  const [appearancePrompt, setAppearancePrompt] = useState("");
  const [voiceProfile, setVoiceProfile] = useState("");
  const [visualReference, setVisualReference] = useState("");
  const [tags, setTags] = useState("");
  const [saving, setSaving] = useState(false);
  const [generateSketch, setGenerateSketch] = useState(true);
  const [aiDescriptionLoading, setAiDescriptionLoading] = useState(false);
  const [aiDescriptionError, setAiDescriptionError] = useState<string | null>(null);
  const [aiFillOpen, setAiFillOpen] = useState(false);

  const isCharacter = type === "character";
  const templates = isCharacter ? CHARACTER_TEMPLATES : LOCATION_TEMPLATES;

  const toCsv = (value: unknown) => {
    if (Array.isArray(value)) {
      return value.map((item) => String(item).trim()).filter(Boolean).join(", ");
    }
    if (typeof value === "string") return value;
    return value ? String(value) : "";
  };

  const openAIFill = () => {
    setAiFillOpen(true);
  };

  const handleApplyFill = (values: Record<string, unknown>) => {
    if (typeof values.name === "string") setName(values.name);
    if (typeof values.description === "string") setDescription(values.description);
    if (isCharacter) {
      if (typeof values.character_type === "string") setCharacterType(values.character_type);
      if (typeof values.appearance_prompt === "string") setAppearancePrompt(values.appearance_prompt);
      if (typeof values.voice_profile === "string") setVoiceProfile(values.voice_profile);
    } else {
      if (typeof values.visual_reference === "string") setVisualReference(values.visual_reference);
      setTags(toCsv(values.tags));
    }
  };

  const handleGenerateDescription = async () => {
    if (!name.trim()) return;
    setAiDescriptionLoading(true);
    setAiDescriptionError(null);
    try {
      const contextParts = isCharacter
        ? [
            appearancePrompt ? `appearance: ${appearancePrompt}` : null,
            voiceProfile ? `voice: ${voiceProfile}` : null,
            characterType ? `role: ${characterType}` : null,
          ]
        : [
            visualReference ? `visual reference: ${visualReference}` : null,
            tags ? `tags: ${tags}` : null,
          ];
      const response = await generateDescription({
        entity_type: isCharacter ? "character" : "location",
        name: name.trim(),
        context: contextParts.filter(Boolean).join("\n"),
      });
      setDescription(response.description || "");
    } catch (err: any) {
      setAiDescriptionError(err?.message || "Не удалось сгенерировать описание.");
    } finally {
      setAiDescriptionLoading(false);
    }
  };

  const applyTemplate = (index: number) => {
    if (isCharacter) {
      const t = CHARACTER_TEMPLATES[index];
      if (!name) setName(t.label);
      setAppearancePrompt(t.prompt);
      setVoiceProfile(t.voice);
    } else {
      const t = LOCATION_TEMPLATES[index];
      if (!name) setName(t.label);
      setVisualReference(t.ref);
      setTags(t.tags.join(", "));
    }
  };

  const handleSubmit = async () => {
    if (!name.trim()) return;
    
    setSaving(true);
    try {
      const data: QuickCreateData = {
        name: name.trim(),
        description: description.trim(),
      };
      
      if (isCharacter) {
        data.character_type = characterType;
        data.appearance_prompt = appearancePrompt.trim() || name;
        data.voice_profile = voiceProfile.trim();
      } else {
        data.visual_reference = visualReference.trim() || name;
        data.tags = tags ? tags.split(",").map(t => t.trim()).filter(Boolean) : [];
      }
      
      await onCreate(data, generateSketch);
      onClose();
    } catch (err) {
      console.error("Failed to create:", err);
    } finally {
      setSaving(false);
    }
  };

  const canSubmit = name.trim() && (isCharacter ? appearancePrompt.trim() : true);

  return (
    <div className="qc-overlay" onClick={onClose}>
      <div className="qc-modal" onClick={e => e.stopPropagation()}>
        <div className="qc-header">
          <h2>✨ Быстрое создание: {isCharacter ? "Персонаж" : "Локация"}</h2>
          <button className="qc-close" onClick={onClose}>×</button>
        </div>

        <div className="qc-templates">
          <span className="qc-templates-label">Шаблоны:</span>
          {templates.map((t, i) => (
            <button key={i} className="qc-template-btn" onClick={() => applyTemplate(i)}>
              {t.label}
            </button>
          ))}
        </div>

        <div className="qc-form">
          <label className="qc-field">
            <span className="qc-label">Имя *</span>
            <input
              className="qc-input"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder={isCharacter ? "Иван Петров" : "Зал суда"}
              autoFocus
            />
          </label>

          <label className="qc-field">
            <span className="qc-label-row">
              <span className="qc-label">Описание</span>
              <button
                className="qc-ai-btn"
                type="button"
                onClick={handleGenerateDescription}
                disabled={!name.trim() || aiDescriptionLoading}
              >
                {aiDescriptionLoading ? "Генерация..." : "Спросить AI"}
              </button>
            </span>
            <textarea
              className="qc-textarea"
              rows={2}
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder={isCharacter ? "Кто этот персонаж, его роль в истории..." : "Что это за место, его атмосфера..."}
            />
            {aiDescriptionError && <span className="qc-error">{aiDescriptionError}</span>}
          </label>

          {isCharacter ? (
            <>
              <label className="qc-field">
                <span className="qc-label">Роль</span>
                <select className="qc-select" value={characterType} onChange={e => setCharacterType(e.target.value)}>
                  <option value="protagonist">Главный герой</option>
                  <option value="antagonist">Антагонист</option>
                  <option value="supporting">Второстепенный</option>
                  <option value="background">Фоновый</option>
                </select>
              </label>

              <label className="qc-field">
                <span className="qc-label">Внешность (для генерации) *</span>
                <textarea
                  className="qc-textarea"
                  rows={2}
                  value={appearancePrompt}
                  onChange={e => setAppearancePrompt(e.target.value)}
                  placeholder="мужчина 40 лет, седые виски, строгий костюм, уверенный взгляд"
                />
              </label>

              <label className="qc-field">
                <span className="qc-label">Голос / манера речи</span>
                <input
                  className="qc-input"
                  value={voiceProfile}
                  onChange={e => setVoiceProfile(e.target.value)}
                  placeholder={VOICE_PROFILE_PLACEHOLDER}
                />
              </label>
            </>
          ) : (
            <>
              <label className="qc-field">
                <span className="qc-label">Визуальное описание (для генерации)</span>
                <textarea
                  className="qc-textarea"
                  rows={2}
                  value={visualReference}
                  onChange={e => setVisualReference(e.target.value)}
                  placeholder="зал суда, высокие потолки, деревянные скамьи"
                />
              </label>

              <label className="qc-field">
                <span className="qc-label">Теги (через запятую)</span>
                <input
                  className="qc-input"
                  value={tags}
                  onChange={e => setTags(e.target.value)}
                  placeholder="суд, драма, финал"
                />
              </label>
            </>
          )}

          <label className="qc-checkbox">
            <input
              type="checkbox"
              checked={generateSketch}
              onChange={e => setGenerateSketch(e.target.checked)}
            />
            <span>Сразу сгенерировать скетч</span>
          </label>
        </div>

        <div className="qc-actions">
          <button className="qc-btn secondary" type="button" onClick={openAIFill}>AI заполнение</button>
          <button className="qc-btn secondary" onClick={onClose}>Отмена</button>
          <button 
            className="qc-btn primary" 
            onClick={handleSubmit} 
            disabled={!canSubmit || saving}
          >
            {saving ? "Создание..." : "Создать"}
          </button>
        </div>
      </div>
      {aiFillOpen && (
        <AIFillModal
          title={isCharacter ? "Быстрый персонаж" : "Быстрая локация"}
          formType={isCharacter ? "quick_character" : "quick_location"}
          fields={isCharacter ? CHARACTER_FILL_FIELDS : LOCATION_FILL_FIELDS}
          currentValues={
            isCharacter
              ? {
                  name,
                  description,
                  character_type: characterType,
                  appearance_prompt: appearancePrompt,
                  voice_profile: voiceProfile,
                }
              : {
                  name,
                  description,
                  visual_reference: visualReference,
                  tags: tags.split(",").map((item) => item.trim()).filter(Boolean),
                }
          }
          context={description ? `current description: ${description}` : undefined}
          onApply={handleApplyFill}
          onClose={() => setAiFillOpen(false)}
        />
      )}
    </div>
  );
}
