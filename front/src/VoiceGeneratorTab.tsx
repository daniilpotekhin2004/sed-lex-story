import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getAssetUrl } from "../api/client";
import type { ProjectVoiceoverLine, SceneSlide } from "../shared/types";
import { selectApprovedAudioForSlide } from "../shared/voiceover";

type SequenceChoice = {
  id: string;
  label: string;
};

type Props = {
  slides: SceneSlide[];
  fallbackImageUrl?: string;
  choices?: SequenceChoice[];
  choicePrompt?: string;
  onChoice?: (choiceId: string) => void;
  resetKey?: string;
  showAudioControls?: boolean;
  speakerPortraits?: Record<string, string | undefined>;
  voiceoverLines?: ProjectVoiceoverLine[];
};

type DialogueEntry = {
  id: string;
  speakerId: string;
  speakerLabel: string;
  type: "speech" | "thought";
  text: string;
  dialogueIndex?: number;
  audioUrl?: string;
};

type RenderDialogueEntry = DialogueEntry & {
  side: "left" | "right";
  portraitUrl?: string;
};

const normalizeSpeakerKey = (value?: string) => {
  const speaker = (value || "").trim();
  if (!speaker) return "__unknown__";
  return speaker.toLowerCase();
};

const speakerInitials = (value?: string) => {
  const speaker = (value || "").trim();
  if (!speaker) return "??";
  const parts = speaker.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
};

