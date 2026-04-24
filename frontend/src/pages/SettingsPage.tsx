import React, { useEffect, useState } from "react";
import { API_BASE_URL } from "../api/client";
import { sendTelemetry } from "../api/telemetry";
import { getAuthStorageBackend } from "../auth/sessionStore";
import { useTheme } from "../theme/ThemeProvider";
import {
  getComfyApiKey,
  getComfyApiUrl,
  getGenerationEnvironment,
  getPoeApiKey,
  getPoeApiUrl,
  getPoeModel,
  setComfyApiKey,
  setComfyApiUrl,
  setGenerationEnvironment,
  setPoeApiKey,
  setPoeApiUrl,
  setPoeModel,
  type GenerationEnvironment,
} from "../utils/generationEnvironment";
import { getRuntimePlatform, isNativeShell } from "../utils/runtimePlatform";
import { clearBufferedEvents, getBufferedEvents, toApiPayloads } from "../utils/tracker";

export const SettingsPage: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const [events, setEvents] = useState(getBufferedEvents());
  const [sending, setSending] = useState(false);
  const [generationEnv, setGenerationEnvState] = useState<GenerationEnvironment>(getGenerationEnvironment());
  const [comfyApiKey, setComfyApiKeyState] = useState(getComfyApiKey());
  const [comfyApiUrl, setComfyApiUrlState] = useState(getComfyApiUrl());
  const [poeApiKey, setPoeApiKeyState] = useState(getPoeApiKey());
  const [poeApiUrl, setPoeApiUrlState] = useState(getPoeApiUrl());
  const [poeModel, setPoeModelState] = useState(getPoeModel());
  const runtimePlatform = getRuntimePlatform();
  const authStorageBackend = getAuthStorageBackend();

  useEffect(() => {
    setEvents(getBufferedEvents());
  }, []);

  async function flushTelemetry() {
    const payloads = toApiPayloads();
    if (payloads.length === 0) return;
    try {
      setSending(true);
      await sendTelemetry(payloads);
      clearBufferedEvents();
      setEvents([]);
    } catch (error) {
      console.error("Failed to send telemetry", error);
    } finally {
      setSending(false);
    }
  }

  function handleGenerationEnvChange(next: GenerationEnvironment) {
    setGenerationEnvironment(next);
    setGenerationEnvState(next);
  }

  function handleComfyApiKeyChange(value: string) {
    setComfyApiKeyState(value);
    setComfyApiKey(value);
  }

  function handleComfyApiUrlChange(value: string) {
    setComfyApiUrlState(value);
    setComfyApiUrl(value);
  }

  function handlePoeApiKeyChange(value: string) {
    setPoeApiKeyState(value);
    setPoeApiKey(value);
  }

  function handlePoeApiUrlChange(value: string) {
    setPoeApiUrlState(value);
    setPoeApiUrl(value);
  }

  function handlePoeModelChange(value: string) {
    setPoeModelState(value);
    setPoeModel(value);
  }

  return (
    <div className="stack">
      <section className="card">
        <div className="card-header">
          <h2>Системные настройки</h2>
          <span className="muted">Служебные параметры фронтенда</span>
        </div>

        <div className="field">
          <span>База API</span>
          <code>{API_BASE_URL}</code>
        </div>

        <div className="field">
          <span>Среда выполнения</span>
          <code>{isNativeShell() ? `native (${runtimePlatform})` : `web (${runtimePlatform})`}</code>
        </div>

        <div className="field">
          <span>Хранилище сессии</span>
          <code>{authStorageBackend}</code>
        </div>

        <div className="field">
          <span>Тема</span>
          <div className="actions">
            <code>{theme}</code>
            <button className="secondary" type="button" onClick={toggleTheme}>
              Переключить
            </button>
          </div>
        </div>

        <label className="field">
          <span>Среда генерации</span>
          <select
            className="input"
            value={generationEnv}
            onChange={(event) => handleGenerationEnvChange(event.target.value as GenerationEnvironment)}
          >
            <option value="local">Локально</option>
            <option value="comfy_api">ComfyUI API</option>
            <option value="poe_api">Poe Image (быстро)</option>
          </select>
          <small className="muted">Эта настройка убрана с пользовательских экранов и влияет на новые генерации.</small>
        </label>

        {generationEnv === "comfy_api" ? (
          <>
            <label className="field">
              <span>Ключ API ComfyUI</span>
              <input
                className="input"
                type="password"
                value={comfyApiKey}
                onChange={(event) => handleComfyApiKeyChange(event.target.value)}
                placeholder="comfyui-..."
              />
              <small className="muted">Хранится только в браузере.</small>
            </label>

            <label className="field">
              <span>Базовый URL API ComfyUI</span>
              <input
                className="input"
                value={comfyApiUrl}
                onChange={(event) => handleComfyApiUrlChange(event.target.value)}
                placeholder="https://cloud.comfy.org/api"
              />
              <small className="muted">Оставьте поле пустым, чтобы использовать backend default.</small>
            </label>
          </>
        ) : null}

        {generationEnv === "poe_api" ? (
          <>
            <label className="field">
              <span>Ключ API Poe</span>
              <input
                className="input"
                type="password"
                value={poeApiKey}
                onChange={(event) => handlePoeApiKeyChange(event.target.value)}
                placeholder="poe-..."
              />
              <small className="muted">Хранится только в браузере.</small>
            </label>

            <label className="field">
              <span>Базовый URL API Poe</span>
              <input
                className="input"
                value={poeApiUrl}
                onChange={(event) => handlePoeApiUrlChange(event.target.value)}
                placeholder="https://api.poe.com/v1"
              />
            </label>

            <label className="field">
              <span>Модель Poe</span>
              <input
                className="input"
                value={poeModel}
                onChange={(event) => handlePoeModelChange(event.target.value)}
                placeholder="GPT-Image-1"
              />
              <small className="muted">По умолчанию backend использует свою модель, если поле пустое.</small>
            </label>
          </>
        ) : null}
      </section>

      <section className="card">
        <div className="card-header">
          <h3>Буфер телеметрии</h3>
          <div className="actions">
            <button className="secondary" type="button" onClick={() => setEvents(getBufferedEvents())}>
              Обновить
            </button>
            <button
              className="secondary"
              type="button"
              onClick={() => {
                clearBufferedEvents();
                setEvents([]);
              }}
            >
              Очистить
            </button>
            <button className="primary" type="button" disabled={sending || events.length === 0} onClick={flushTelemetry}>
              {sending ? "Отправка..." : "Отправить"}
            </button>
          </div>
        </div>

        {events.length === 0 ? (
          <p className="muted">В буфере нет событий.</p>
        ) : (
          <div className="wizard-json">
            {events.map((ev, idx) => (
              <div key={`${ev.ts}-${idx}`} className="field" style={{ marginBottom: 16 }}>
                <div className="muted">{new Date(ev.ts).toISOString()}</div>
                <strong>{ev.name}</strong>
                {ev.payload && Object.keys(ev.payload).length > 0 ? (
                  <pre style={{ margin: 0 }}>{JSON.stringify(ev.payload, null, 2)}</pre>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};
