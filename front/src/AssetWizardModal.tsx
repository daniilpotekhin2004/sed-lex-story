import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getAllSDOptions } from "../api/sdOptions";
import {
  createUserPreset,
  deleteUserPreset,
  listUserPresets,
  touchUserPreset,
  updateUserPreset,
} from "../api/userPresets";
import type {
  GenerationOverrides,
  LoraRef,
  UserGenerationPreset,
  UserPresetCreate,
} from "../shared/types";
import {
  getGenerationEnvironment,
  setGenerationEnvironment,
  type GenerationEnvironment,
} from "../utils/generationEnvironment";

type Props = {
  value: GenerationOverrides;
  onChange: (next: GenerationOverrides) => void;
  title?: string;

  // UI toggles
  showResolution?: boolean;
  showCfgSteps?: boolean;
  showNegative?: boolean;
  showModelSampler?: boolean;
  showLoras?: boolean;
  showSeed?: boolean;
  showPipelineProfile?: boolean;
};

type SelectOption = {
  value: string;
  label: string;
};

function clampNumber(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function presetToOverrides(preset: UserGenerationPreset): GenerationOverrides {
  return {
    width: preset.width,
    height: preset.height,
    steps: preset.steps,
    cfg_scale: preset.cfg_scale,
    negative_prompt: preset.negative_prompt ?? null,
    sampler: preset.sampler ?? null,
    scheduler: preset.scheduler ?? null,
    model_id: preset.model_id ?? null,
    vae_id: preset.vae_id ?? null,
    seed: preset.seed ?? null,
    pipeline_profile_id: preset.pipeline_profile_id ?? null,
    pipeline_profile_version: preset.pipeline_profile_version ?? null,
    loras: preset.lora_models ?? null,
  };
}

function overridesToPresetPayload(name: string, description: string, isFavorite: boolean, o: GenerationOverrides): UserPresetCreate {
  return {
    name,
    description: description || null,
    is_favorite: isFavorite,
    negative_prompt: o.negative_prompt ?? null,
    cfg_scale: o.cfg_scale ?? 7,
    steps: o.steps ?? 20,
    width: o.width ?? 512,
    height: o.height ?? 512,
    sampler: o.sampler ?? null,
    scheduler: o.scheduler ?? null,
    model_id: o.model_id ?? null,
    vae_id: o.vae_id ?? null,
    seed: o.seed ?? null,
    pipeline_profile_id: o.pipeline_profile_id ?? null,
    pipeline_profile_version: o.pipeline_profile_version ?? null,
    lora_models: o.loras ?? null,
  };
}

export default function AdvancedGenerationSettings({
  value,
  onChange,
  title = "Настройки генерации",
  showResolution = true,
  showCfgSteps = true,
  showNegative = true,
  showModelSampler = true,
  showLoras = true,
  showSeed = true,
  showPipelineProfile = false,
}: Props) {
  const queryClient = useQueryClient();
  const [selectedPresetId, setSelectedPresetId] = useState<string>("");
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveDescription, setSaveDescription] = useState("");
  const [saveFavorite, setSaveFavorite] = useState(false);
  const [generationEnv, setGenerationEnvState] = useState<GenerationEnvironment>(getGenerationEnvironment());

  const { data: sdOptions, isLoading: optionsLoading } = useQuery({
    queryKey: ["sdOptionsAll"],
    queryFn: getAllSDOptions,
    staleTime: 5 * 60 * 1000,
  });

  const { data: presetList, isLoading: presetsLoading } = useQuery({
    queryKey: ["userPresets"],
    queryFn: listUserPresets,
    staleTime: 30 * 1000,
  });

  const presets = presetList?.items ?? [];
  const selectedPreset = useMemo(
    () => presets.find((p) => p.id === selectedPresetId),
    [presets, selectedPresetId],
  );

  const createMutation = useMutation({
    mutationFn: (payload: UserPresetCreate) => createUserPreset(payload),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ["userPresets"] });
      setSelectedPresetId(created.id);
      setSaveOpen(false);
      setSaveName("");
      setSaveDescription("");
      setSaveFavorite(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ presetId, payload }: { presetId: string; payload: Partial<UserPresetCreate> }) =>
      updateUserPreset(presetId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["userPresets"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (presetId: string) => deleteUserPreset(presetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["userPresets"] });
      setSelectedPresetId("");
    },
  });

  const touchMutation = useMutation({
    mutationFn: (presetId: string) => touchUserPreset(presetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["userPresets"] });
    },
  });

  const loraOptions = sdOptions?.loras ?? [];
  const modelOptions = sdOptions?.sd_models ?? [];
  const vaeOptions = sdOptions?.vae_models ?? [];

  const samplerOptions = useMemo<SelectOption[]>(
    () =>
      (sdOptions?.samplers ?? [])
        .map((sampler: any) => {
          if (typeof sampler === "string") {
            return { value: sampler, label: sampler };
          }
          const name = String(sampler?.name ?? "");
          return { value: name, label: name };
        })
        .filter((option) => option.value),
    [sdOptions?.samplers],
  );

  const schedulerOptions = useMemo<SelectOption[]>(
    () =>
      (sdOptions?.schedulers ?? [])
        .map((scheduler: any) => {
          if (typeof scheduler === "string") {
            return { value: scheduler, label: scheduler };
          }
          const name = String(scheduler?.name ?? "");
          const label = String(scheduler?.label ?? name);
          return { value: name, label };
        })
        .filter((option) => option.value),
    [sdOptions?.schedulers],
  );

  const loras: LoraRef[] = (value.loras ?? []) as LoraRef[];

  const [loraDraftName, setLoraDraftName] = useState<string>("");
  const [loraDraftWeight, setLoraDraftWeight] = useState<number>(0.8);

  const isBusy =
    optionsLoading ||
    presetsLoading ||
    createMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending ||
    touchMutation.isPending;

  const applyPreset = () => {
    if (!selectedPreset) return;
    onChange({ ...value, ...presetToOverrides(selectedPreset) });
    // small convenience: update usage counter
    touchMutation.mutate(selectedPreset.id);
  };

  const saveNewPreset = () => {
    const name = saveName.trim();
    if (!name) return;
    const payload = overridesToPresetPayload(name, saveDescription.trim(), saveFavorite, value);
    createMutation.mutate(payload);
  };

  const updateSelectedPreset = () => {
    if (!selectedPreset) return;
    const payload = overridesToPresetPayload(
      selectedPreset.name,
      selectedPreset.description ?? "",
      selectedPreset.is_favorite,
      value,
    );
    updateMutation.mutate({ presetId: selectedPreset.id, payload });
  };

  const removeSelectedPreset = () => {
    if (!selectedPreset) return;
    if (!window.confirm(`Удалить пресет "${selectedPreset.name}"?`)) return;
    deleteMutation.mutate(selectedPreset.id);
  };

  const addLora = () => {
    const name = loraDraftName.trim();
    if (!name) return;
    const next: LoraRef[] = [...loras];
    const existingIdx = next.findIndex((l) => l.name === name);
    const weight = clampNumber(loraDraftWeight, 0, 2);
    if (existingIdx >= 0) {
      next[existingIdx] = { ...next[existingIdx], weight };
    } else {
      next.push({ name, weight });
    }
    onChange({ ...value, loras: next });
    setLoraDraftName("");
    setLoraDraftWeight(0.8);
  };

  const updateLora = (idx: number, patch: Partial<LoraRef>) => {
    const next = loras.map((l, i) => (i === idx ? { ...l, ...patch } : l));
    // de-dupe by name (keep last)
    const deduped: LoraRef[] = [];
    for (const item of next) {
      const found = deduped.findIndex((d) => d.name === item.name);
      if (found >= 0) {
        deduped.splice(found, 1);
      }
      deduped.push(item);
    }
    onChange({ ...value, loras: deduped });
  };

  const removeLora = (idx: number) => {
    const next = loras.filter((_, i) => i !== idx);
    onChange({ ...value, loras: next });
  };

  const handleGenerationEnvChange = (next: GenerationEnvironment) => {
    setGenerationEnvironment(next);
    setGenerationEnvState(next);
  };

  return (
    <div className="cvs-card" style={{ padding: 16 }}>
      <div className="cvs-card-header" style={{ marginBottom: 12 }}>
        <div>
          <strong>{title}</strong>
          <div className="muted" style={{ marginTop: 4 }}>
            Пресеты сохраняют LoRA/модель/сэмплер (и при желании размер/шаги), чтобы использовать их повторно.
          </div>
        </div>
      </div>

      <div className="cvs-grid">
        <label className="cvs-field">
          <span>Провайдер</span>
          <select
            className="cvs-select"
            value={generationEnv}
            onChange={(event) => handleGenerationEnvChange(event.target.value as GenerationEnvironment)}
          >
            <option value="local">Локально</option>
            <option value="comfy_api">ComfyUI API</option>
            <option value="poe_api">Poe Image (быстро)</option>
          </select>
          <span className="muted">Переключатель действует на новые генерации во всех режимах.</span>
        </label>

        <label className="cvs-field">
          <span>Пресет</span>
          <select
            className="cvs-select"
            value={selectedPresetId}
            onChange={(e) => setSelectedPresetId(e.target.value)}
            disabled={isBusy}
          >
            <option value="">— нет —</option>
            {presets
              .slice()
              .sort((a, b) => {
                if (a.is_favorite !== b.is_favorite) return a.is_favorite ? -1 : 1;
                return a.name.localeCompare(b.name);
              })
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.is_favorite ? "★ " : ""}
                  {p.name}
                </option>
              ))}
          </select>
          {selectedPreset ? (
            <span className="muted">
              {selectedPreset.description ? selectedPreset.description : ""}
            </span>
          ) : null}
        </label>

        <div className="cvs-field">
          <span>Действия</span>
          <div className="cvs-actions" style={{ justifyContent: "flex-start", gap: 8 }}>
            <button className="secondary" type="button" disabled={!selectedPreset || isBusy} onClick={applyPreset}>Применить</button>
            <button className="secondary" type="button" disabled={isBusy} onClick={() => setSaveOpen((v) => !v)}>
              {saveOpen ? "Отмена" : "Сохранить как…"}
            </button>
            <button
              className="secondary"
              type="button"
              disabled={!selectedPreset || isBusy}
              onClick={updateSelectedPreset}
              title="Перезаписать выбранный пресет текущими настройками"
            >Обновить</button>
            <button className="secondary" type="button" disabled={!selectedPreset || isBusy} onClick={removeSelectedPreset}>Удалить</button>
          </div>
        </div>
      </div>

      {saveOpen ? (
        <div className="cvs-card" style={{ padding: 12, marginTop: 12 }}>
          <div className="cvs-grid">
            <label className="cvs-field">
              <span>Название</span>
              <input
                className="cvs-input"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                placeholder="например, Кино + LoRA зала суда"
              />
            </label>
            <label className="cvs-field">
              <span>Описание</span>
              <input
                className="cvs-input"
                value={saveDescription}
                onChange={(e) => setSaveDescription(e.target.value)}
                placeholder="необязательно"
              />
            </label>
            <label className="cvs-field cvs-checkbox">
              <input type="checkbox" checked={saveFavorite} onChange={(e) => setSaveFavorite(e.target.checked)} />
              <span>Избранное</span>
            </label>
          </div>
          <div className="cvs-actions" style={{ justifyContent: "flex-start" }}>
            <button
              className="primary"
              type="button"
              disabled={!saveName.trim() || isBusy}
              onClick={saveNewPreset}
            >
              Сохранить пресет
            </button>
          </div>
        </div>
      ) : null}

      {showResolution || showCfgSteps || showNegative || showModelSampler || showSeed || showPipelineProfile || showLoras ? (
        <div style={{ marginTop: 14 }}>
          <div className="cvs-grid">
            {showResolution ? (
              <>
                <label className="cvs-field">
                  <span>Ширина</span>
                  <input
                    className="cvs-input"
                    type="number"
                    min={256}
                    max={2048}
                    value={value.width ?? ""}
                    onChange={(e) =>
                      onChange({
                        ...value,
                        width: e.target.value === "" ? null : clampNumber(Number(e.target.value), 256, 2048),
                      })
                    }
                    placeholder="по умолчанию"
                    disabled={isBusy}
                  />
                </label>
                <label className="cvs-field">
                  <span>Высота</span>
                  <input
                    className="cvs-input"
                    type="number"
                    min={256}
                    max={2048}
                    value={value.height ?? ""}
                    onChange={(e) =>
                      onChange({
                        ...value,
                        height: e.target.value === "" ? null : clampNumber(Number(e.target.value), 256, 2048),
                      })
                    }
                    placeholder="по умолчанию"
                    disabled={isBusy}
                  />
                </label>
              </>
            ) : null}

            {showCfgSteps ? (
              <>
                <label className="cvs-field">
                  <span>Шаги</span>
                  <input
                    className="cvs-input"
                    type="number"
                    min={1}
                    max={80}
                    value={value.steps ?? ""}
                    onChange={(e) =>
                      onChange({
                        ...value,
                        steps: e.target.value === "" ? null : clampNumber(Number(e.target.value), 1, 80),
                      })
                    }
                    placeholder="по умолчанию"
                    disabled={isBusy}
                  />
                </label>
                <label className="cvs-field">
                  <span>CFG</span>
                  <input
                    className="cvs-input"
                    type="number"
                    min={0.1}
                    max={20}
                    step={0.1}
                    value={value.cfg_scale ?? ""}
                    onChange={(e) =>
                      onChange({
                        ...value,
                        cfg_scale: e.target.value === "" ? null : clampNumber(Number(e.target.value), 0.1, 20),
                      })
                    }
                    placeholder="по умолчанию"
                    disabled={isBusy}
                  />
                </label>
              </>
            ) : null}

            {showSeed ? (
              <label className="cvs-field">
                <span>Seed</span>
                <input
                  className="cvs-input"
                  type="number"
                  value={value.seed ?? ""}
                  onChange={(e) =>
                    onChange({
                      ...value,
                      seed: e.target.value === "" ? null : Math.max(0, Number(e.target.value)),
                    })
                  }
                  placeholder="случайный"
                  disabled={isBusy}
                />
              </label>
            ) : null}

            {showNegative ? (
              <label className="cvs-field">
                <span>Дополнительный негативный промпт</span>
                <textarea
                  className="cvs-textarea"
                  rows={2}
                  value={value.negative_prompt ?? ""}
                  onChange={(e) => onChange({ ...value, negative_prompt: e.target.value })}
                  placeholder="необязательно"
                  disabled={isBusy}
                />
              </label>
            ) : null}
          </div>

          {showModelSampler ? (
            <div className="cvs-grid" style={{ marginTop: 8 }}>
              <label className="cvs-field">
                <span>Модель</span>
                <select
                  className="cvs-select"
                  value={value.model_id ?? ""}
                  onChange={(e) => onChange({ ...value, model_id: e.target.value || null })}
                  disabled={isBusy}
                >
                  <option value="">— по умолчанию —</option>
                  {modelOptions.map((m: any) => (
                    <option key={m.model_name ?? m.title} value={m.model_name ?? m.title}>
                      {m.title ?? m.model_name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="cvs-field">
                <span>VAE</span>
                <select
                  className="cvs-select"
                  value={value.vae_id ?? ""}
                  onChange={(e) => onChange({ ...value, vae_id: e.target.value || null })}
                  disabled={isBusy}
                >
                  <option value="">— по умолчанию —</option>
                  {vaeOptions.map((v: string) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label className="cvs-field">
                <span>Сэмплер</span>
                <select
                  className="cvs-select"
                  value={value.sampler ?? ""}
                  onChange={(e) => onChange({ ...value, sampler: e.target.value || null })}
                  disabled={isBusy}
                >
                  <option value="">— по умолчанию —</option>
                  {samplerOptions.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="cvs-field">
                <span>Планировщик</span>
                <select
                  className="cvs-select"
                  value={value.scheduler ?? ""}
                  onChange={(e) => onChange({ ...value, scheduler: e.target.value || null })}
                  disabled={isBusy}
                >
                  <option value="">— по умолчанию —</option>
                  {schedulerOptions.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : null}

          {showPipelineProfile ? (
            <div className="cvs-grid" style={{ marginTop: 8 }}>
              <label className="cvs-field">
                <span>ID профиля пайплайна</span>
                <input
                  className="cvs-input"
                  value={value.pipeline_profile_id ?? ""}
                  onChange={(e) => onChange({ ...value, pipeline_profile_id: e.target.value || null })}
                  placeholder="необязательно"
                  disabled={isBusy}
                />
              </label>
              <label className="cvs-field">
                <span>Версия профиля пайплайна</span>
                <input
                  className="cvs-input"
                  type="number"
                  value={value.pipeline_profile_version ?? ""}
                  onChange={(e) =>
                    onChange({
                      ...value,
                      pipeline_profile_version: e.target.value === "" ? null : Number(e.target.value),
                    })
                  }
                  placeholder="необязательно"
                  disabled={isBusy}
                />
              </label>
            </div>
          ) : null}

          {showLoras ? (
            <div style={{ marginTop: 10 }}>
              <div className="muted" style={{ marginBottom: 6 }}>
                LoRA (на генерацию)
              </div>
              <div className="cvs-grid">
                <label className="cvs-field">
                  <span>Добавить LoRA</span>
                  <select
                    className="cvs-select"
                    value={loraDraftName}
                    onChange={(e) => setLoraDraftName(e.target.value)}
                    disabled={isBusy}
                  >
                    <option value="">— выбрать —</option>
                    {loraOptions.map((l: any) => (
                      <option key={l.name} value={l.name}>
                        {l.alias ? `${l.alias} (${l.name})` : l.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="cvs-field">
                  <span>Вес</span>
                  <input
                    className="cvs-input"
                    type="number"
                    min={0}
                    max={2}
                    step={0.05}
                    value={loraDraftWeight}
                    onChange={(e) => setLoraDraftWeight(Number(e.target.value))}
                    disabled={isBusy}
                  />
                </label>
                <div className="cvs-field">
                  <span>&nbsp;</span>
                  <button className="secondary" type="button" onClick={addLora} disabled={!loraDraftName || isBusy}>Добавить</button>
                </div>
              </div>

              {loras.length ? (
                <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
                  {loras.map((l, idx) => (
                    <div key={`${l.name}-${idx}`} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <select
                        className="cvs-select"
                        value={l.name}
                        onChange={(e) => updateLora(idx, { name: e.target.value })}
                        disabled={isBusy}
                      >
                        {loraOptions.map((opt: any) => (
                          <option key={opt.name} value={opt.name}>
                            {opt.alias ? `${opt.alias} (${opt.name})` : opt.name}
                          </option>
                        ))}
                      </select>
                      <input
                        className="cvs-input cvs-input-small"
                        type="number"
                        min={0}
                        max={2}
                        step={0.05}
                        value={l.weight}
                        onChange={(e) => updateLora(idx, { weight: clampNumber(Number(e.target.value), 0, 2) })}
                        disabled={isBusy}
                      />
                      <button className="secondary" type="button" onClick={() => removeLora(idx)} disabled={isBusy}>Удалить</button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="muted">LoRA не выбраны.</div>
              )}
            </div>
          ) : null}

          {(createMutation.error || updateMutation.error || deleteMutation.error) ? (
            <div style={{ marginTop: 10, color: "var(--danger, #b00020)" }}>
              {(createMutation.error as any)?.message ||
                (updateMutation.error as any)?.message ||
                (deleteMutation.error as any)?.message}
            </div>
          ) : null}

          {(optionsLoading || presetsLoading) && (
            <div className="muted" style={{ marginTop: 10 }}>
              Загрузка настроек…
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
