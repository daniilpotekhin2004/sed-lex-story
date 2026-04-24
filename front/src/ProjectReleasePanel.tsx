import React from "react";
import type { PresetList } from "../../shared/types";

export type SettingsState = {
  style?: string;
  num_variants: number;
  width: number;
  height: number;
  cfg_scale: number;
  steps: number;
  character_preset?: string | null;
  lora_preset?: string | null;
  negativePrompt?: string | null;
};

type Props = {
  value: SettingsState;
  onChange: (next: SettingsState) => void;
  disabled?: boolean;
  presets?: PresetList;
  loadingPresets?: boolean;
};

export const SettingsPanel: React.FC<Props> = ({
  value,
  onChange,
  disabled,
  presets,
  loadingPresets,
}) => {
  const setField = <K extends keyof SettingsState>(key: K, val: SettingsState[K]) =>
    onChange({ ...value, [key]: val });

  return (
    <div className="card">
      <div className="card-header">
        <h2>Параметры</h2>
        <span className="muted">Шаги/размер/варианты для Stable Diffusion</span>
      </div>
      <div className="field">
        <label>Стиль</label>
        <input
          className="input"
          placeholder="comic / realistic / watercolor..."
          value={value.style ?? ""}
          onChange={(e) => setField("style", e.target.value)}
          disabled={disabled}
        />
      </div>
      <div className="field two-cols">
        <div>
          <label>CFG Scale</label>
          <input
            className="input"
            type="number"
            min={1}
            max={30}
            step={0.5}
            value={value.cfg_scale}
            onChange={(e) => setField("cfg_scale", Number(e.target.value))}
            disabled={disabled}
          />
        </div>
        <div>
          <label>Шаги</label>
          <input
            className="input"
            type="number"
            min={5}
            max={100}
            value={value.steps}
            onChange={(e) => setField("steps", Number(e.target.value))}
            disabled={disabled}
          />
        </div>
      </div>
      <div className="field two-cols">
        <div>
          <label>Количество вариантов</label>
          <input
            className="input"
            type="number"
            min={1}
            max={8}
            value={value.num_variants}
            onChange={(e) => setField("num_variants", Number(e.target.value))}
            disabled={disabled}
          />
        </div>
        <div>
          <label>Размер</label>
          <div className="size-inputs">
            <input
              className="input"
              type="number"
              min={256}
              max={1024}
              value={value.width}
              onChange={(e) => setField("width", Number(e.target.value))}
              disabled={disabled}
            />
            <span className="muted">×</span>
            <input
              className="input"
              type="number"
              min={256}
              max={1024}
              value={value.height}
              onChange={(e) => setField("height", Number(e.target.value))}
              disabled={disabled}
            />
          </div>
        </div>
      </div>
      <div className="field two-cols">
        <div>
          <label>Персонаж</label>
          <select
            className="input"
            value={value.character_preset ?? ""}
            onChange={(e) => setField("character_preset", e.target.value || null)}
            disabled={disabled || loadingPresets}
          >
            <option value="">Не выбрано</option>
            {presets?.characters.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          {value.character_preset && (
            <small className="muted">
              {presets?.characters.find((c) => c.id === value.character_preset)?.description}
            </small>
          )}
        </div>
        <div>
          <label>LoRA</label>
          <select
            className="input"
            value={value.lora_preset ?? ""}
            onChange={(e) => setField("lora_preset", e.target.value || null)}
            disabled={disabled || loadingPresets}
          >
            <option value="">Не выбрано</option>
            {presets?.loras.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
          {value.lora_preset && (
            <small className="muted">
              {presets?.loras.find((l) => l.id === value.lora_preset)?.description}
            </small>
          )}
        </div>
      </div>
    </div>
  );
};
