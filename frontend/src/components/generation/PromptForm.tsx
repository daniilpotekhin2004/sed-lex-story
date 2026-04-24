import React, { useState } from "react";

type Props = {
  disabled?: boolean;
  onSubmit: (prompt: string) => void;
  initialPrompt?: string;
  initialNegative?: string;
  onNegativeChange?: (value: string) => void;
};

export const PromptForm: React.FC<Props> = ({
  disabled,
  onSubmit,
  initialPrompt,
  initialNegative,
  onNegativeChange,
}) => {
  const [prompt, setPrompt] = useState(initialPrompt ?? "");
  const [negative, setNegative] = useState(initialNegative ?? "");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    onSubmit(prompt.trim());
  };

  return (
    <form className="card" onSubmit={handleSubmit}>
      <div className="card-header">
        <h2>Промпт</h2>
        <span className="muted">Опишите сцену или идею</span>
      </div>
      <textarea
        className="input"
        placeholder="Например: Подросток обсуждает права потребителей в школьном клубе"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={5}
        disabled={disabled}
      />
      <label className="field">
        <span>Негативный промпт (необязательно)</span>
        <textarea
          className="input"
          placeholder="Нежелательные детали"
          value={negative}
          onChange={(e) => {
            setNegative(e.target.value);
            onNegativeChange?.(e.target.value);
          }}
          rows={3}
          disabled={disabled}
        />
      </label>
      <div className="actions">
        <button className="primary" type="submit" disabled={disabled || !prompt.trim()}>
          {disabled ? "Генерируем..." : "Сгенерировать"}
        </button>
      </div>
    </form>
  );
};
