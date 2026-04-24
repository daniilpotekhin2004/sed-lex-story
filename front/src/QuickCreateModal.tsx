import { useEffect, useState } from "react";
import { analyzePrompt, type PromptAnalysis } from "../api/generation";

type Props = {
  prompt: string;
  showTranslation?: boolean;
  debounceMs?: number;
};

/**
 * Component that analyzes a prompt and shows a warning if it contains
 * too many non-English words (>10).
 */
export default function PromptWarning({ prompt, showTranslation = true, debounceMs = 500 }: Props) {
  const [analysis, setAnalysis] = useState<PromptAnalysis | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!prompt || prompt.length < 5) {
      setAnalysis(null);
      return;
    }

    // Check if prompt contains non-ASCII characters (quick local check)
    const hasNonAscii = /[^\x00-\x7F]/.test(prompt);
    if (!hasNonAscii) {
      setAnalysis(null);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const result = await analyzePrompt(prompt);
        setAnalysis(result);
      } catch (error) {
        console.error("Failed to analyze prompt", error);
        setAnalysis(null);
      } finally {
        setLoading(false);
      }
    }, debounceMs);

    return () => clearTimeout(timer);
  }, [prompt, debounceMs]);

  if (loading) {
    return (
      <div className="prompt-warning prompt-warning-loading">
        <span className="prompt-warning-icon">⏳</span>
        <span>Анализ промпта...</span>
      </div>
    );
  }

  if (!analysis) {
    return null;
  }

  // Show warning if more than 10 non-English words
  if (analysis.warning) {
    return (
      <div className="prompt-warning prompt-warning-warn">
        <span className="prompt-warning-icon">⚠️</span>
        <div className="prompt-warning-content">
          <div className="prompt-warning-text">{analysis.warning}</div>
          {showTranslation && analysis.translation_changed && (
            <div className="prompt-warning-translation">
              <strong>Предпросмотр перевода:</strong>
              <span>{analysis.translated}</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Show info if translation happened
  if (analysis.translation_changed && showTranslation) {
    return (
      <div className="prompt-warning prompt-warning-info">
        <span className="prompt-warning-icon">🌐</span>
        <div className="prompt-warning-content">
          <div className="prompt-warning-text">
            Промпт будет переведён (неанглийских слов: {analysis.non_english_count})
          </div>
          <div className="prompt-warning-translation">
            <strong>→</strong>
            <span>{analysis.translated}</span>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
