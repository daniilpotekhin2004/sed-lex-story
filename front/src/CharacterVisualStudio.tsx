import { useMemo, useState } from "react";
import { generateFormFill } from "../api/ai";
import type { AIFieldSpec } from "../api/ai";
import "./AIFillModal.css";

const formatValue = (value: unknown) => {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const isEmptyValue = (value: unknown) => {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return value.trim().length === 0;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value as Record<string, unknown>).length === 0;
  return false;
};

const extractErrorMessage = (error: unknown) => {
  if (!error) return "Не удалось сгенерировать значения формы.";
  if (typeof error === "string") return error;
  if (typeof error === "object") {
    const maybe = error as { message?: unknown };
    if (typeof maybe.message === "string" && maybe.message.trim().length > 0) {
      return maybe.message;
    }
  }
  return "Не удалось сгенерировать значения формы.";
};

export default function AIFillModal({
  title,
  formType,
  fields,
  currentValues,
  context,
  onApply,
  onClose,
}: {
  title: string;
  formType: string;
  fields: AIFieldSpec[];
  currentValues: Record<string, unknown>;
  context?: string;
  onApply: (values: Record<string, unknown>) => void;
  onClose: () => void;
}) {
  const [extraContext, setExtraContext] = useState("");
  const [detailLevel, setDetailLevel] = useState<"narrow" | "standard" | "detailed">("standard");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<Record<string, unknown> | null>(null);
  const [proposalFieldKeys, setProposalFieldKeys] = useState<string[]>([]);

  const contextPreview = useMemo(() => context?.trim() || "", [context]);
  const fillableFields = useMemo(
    () => fields.filter((field) => isEmptyValue(currentValues[field.key])),
    [fields, currentValues],
  );
  const generationFields = useMemo(
    () => (fillableFields.length > 0 ? fillableFields : fields),
    [fields, fillableFields],
  );
  const generationFieldKeys = useMemo(
    () => generationFields.map((field) => field.key),
    [generationFields],
  );
  const applyKeys = useMemo(
    () => new Set(proposalFieldKeys.length > 0 ? proposalFieldKeys : generationFieldKeys),
    [generationFieldKeys, proposalFieldKeys],
  );
  const proposalFields = useMemo(() => {
    const keys = proposalFieldKeys.length > 0 ? new Set(proposalFieldKeys) : new Set(generationFieldKeys);
    return fields.filter((field) => keys.has(field.key));
  }, [fields, generationFieldKeys, proposalFieldKeys]);
  const generatesOnlyEmpty = fillableFields.length > 0;

  const handleGenerate = async () => {
    if (generationFields.length === 0) {
      setError("Нет полей для AI-заполнения. Проверьте конфигурацию формы.");
      setProposal(null);
      setProposalFieldKeys([]);
      return;
    }
    setLoading(true);
    setError(null);
    setProposal(null);
    setProposalFieldKeys([]);
    try {
      const response = await generateFormFill({
        form_type: formType,
        fields: generationFields,
        current_values: currentValues,
        context: contextPreview,
        extra_context: extraContext.trim() || undefined,
        detail_level: detailLevel,
        fill_only_empty: generatesOnlyEmpty,
      });
      const values = response.values || {};
      if (!Object.keys(values).length) {
        setError("AI вернул пустой ответ. Уточните контекст и попробуйте снова.");
      }
      setProposal(values);
      setProposalFieldKeys(generationFieldKeys);
    } catch (err: unknown) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleApply = () => {
    if (!proposal) return;
    const filtered = Object.fromEntries(
      Object.entries(proposal).filter(([key]) => applyKeys.has(key)),
    );
    onApply(filtered);
    onClose();
  };

  return (
    <div className="ai-fill-overlay" onClick={onClose}>
      <div className="ai-fill-modal" onClick={(event) => event.stopPropagation()}>
        <div className="ai-fill-header">
          <div>
            <div className="ai-fill-kicker">AI заполнение</div>
            <h2>{title}</h2>
            <p className="muted">
              {generatesOnlyEmpty
                ? "Заполняются только пустые поля на основе контекста и подсказок."
                : "Пустых полей нет: генерация выполнится для всех полей формы (перезапись значений)."}
            </p>
          </div>
          <button className="ai-fill-close" onClick={onClose}>
            x
          </button>
        </div>

        <div className="ai-fill-body">
          {contextPreview && (
            <details className="ai-fill-context">
              <summary>Автоконтекст</summary>
              <pre>{contextPreview}</pre>
            </details>
          )}
          <label className="ai-fill-field">
            <span>Дополнительный контекст</span>
            <textarea
              rows={4}
              value={extraContext}
              onChange={(event) => setExtraContext(event.target.value)}
              placeholder="Дополнительные ограничения, тон, факты или правовой контекст"
            />
          </label>
          <label className="ai-fill-field">
            <span>Уровень детализации</span>
            <select
              value={detailLevel}
              onChange={(event) =>
                setDetailLevel(event.target.value as "narrow" | "standard" | "detailed")
              }
            >
              <option value="narrow">Кратко</option>
              <option value="standard">Стандартно</option>
              <option value="detailed">Подробно</option>
            </select>
          </label>

          <div className="ai-fill-actions">
            <button
              className="ai-fill-generate"
              type="button"
              onClick={handleGenerate}
              disabled={loading}
            >
              {loading ? "Генерация..." : "Генерировать"}
            </button>
            <button className="secondary" type="button" onClick={handleApply} disabled={!proposal}>
              Применить
            </button>
          </div>

          {error && <div className="ai-fill-error">{error}</div>}

          {proposal && (
            <div className="ai-fill-proposal">
              <h3>Предложенные значения</h3>
              <div className="ai-fill-proposal-grid">
                {proposalFields.map((field) => (
                  <div key={field.key} className="ai-fill-proposal-card">
                    <strong>{field.label || field.key}</strong>
                    <pre>{formatValue(proposal[field.key])}</pre>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