export default function SequencePlayer({
  slides,
  fallbackImageUrl,
  choices,
  choicePrompt,
  onChoice,
  resetKey,
  showAudioControls = false,
  speakerPortraits,
  voiceoverLines,
}: Props) {
  const [index, setIndex] = useState(0);
  const [audioEnabled, setAudioEnabled] = useState(false);
  const [autoPlay, setAutoPlay] = useState(false);
  const [audioStatus, setAudioStatus] = useState<"idle" | "loading" | "playing" | "error">("idle");
  const [audioError, setAudioError] = useState<string | null>(null);
  const [lineAudioPlayingId, setLineAudioPlayingId] = useState<string | null>(null);
  const [lineAudioLoadingId, setLineAudioLoadingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lineAudioRef = useRef<HTMLAudioElement | null>(null);
  const playbackTokenRef = useRef(0);

  useEffect(() => {
    setIndex(0);
    setAudioStatus("idle");
    setAudioError(null);
  }, [resetKey]);

  const total = slides.length;
  const current = slides[index] ?? null;
  const imageUrl = useMemo(() => {
    return getAssetUrl(current?.image_url || fallbackImageUrl) || "";
  }, [current?.image_url, fallbackImageUrl]);
  const isLast = total > 0 && index === total - 1;

  const dialogueEntries = useMemo<DialogueEntry[]>(() => {
    if (!current) return [];
    const approvedLines = (voiceoverLines || [])
      .filter((line) => line.slide_index === index && Boolean(line.approved_audio_url))
      .sort((a, b) => a.order - b.order);
    const approvedDialogue = approvedLines.filter((line) => line.kind === "dialogue");
    const approvedThought = approvedLines.filter((line) => line.kind === "thought");
    const usedLineIds = new Set<string>();
    const normalizeText = (value: string) => value.trim().replace(/\s+/g, " ").toLowerCase();
    const claimDialogueAudio = (speaker: string, text: string, lineId: string | undefined, lineIndex: number) => {
      const speakerKey = normalizeSpeakerKey(speaker);
      const normalizedText = normalizeText(text);
      const pick = (match: (line: ProjectVoiceoverLine) => boolean) =>
        approvedDialogue.find((line) => !usedLineIds.has(line.id) && match(line));

      const byId =
        lineId && !lineId.startsWith("speech-")
          ? pick((line) => (line.dialogue_id || "").trim() === lineId)
          : undefined;
      const byIndex = pick((line) => line.dialogue_index === lineIndex);
      const byText = pick(
        (line) =>
          normalizeSpeakerKey(line.speaker || "") === speakerKey &&
          normalizeText(line.text || "") === normalizedText,
      );
      const fallback = pick(() => true);
      const found = byId || byIndex || byText || fallback;
      if (!found) return "";
      usedLineIds.add(found.id);
      return found.approved_audio_url || "";
    };

    const entries: DialogueEntry[] = [];
    (current.dialogue || []).forEach((line, lineIndex) => {
      const text = (line.text || "").trim();
      if (!text) return;
      const speakerLabel = (line.speaker || "").trim() || "Unknown";
      const speakerId = normalizeSpeakerKey(line.speaker);
      entries.push({
        id: line.id || `speech-${lineIndex}`,
        speakerId,
        speakerLabel,
        type: "speech",
        text,
        dialogueIndex: lineIndex,
        audioUrl: getAssetUrl(claimDialogueAudio(line.speaker || "", text, line.id, lineIndex)) || "",
      });
    });

    const thoughtText = (current.thought || "").trim();
    if (thoughtText) {
      const thoughtSpeaker = entries[0]?.speakerLabel || "Inner Voice";
      const thoughtSpeakerId = entries[0]?.speakerId || normalizeSpeakerKey(thoughtSpeaker);
      const thoughtEntry: DialogueEntry = {
        id: `thought-${current.id || index}`,
        speakerId: thoughtSpeakerId,
        speakerLabel: thoughtSpeaker,
        type: "thought",
        text: thoughtText,
        audioUrl: getAssetUrl(approvedThought[0]?.approved_audio_url || "") || "",
      };
      if (entries.length > 0) {
        const insertionIndex = entries.findIndex((entry) => entry.speakerId === thoughtSpeakerId);
        if (insertionIndex >= 0) entries.splice(insertionIndex + 1, 0, thoughtEntry);
        else entries.push(thoughtEntry);
      } else {
        entries.push(thoughtEntry);
      }
    }
    return entries;
  }, [current, index, voiceoverLines]);

  const renderedDialogueEntries = useMemo<RenderDialogueEntry[]>(() => {
    let previousSpeakerId = "";
    let currentSide: "left" | "right" = "left";
    return dialogueEntries.map((entry, entryIndex) => {
      if (entryIndex === 0) {
        currentSide = "left";
      } else if (entry.speakerId !== previousSpeakerId) {
        currentSide = currentSide === "left" ? "right" : "left";
      }
      previousSpeakerId = entry.speakerId;
      const portraitUrl = getAssetUrl(speakerPortraits?.[entry.speakerId] || speakerPortraits?.[entry.speakerLabel]) || undefined;
      return { ...entry, side: currentSide, portraitUrl };
    });
  }, [dialogueEntries, speakerPortraits]);

  const animation = (current?.animation || "none").toLowerCase();
  const hasExposition = Boolean(current?.exposition?.trim());
  const hasDialogues = renderedDialogueEntries.length > 0;
  const currentSlideAudioUrls = useMemo(
    () =>
      selectApprovedAudioForSlide(voiceoverLines, index)
        .map((url) => getAssetUrl(url) || "")
        .filter((url) => Boolean(url)),
    [voiceoverLines, index],
  );

  const cleanupAudio = useCallback(() => {
    playbackTokenRef.current += 1;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
  }, []);

  const stopAudio = useCallback(() => {
    cleanupAudio();
    setAudioStatus("idle");
    setAudioError(null);
  }, [cleanupAudio]);

  const cleanupLineAudio = useCallback(() => {
    if (lineAudioRef.current) {
      lineAudioRef.current.pause();
      lineAudioRef.current = null;
    }
    setLineAudioPlayingId(null);
    setLineAudioLoadingId(null);
  }, []);

  const toggleLineAudio = useCallback(
    async (entry: RenderDialogueEntry) => {
      const audioUrl = (entry.audioUrl || "").trim();
      if (!audioUrl) return;
      if (lineAudioPlayingId === entry.id) {
        cleanupLineAudio();
        return;
      }

      stopAudio();
      cleanupLineAudio();
      setLineAudioLoadingId(entry.id);

      const audio = new Audio(audioUrl);
      lineAudioRef.current = audio;

      audio.onended = () => {
        setLineAudioPlayingId(null);
        setLineAudioLoadingId(null);
        lineAudioRef.current = null;
      };
      audio.onpause = () => {
        if (audio.currentTime > 0 && !audio.ended) {
          setLineAudioPlayingId(null);
          setLineAudioLoadingId(null);
        }
      };
      audio.onerror = () => {
        setLineAudioPlayingId(null);
        setLineAudioLoadingId(null);
        lineAudioRef.current = null;
      };

      try {
        await audio.play();
        setLineAudioPlayingId(entry.id);
        setLineAudioLoadingId(null);
      } catch {
        setLineAudioPlayingId(null);
        setLineAudioLoadingId(null);
        lineAudioRef.current = null;
      }
    },
    [cleanupLineAudio, lineAudioPlayingId, stopAudio],
  );

  const playAudio = useCallback(async () => {
    if (currentSlideAudioUrls.length === 0) {
      setAudioError("Нет утверждённой озвучки для этого слайда. Подтвердите реплики в разделе озвучки проекта.");
      setAudioStatus("error");
      return;
    }

    setAudioError(null);
    setAudioStatus("loading");
    cleanupAudio();

    const token = playbackTokenRef.current;

    const playByIndex = async (queueIndex: number): Promise<void> => {
      if (token !== playbackTokenRef.current) return;
      if (queueIndex >= currentSlideAudioUrls.length) {
        setAudioStatus("idle");
        return;
      }

      const audio = new Audio(currentSlideAudioUrls[queueIndex]);
      audioRef.current = audio;

      audio.onended = () => {
        void playByIndex(queueIndex + 1);
      };
      audio.onerror = () => {
        if (token !== playbackTokenRef.current) return;
        setAudioStatus("error");
        setAudioError("Не удалось воспроизвести один из утверждённых аудиофайлов.");
      };

      try {
        await audio.play();
        if (token === playbackTokenRef.current) {
          setAudioStatus("playing");
        }
      } catch {
        if (token !== playbackTokenRef.current) return;
        setAudioStatus("error");
        setAudioError("Браузер заблокировал воспроизведение. Нажмите кнопку ещё раз.");
      }
    };

    await playByIndex(0);
  }, [cleanupAudio, currentSlideAudioUrls]);

  useEffect(() => {
    if (!showAudioControls || !audioEnabled) {
      stopAudio();
      return;
    }
    stopAudio();
    if (autoPlay && current) {
      void playAudio();
    }
  }, [audioEnabled, autoPlay, current?.id, playAudio, showAudioControls, stopAudio]);

  useEffect(() => {
    cleanupLineAudio();
  }, [cleanupLineAudio, current?.id]);

  useEffect(() => {
    return () => {
      cleanupAudio();
      cleanupLineAudio();
    };
  }, [cleanupAudio, cleanupLineAudio]);

  return (
    <div className={`sequence-player sequence-anim-${animation}`}>
      <div className="sequence-stage">
        <div className="sequence-image">
          {imageUrl ? (
            <img src={imageUrl} alt={current?.title || "Кадр сцены"} />
          ) : (
            <div className="sequence-placeholder">Изображение не выбрано</div>
          )}
        </div>
        <div className="sequence-dialogue-zone" key={`${current?.id || index}-${animation}`}>
          {current?.title?.trim() ? <div className="sequence-title">{current.title}</div> : null}
          {hasExposition ? (
            <section className="sequence-exposition-panel">
              <p>{current?.exposition}</p>
            </section>
          ) : null}
          <div className="sequence-dialogue-flow">
            {hasDialogues ? (
              renderedDialogueEntries.map((entry, entryIndex) => (
                <article
                  key={entry.id || `${entry.speakerId}-${entryIndex}`}
                  className={`sequence-dialogue-container ${entry.side} ${entry.type}`}
                >
                  <div className={`sequence-portrait ${entry.portraitUrl ? "has-image" : ""}`}>
                    {entry.portraitUrl ? (
                      <img src={entry.portraitUrl} alt={entry.speakerLabel} />
                    ) : (
                      <span>{speakerInitials(entry.speakerLabel)}</span>
                    )}
                  </div>
                  <div className="sequence-dialogue-bubble">
                    <div className="sequence-dialogue-meta">
                      <span className="sequence-speaker">{entry.speakerLabel}</span>
                      <span className="sequence-dialogue-meta-right">
                        <span
                          className={`sequence-content-indicator ${entry.type === "thought" ? "thought" : "speech"}`}
                          aria-hidden="true"
                        >
                          {entry.type === "thought" ? "🧠" : "•"}
                        </span>
                        {entry.audioUrl ? (
                          <button
                            type="button"
                            className={`sequence-line-audio-btn ${
                              lineAudioPlayingId === entry.id ? "playing" : ""
                            }`}
                            title={lineAudioPlayingId === entry.id ? "Пауза" : "Воспроизвести"}
                            aria-label={lineAudioPlayingId === entry.id ? "Пауза" : "Воспроизвести"}
                            onClick={() => void toggleLineAudio(entry)}
                          >
                            {lineAudioLoadingId === entry.id ? "…" : lineAudioPlayingId === entry.id ? "⏸" : "▶"}
                          </button>
                        ) : null}
                      </span>
                    </div>
                    <div className="sequence-dialogue-text">{entry.text}</div>
                  </div>
                </article>
              ))
            ) : (
              <div className="sequence-narrative-empty">
                {hasExposition ? "Диалога в этом кадре нет." : "Для этого кадра пока нет текста."}
              </div>
            )}
          </div>
          <div className="sequence-slide-meta">
            Слайд {total === 0 ? 0 : index + 1} из {total}
          </div>
        </div>
      </div>

      <div className="sequence-controls">
        <button
          className="ghost"
          type="button"
          disabled={index === 0}
          onClick={() => setIndex((prev) => Math.max(0, prev - 1))}
        >
          ← Назад
        </button>
        <div className="sequence-counter">{total === 0 ? "0/0" : `${index + 1}/${total}`}</div>
        <button
          className="ghost"
          type="button"
          disabled={index >= total - 1}
          onClick={() => setIndex((prev) => Math.min(total - 1, prev + 1))}
        >
          Далее →
        </button>
      </div>

      {showAudioControls && (
        <div className="sequence-audio">
          <label className="sequence-audio-toggle">
            <input
              type="checkbox"
              checked={audioEnabled}
              onChange={(event) => setAudioEnabled(event.target.checked)}
            />
            <span>Аудиорежим</span>
          </label>
          <label className="sequence-audio-toggle">
            <input
              type="checkbox"
              checked={autoPlay}
              disabled={!audioEnabled}
              onChange={(event) => setAutoPlay(event.target.checked)}
            />
            <span>Автовоспроизведение</span>
          </label>
          <button
            className="ghost"
            type="button"
            disabled={!audioEnabled || audioStatus === "loading" || currentSlideAudioUrls.length === 0}
            onClick={() => (audioStatus === "playing" ? stopAudio() : playAudio())}
          >
            {audioStatus === "loading"
              ? "Загрузка..."
              : audioStatus === "playing"
                ? "Остановить звук"
                : "Воспроизвести звук"}
          </button>
          {audioEnabled && currentSlideAudioUrls.length === 0 && !audioError && (
            <div className="sequence-audio-error">Для этого слайда ещё нет утверждённой озвучки.</div>
          )}
          {audioError && <div className="sequence-audio-error">{audioError}</div>}
        </div>
      )}

      {isLast && choices && choices.length > 0 && (
        <div className="sequence-choices">
          {choicePrompt && <div className="sequence-choices-title">{choicePrompt}</div>}
          <div className="sequence-choice-list">
            {choices.map((choice) => (
              <button key={choice.id} className="primary" type="button" onClick={() => onChoice?.(choice.id)}>
                {choice.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}




