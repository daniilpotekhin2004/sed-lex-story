import React, { useEffect, useMemo, useState } from "react";
import { SettingsPanel } from "../components/generation/SettingsPanel";
import { TaskStatusBar } from "../components/generation/TaskStatusBar";
import { ResultsGrid } from "../components/generation/ResultsGrid";
import { TaskHistory } from "../components/generation/TaskHistory";
import { useGenerateImage } from "../hooks/useGenerateImage";
import { useTaskStore } from "../hooks/useTaskStore";
import { usePresets } from "../hooks/usePresets";
import { usePersistedSettings } from "../hooks/usePersistedSettings";
import { createCharacterPreset, generateCombinedPrompt, listCharacterPresets } from "../api/characters";
import type { CharacterPreset, SDPromptResponse, TaskSummary } from "../shared/types";

const STORY_BEATS_KEY = "lwq_story_beats";
const STORY_BRIEF_KEY = "lwq_story_brief";

const DEFAULT_NEGATIVE =
  "blurry, low quality, overexposed, underexposed, watermark, signature, extra limbs, distorted hands, deformed face, low-res, duplicated features";
const CHARACTER_NEGATIVE =
  "asymmetry, deformed hands, extra fingers, low detail skin, artifacts, watermark";

const SHOT_OPTIONS = [
  { id: "establishing", label: "Общий план", value: "establishing wide shot, 24mm lens, sense of scale" },
  { id: "medium", label: "Средний план", value: "cinematic medium shot, 35mm lens, balanced framing" },
  { id: "portrait", label: "Портрет", value: "portrait close-up, 85mm lens, shallow depth of field" },
  { id: "action", label: "Действие", value: "dynamic action shot, 35mm lens, dramatic angle" },
];

const LIGHTING_OPTIONS = [
  { id: "studio", label: "Студия", value: "clean studio lighting, three point light setup" },
  { id: "night", label: "Ночь", value: "night lighting, cool blue tones, gentle rim light" },
  { id: "dusk", label: "Золотой час", value: "sunset glow, golden hour rim light, long shadows" },
  { id: "neon", label: "Неон", value: "neon city lights, reflective surfaces, moody contrast" },
  { id: "overcast", label: "Пасмурно", value: "soft overcast lighting, diffuse shadows" },
];

const MOOD_OPTIONS = [
  { id: "tense", label: "Напряжённо", value: "tense atmosphere, heightened contrast" },
  { id: "calm", label: "Спокойно", value: "calm mood, balanced soft light" },
  { id: "heroic", label: "Героично", value: "heroic tone, confident posture" },
  { id: "mysterious", label: "Таинственно", value: "mysterious vibe, foggy depth" },
  { id: "romantic", label: "Романтично", value: "romantic warmth, soft highlights" },
];

const STYLE_OPTIONS = [
  { id: "cinematic", label: "Кинематографично", value: "cinematic still frame, depth of field, film grain" },
  { id: "aesthetic", label: "Эстетично", value: "award-winning photography, dramatic composition" },
  { id: "noir", label: "Нуар", value: "film noir aesthetic, high contrast rim lighting" },
  { id: "illustration", label: "Иллюстрация", value: "digital illustration, painterly shading, rich colors" },
  { id: "high", label: "Ультра‑деталь", value: "ultra-detailed, sharp focus, 8k" },
];

const ROLE_TAGS: Record<string, string> = {
  protagonist: "lead character focus",
  antagonist: "ominous presence, antagonist focus",
  supporting: "supporting character, complementary framing",
  background: "background character, subtle presence",
};

type StoryBeat = {
  id: string;
  title: string;
  description: string;
};

type CharacterDraft = {
  name: string;
  description: string;
  role: string;
  traits: string;
  anchor: string;
  appearance_prompt: string;
  negative_prompt: string;
  is_public: boolean;
};

function buildScenePrompt(
  description: string,
  config: { shot: string; lighting: string; mood: string; style: string },
) {
  const shotTag = SHOT_OPTIONS.find((item) => item.id === config.shot)?.value ?? SHOT_OPTIONS[1].value;
  const lightingTag =
    LIGHTING_OPTIONS.find((item) => item.id === config.lighting)?.value ?? LIGHTING_OPTIONS[0].value;
  const moodTag = MOOD_OPTIONS.find((item) => item.id === config.mood)?.value ?? "";
  const styleTag = STYLE_OPTIONS.find((item) => item.id === config.style)?.value ?? STYLE_OPTIONS[0].value;
  return [shotTag, lightingTag, moodTag, styleTag, description.trim()].filter(Boolean).join(", ");
}

function buildCharacterPrompt(draft: CharacterDraft) {
  const traits = draft.traits
    ? draft.traits
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
        .join(", ")
    : "";
  const roleTag = ROLE_TAGS[draft.role] || ROLE_TAGS.supporting;
  const anchor = draft.anchor ? `consistency tag ${draft.anchor}` : "";
  const baseSheet = "turnaround character sheet, neutral pose, evenly lit, clean background";
  const detail = "studio lighting, skin texture, accurate anatomy";
  return [roleTag, draft.name, draft.description, traits, baseSheet, detail, anchor]
    .filter(Boolean)
    .join(", ");
}

function loadStoryBeats(): StoryBeat[] {
  const raw = localStorage.getItem(STORY_BEATS_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function generateId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `beat-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
}

export const GeneratePage: React.FC = () => {
  const { mutateAsync, isPending, error } = useGenerateImage();
  const tasks = useTaskStore((s) => s.tasks);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const { data: presets, isLoading: isLoadingPresets } = usePresets();
  const { settings, setSettings, setPrompt, setNegativePrompt, prompt } = usePersistedSettings();

  const [promptDraft, setPromptDraft] = useState(prompt);
  const [negativeDraft, setNegativeDraft] = useState(settings.negativePrompt ?? "");

  const [sceneBrief, setSceneBrief] = useState(() => localStorage.getItem(STORY_BRIEF_KEY) ?? "");
  const [storyBeats, setStoryBeats] = useState<StoryBeat[]>(() => loadStoryBeats());
  const [beatDraft, setBeatDraft] = useState({ title: "", description: "" });

  const [shot, setShot] = useState("medium");
  const [lighting, setLighting] = useState("studio");
  const [mood, setMood] = useState("calm");
  const [styleTag, setStyleTag] = useState("cinematic");
  const [buildingPrompt, setBuildingPrompt] = useState(false);
  const [promptMeta, setPromptMeta] = useState<SDPromptResponse | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);

  const [characters, setCharacters] = useState<CharacterPreset[]>([]);
  const [charactersLoading, setCharactersLoading] = useState(true);
  const [characterFilter, setCharacterFilter] = useState("");
  const [selectedCharacters, setSelectedCharacters] = useState<string[]>([]);
  const [characterDraft, setCharacterDraft] = useState<CharacterDraft>({
    name: "",
    description: "",
    role: "supporting",
    traits: "",
    anchor: "",
    appearance_prompt: "",
    negative_prompt: CHARACTER_NEGATIVE,
    is_public: false,
  });
  const [characterSaving, setCharacterSaving] = useState(false);
  const [characterError, setCharacterError] = useState<string | null>(null);

  useEffect(() => {
    setPromptDraft(prompt);
  }, [prompt]);

  useEffect(() => {
    setNegativeDraft(settings.negativePrompt ?? "");
  }, [settings.negativePrompt]);

  useEffect(() => {
    localStorage.setItem(STORY_BRIEF_KEY, sceneBrief);
  }, [sceneBrief]);

  useEffect(() => {
    localStorage.setItem(STORY_BEATS_KEY, JSON.stringify(storyBeats));
  }, [storyBeats]);

  useEffect(() => {
    void loadCharacters();
  }, []);

  const activeTask: TaskSummary | undefined = useMemo(() => {
    if (activeTaskId) {
      return tasks.find((t) => t.taskId === activeTaskId);
    }
    return tasks[0];
  }, [tasks, activeTaskId]);

  const selectedCharacterNames = useMemo(() => {
    return selectedCharacters
      .map((id) => characters.find((char) => char.id === id)?.name)
      .filter(Boolean);
  }, [selectedCharacters, characters]);

  const filteredCharacters = useMemo(() => {
    if (!characterFilter.trim()) return characters;
    const query = characterFilter.toLowerCase();
    return characters.filter(
      (char) =>
        char.name.toLowerCase().includes(query) ||
        (char.description || "").toLowerCase().includes(query),
    );
  }, [characters, characterFilter]);

  async function loadCharacters() {
    try {
      setCharactersLoading(true);
      const data = await listCharacterPresets();
      setCharacters(data);
    } catch (err) {
      console.error("Failed to load characters", err);
    } finally {
      setCharactersLoading(false);
    }
  }

  const handleGenerate = async () => {
    if (!promptDraft.trim()) return;
    setPrompt(promptDraft);
    setNegativePrompt(negativeDraft || null);
    const result = await mutateAsync({
      prompt: promptDraft,
      negative_prompt: negativeDraft || undefined,
      style: settings.style,
      num_variants: settings.num_variants,
      width: settings.width,
      height: settings.height,
      cfg_scale: settings.cfg_scale,
      steps: settings.steps,
      character_preset: settings.character_preset,
      lora_preset: settings.lora_preset,
    });
    setActiveTaskId(result.task_id);
  };

  async function handleBuildPrompt() {
    if (!sceneBrief.trim()) {
      setBuildError("Сначала опишите сцену.");
      return;
    }
    setBuildError(null);
    setBuildingPrompt(true);
    const basePrompt = buildScenePrompt(sceneBrief, { shot, lighting, mood, style: styleTag });
    try {
      if (selectedCharacters.length > 0) {
        const response = await generateCombinedPrompt({
          prompt: basePrompt,
          character_ids: selectedCharacters,
          style: settings.style || "cinematic",
          width: settings.width,
          height: settings.height,
          steps: settings.steps,
          cfg_scale: settings.cfg_scale,
        });
        setPromptMeta(response);
        setPromptDraft(response.prompt);
        setNegativeDraft(response.negative_prompt || DEFAULT_NEGATIVE);
        setPrompt(response.prompt);
        setNegativePrompt(response.negative_prompt || DEFAULT_NEGATIVE);
      } else {
        setPromptMeta(null);
        setPromptDraft(basePrompt);
        setNegativeDraft(DEFAULT_NEGATIVE);
        setPrompt(basePrompt);
        setNegativePrompt(DEFAULT_NEGATIVE);
      }
    } catch (err) {
      console.error("Failed to build prompt", err);
      setBuildError("Не удалось собрать промпт. Попробуйте ещё раз.");
    } finally {
      setBuildingPrompt(false);
    }
  }

  function handleAddBeat() {
    if (!beatDraft.title.trim() || !beatDraft.description.trim()) return;
    setStoryBeats((prev) => [
      { id: generateId(), title: beatDraft.title.trim(), description: beatDraft.description.trim() },
      ...prev,
    ]);
    setBeatDraft({ title: "", description: "" });
  }

  function handleRemoveBeat(beatId: string) {
    setStoryBeats((prev) => prev.filter((beat) => beat.id !== beatId));
  }

  function toggleCharacter(id: string) {
    setSelectedCharacters((prev) => (prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id]));
  }

  function handleBuildCharacterPrompt() {
    if (!characterDraft.name.trim()) {
      setCharacterError("Имя персонажа обязательно.");
      return;
    }
    setCharacterError(null);
    const promptValue = buildCharacterPrompt(characterDraft);
    setCharacterDraft((prev) => ({
      ...prev,
      appearance_prompt: promptValue,
      negative_prompt: prev.negative_prompt || CHARACTER_NEGATIVE,
    }));
  }

  async function handleCreateCharacter() {
    if (!characterDraft.name.trim()) {
      setCharacterError("Имя персонажа обязательно.");
      return;
    }
    const appearancePrompt = characterDraft.appearance_prompt.trim() || buildCharacterPrompt(characterDraft);
    if (!appearancePrompt.trim()) {
      setCharacterError("Промпт персонажа обязателен.");
      return;
    }
    setCharacterError(null);
    setCharacterSaving(true);
    try {
      const created = await createCharacterPreset({
        name: characterDraft.name.trim(),
        description: characterDraft.description || null,
        character_type: characterDraft.role,
        appearance_prompt: appearancePrompt,
        negative_prompt: characterDraft.negative_prompt || CHARACTER_NEGATIVE,
        style_tags: characterDraft.traits
          ? characterDraft.traits.split(",").map((item) => item.trim()).filter(Boolean)
          : null,
        is_public: characterDraft.is_public,
      });
      setCharacters((prev) => [created, ...prev]);
      setSelectedCharacters((prev) => [...new Set([...prev, created.id])]);
      setCharacterDraft({
        name: "",
        description: "",
        role: "supporting",
        traits: "",
        anchor: "",
        appearance_prompt: "",
        negative_prompt: CHARACTER_NEGATIVE,
        is_public: false,
      });
    } catch (err) {
      console.error("Failed to create character", err);
      setCharacterError("Не удалось сохранить пресет персонажа.");
    } finally {
      setCharacterSaving(false);
    }
  }

  return (
    <div className="studio-shell">
      <header className="studio-hero">
        <div>
          <div className="studio-kicker">Студия изображений</div>
          <h1>Генерация от сюжета</h1>
          <p>Создавайте кинематографичные промпты, фиксируйте консистентность персонажей и рендерьте готовые кадры.</p>
          <div className="studio-badges">
            <span className="studio-chip">Постоянные персонажи</span>
            <span className="studio-chip">Переводчик промптов</span>
            <span className="studio-chip">Готовые рендеры</span>
          </div>
        </div>
      </header>

      <div className="studio-layout">
        <div className="studio-column">
          <section className="studio-panel">
            <div className="studio-panel-header">
              <div>
                <h2>Сюжетные вехи</h2>
                <p className="muted">Зафиксируйте драматургию до рендера.</p>
              </div>
              <span className="studio-chip">{storyBeats.length} вех</span>
            </div>
            <div className="studio-beat-list">
              {storyBeats.length === 0 ? (
                <div className="muted">Вех пока нет. Добавьте первую.</div>
              ) : (
                storyBeats.map((beat) => (
                  <div key={beat.id} className="studio-beat-card">
                    <button
                      type="button"
                      className="studio-beat-main"
                      onClick={() => setSceneBrief(beat.description)}
                    >
                      <strong>{beat.title}</strong>
                      <span>{beat.description}</span>
                    </button>
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => handleRemoveBeat(beat.id)}
                    >Удалить</button>
                  </div>
                ))
              )}
            </div>
            <div className="studio-form">
              <label className="studio-field">
                <span>Название вехи</span>
                <input
                  className="studio-input"
                  value={beatDraft.title}
                  onChange={(event) => setBeatDraft({ ...beatDraft, title: event.target.value })}
                  placeholder="Завязка"
                />
              </label>
              <label className="studio-field">
                <span>Описание вехи</span>
                <textarea
                  className="studio-textarea"
                  rows={3}
                  value={beatDraft.description}
                  onChange={(event) => setBeatDraft({ ...beatDraft, description: event.target.value })}
                  placeholder="Опишите переломный момент..."
                />
              </label>
              <div className="studio-actions">
                <button className="secondary" type="button" onClick={handleAddBeat}>
                  Добавить веху
                </button>
              </div>
            </div>
          </section>

          <section className="studio-panel">
            <div className="studio-panel-header">
              <div>
                <h2>Хранилище персонажей</h2>
                <p className="muted">Выберите состав, чтобы сохранить консистентность лиц.</p>
              </div>
              <span className="studio-chip">{selectedCharacters.length} выбрано</span>
            </div>
            <input
              className="studio-input"
              placeholder="Поиск персонажей"
              value={characterFilter}
              onChange={(event) => setCharacterFilter(event.target.value)}
            />
            <div className="studio-character-grid">
              {charactersLoading ? (
                <div className="muted">Загрузка персонажей...</div>
              ) : filteredCharacters.length === 0 ? (
                <div className="muted">Персонажи не найдены.</div>
              ) : (
                filteredCharacters.map((character) => (
                  <button
                    key={character.id}
                    type="button"
                    className={`studio-character-card ${
                      selectedCharacters.includes(character.id) ? "selected" : ""
                    }`}
                    onClick={() => toggleCharacter(character.id)}
                  >
                    <div className="studio-character-top">
                      <strong>{character.name}</strong>
                      <span className="studio-pill">{character.character_type}</span>
                    </div>
                    <p>{character.description || "Без описания"}</p>
                  </button>
                ))
              )}
            </div>
            <div className="studio-actions">
              <button className="ghost" type="button" onClick={() => setSelectedCharacters([])}>
                Очистить выбор
              </button>
            </div>
          </section>

          <section className="studio-panel">
            <div className="studio-panel-header">
              <div>
                <h2>Кузница персонажей</h2>
                <p className="muted">Создавайте пресеты для использования во всей истории.</p>
              </div>
              <button
                className="ghost"
                type="button"
                onClick={() =>
                  setCharacterDraft({
                    name: "",
                    description: "",
                    role: "supporting",
                    traits: "",
                    anchor: "",
                    appearance_prompt: "",
                    negative_prompt: CHARACTER_NEGATIVE,
                    is_public: false,
                  })
                }
              >Сбросить</button>
            </div>
            {characterError && <div className="studio-error">{characterError}</div>}
            <div className="studio-form">
              <label className="studio-field">
                <span>Название</span>
                <input
                  className="studio-input"
                  value={characterDraft.name}
                  onChange={(event) =>
                    setCharacterDraft((prev) => ({ ...prev, name: event.target.value }))
                  }
                  placeholder="Детектив Соколов"
                />
              </label>
              <label className="studio-field">
                <span>Роль</span>
                <select
                  className="studio-select"
                  value={characterDraft.role}
                  onChange={(event) =>
                    setCharacterDraft((prev) => ({ ...prev, role: event.target.value }))
                  }
                >
                  <option value="protagonist">Протагонист</option>
                  <option value="antagonist">Антагонист</option>
                  <option value="supporting">Второстепенный</option>
                  <option value="background">Фон</option>
                </select>
              </label>
              <label className="studio-field">
                <span>Описание</span>
                <textarea
                  className="studio-textarea"
                  rows={2}
                  value={characterDraft.description}
                  onChange={(event) =>
                    setCharacterDraft((prev) => ({ ...prev, description: event.target.value }))
                  }
                  placeholder="Возраст, стиль, ключевые детали..."
                />
              </label>
              <label className="studio-field">
                <span>Визуальные теги</span>
                <input
                  className="studio-input"
                  value={characterDraft.traits}
                  onChange={(event) =>
                    setCharacterDraft((prev) => ({ ...prev, traits: event.target.value }))
                  }
                  placeholder="шрам на щеке, шерстяное пальто, острый взгляд"
                />
              </label>
              <label className="studio-field">
                <span>Якорь консистентности</span>
                <input
                  className="studio-input"
                  value={characterDraft.anchor}
                  onChange={(event) =>
                    setCharacterDraft((prev) => ({ ...prev, anchor: event.target.value }))
                  }
                  placeholder="token-lwq-01"
                />
              </label>
              <label className="studio-field">
                <span>Промпт внешности</span>
                <textarea
                  className="studio-textarea"
                  rows={3}
                  value={characterDraft.appearance_prompt}
                  onChange={(event) =>
                    setCharacterDraft((prev) => ({ ...prev, appearance_prompt: event.target.value }))
                  }
                  placeholder="Нажмите «Собрать», чтобы сгенерировать."
                />
              </label>
              <label className="studio-field">
                <span>Негативный промпт</span>
                <textarea
                  className="studio-textarea"
                  rows={2}
                  value={characterDraft.negative_prompt}
                  onChange={(event) =>
                    setCharacterDraft((prev) => ({ ...prev, negative_prompt: event.target.value }))
                  }
                />
              </label>
              <label className="studio-checkbox">
                <input
                  type="checkbox"
                  checked={characterDraft.is_public}
                  onChange={(event) =>
                    setCharacterDraft((prev) => ({ ...prev, is_public: event.target.checked }))
                  }
                />
                Публичный пресет
              </label>
              <div className="studio-actions">
                <button className="secondary" type="button" onClick={handleBuildCharacterPrompt}>
                  Собрать промпт
                </button>
                <button className="primary" type="button" onClick={handleCreateCharacter} disabled={characterSaving}>
                  {characterSaving ? "Сохранение..." : "Сохранить в хранилище"}
                </button>
              </div>
            </div>
          </section>
        </div>

        <div className="studio-column">
          <section className="studio-panel">
            <div className="studio-panel-header">
              <div>
                <h2>Кузница промптов</h2>
                <p className="muted">Преобразуйте сюжетные вехи в кинематографичные промпты.</p>
              </div>
              <button className="secondary" type="button" onClick={handleBuildPrompt} disabled={buildingPrompt}>
                {buildingPrompt ? "Сборка..." : "Собрать промпт"}
              </button>
            </div>
            {buildError && <div className="studio-error">{buildError}</div>}
            <div className="studio-form">
              <label className="studio-field">
                <span>Краткое описание сцены</span>
                <textarea
                  className="studio-textarea"
                  rows={4}
                  value={sceneBrief}
                  onChange={(event) => setSceneBrief(event.target.value)}
                  placeholder="Опишите кадр и действие..."
                />
              </label>
              <div className="studio-grid">
                <label className="studio-field">
                  <span>Кадр</span>
                  <select className="studio-select" value={shot} onChange={(event) => setShot(event.target.value)}>
                    {SHOT_OPTIONS.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="studio-field">
                  <span>Свет</span>
                  <select
                    className="studio-select"
                    value={lighting}
                    onChange={(event) => setLighting(event.target.value)}
                  >
                    {LIGHTING_OPTIONS.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="studio-field">
                  <span>Настроение</span>
                  <select className="studio-select" value={mood} onChange={(event) => setMood(event.target.value)}>
                    {MOOD_OPTIONS.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="studio-field">
                  <span>Стиль</span>
                  <select
                    className="studio-select"
                    value={styleTag}
                    onChange={(event) => setStyleTag(event.target.value)}
                  >
                    {STYLE_OPTIONS.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="studio-cast">
                <span className="studio-label">Состав:</span>
                {selectedCharacterNames.length === 0 ? (
                  <span className="muted">Персонажи не выбраны.</span>
                ) : (
                  selectedCharacterNames.map((name) => (
                    <span key={name} className="studio-chip">
                      {name}
                    </span>
                  ))
                )}
              </div>
            </div>
          </section>

          <form
            className="studio-panel"
            onSubmit={(event) => {
              event.preventDefault();
              void handleGenerate();
            }}
          >
            <div className="studio-panel-header">
              <div>
                <h2>Текущий промпт</h2>
                <p className="muted">Отредактируйте перед отправкой в очередь рендера.</p>
              </div>
              <button className="primary" type="submit" disabled={isPending || !promptDraft.trim()}>
                {isPending ? "Рендер..." : "Рендер"}
              </button>
            </div>
            <label className="studio-field">
              <span>Промпт</span>
              <textarea
                className="studio-textarea"
                rows={4}
                value={promptDraft}
                onChange={(event) => {
                  setPromptDraft(event.target.value);
                  setPrompt(event.target.value);
                }}
              />
            </label>
            <label className="studio-field">
              <span>Негативный промпт</span>
              <textarea
                className="studio-textarea"
                rows={2}
                value={negativeDraft}
                onChange={(event) => {
                  setNegativeDraft(event.target.value);
                  setNegativePrompt(event.target.value);
                }}
              />
            </label>
            {promptMeta && (
              <div className="studio-meta">
                <div>
                  <strong>Подсказки LoRA</strong>
                  <span>{promptMeta.lora_models?.length || 0}</span>
                </div>
                <div>
                  <strong>Эмбеддинги</strong>
                  <span>{promptMeta.embeddings?.length || 0}</span>
                </div>
                <div>
                  <strong>Персонажи</strong>
                  <span>{promptMeta.characters?.length || 0}</span>
                </div>
              </div>
            )}
          </form>

          <TaskStatusBar taskId={activeTask?.taskId ?? null} />
          <ResultsGrid outputs={activeTask?.outputs} />
        </div>

        <div className="studio-column">
          <SettingsPanel
            value={settings}
            onChange={setSettings}
            disabled={isPending}
            presets={presets}
            loadingPresets={isLoadingPresets}
          />
          {error && <div className="card error">Ошибка: {(error as Error).message}</div>}
          <TaskHistory
            onSelect={(taskId) => {
              setActiveTaskId(taskId);
            }}
          />
        </div>
      </div>
    </div>
  );
};
