import { useVoiceGeneration } from '../hooks/useAsyncGeneration';
import { GenerationButton, GenerationStatus } from './GenerationStatus';
import React, { useState, useEffect, useRef } from 'react';
import './VoiceGeneratorTab.css';
import { apiClient } from '../api/client';

interface VoiceModel {
  id: string;
  name: string;
  info: string;
  type: string;
  quality: string;
  supports_voice_design?: boolean;
  available_locally?: boolean;
}

interface VoicePreset {
  name: string;
  description: string;
  speed?: number;
  pitch?: number;
  emotion?: string;
  type?: string;
  instruct?: string;
  language?: string;
}

interface GenerationHistory {
  text: string;
  voice_prompt: string;
  model_id: string;
  preset: string;
  timestamp: string;
  audio_filename: string;
  audio_url: string;
  duration_estimate: number;
}

interface VoiceGeneratorStatus {
  available: boolean;
  qwen_tts_available?: boolean;
  legacy_tts_available?: boolean;
  models_count: number;
  models: VoiceModel[];
  presets: Record<string, VoicePreset>;
  recent_generations: number;
  output_directory: string;
  qwen_status?: any;
}

interface GenerationProgress {
  step: number;
  totalSteps: number;
  currentStep: string;
  progress: number;
  status: 'idle' | 'preparing' | 'processing' | 'finalizing' | 'complete' | 'error';
  message: string;
  startTime?: number;
  estimatedTime?: number;
}

const EMPTY_STATUS: VoiceGeneratorStatus = {
  available: false,
  models_count: 0,
  models: [],
  presets: {},
  recent_generations: 0,
  output_directory: ""
};

const VoiceGeneratorTab: React.FC = () => {
  const [status, setStatus] = useState<VoiceGeneratorStatus>(EMPTY_STATUS);
  const [statusLoading, setStatusLoading] = useState(false);
  // Non-blocking voice generation
  const voiceGeneration = useVoiceGeneration();
  
  // Root cause: Synchronous voice generation blocks UI
  // Fix: Use async generation with local loading state
  const handleVoiceGeneration = () => {
    if (!text.trim()) return;
    
    const payload = {
      text: text.trim(),
      voice_profile: selectedVoiceProfile,
      language: voiceLanguage
    };
    
    if (generationMode === 'voice_design' && voiceInstruct.trim()) {
      payload.instruct = voiceInstruct;
    }
    
    voiceGeneration.generateAsync(payload);
  };
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState('');
  const [voicePrompt, setVoicePrompt] = useState('');
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [selectedPreset, setSelectedPreset] = useState<string>('');
  const [customSpeed, setCustomSpeed] = useState<number>(1.0);
  const [customPitch, setCustomPitch] = useState<number>(0.0);
  const [history, setHistory] = useState<GenerationHistory[]>([]);
  const [currentAudio, setCurrentAudio] = useState<string>('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showVoiceDesign, setShowVoiceDesign] = useState(false);
  const [voiceInstruct, setVoiceInstruct] = useState('');
  const [voiceLanguage, setVoiceLanguage] = useState('English');
  const [generationMode, setGenerationMode] = useState<'standard' | 'voice_design'>('standard');
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [progress, setProgress] = useState<GenerationProgress>({
    step: 0,
    totalSteps: 5,
    currentStep: 'Готово',
    progress: 0,
    status: 'idle',
    message: 'Готово к генерации голоса'
  });
  
  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    fetchStatus();
    fetchHistory();
    
    return () => {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
      }
    };
  }, []);

  const showMessage = (type: 'success' | 'error' | 'info', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const updateProgress = (step: number, currentStep: string, progress: number, status: GenerationProgress['status'], message: string) => {
    setProgress(prev => ({
      ...prev,
      step,
      currentStep,
      progress,
      status,
      message,
      estimatedTime: prev.startTime ? Date.now() - prev.startTime : undefined
    }));
  };

  const simulateProgress = () => {
    const steps = [
      { step: 1, name: 'Подготовка текста', duration: 500 },
      { step: 2, name: 'Загрузка модели голоса', duration: 1000 },
      { step: 3, name: 'Обработка описания голоса', duration: 800 },
      { step: 4, name: 'Генерация аудио', duration: 3000 },
      { step: 5, name: 'Завершение результата', duration: 500 }
    ];

    let currentStepIndex = 0;
    
    const runStep = () => {
      if (currentStepIndex >= steps.length) {
        updateProgress(5, 'Завершено', 100, 'complete', 'Генерация голоса успешно завершена');
        return;
      }

      const step = steps[currentStepIndex];
      updateProgress(
        step.step, 
        step.name, 
        (step.step / steps.length) * 100, 
        'processing', 
        `${step.name}...`
      );

      setTimeout(() => {
        currentStepIndex++;
        runStep();
      }, step.duration);
    };

    runStep();
  };

  const fetchStatus = async () => {
    setStatusLoading(true);
    try {
      const response = await apiClient.get('/v1/voice/status');
      const payload = response.data;

      const models = Array.isArray(payload?.models) ? payload.models : [];
      const presets = payload?.presets && typeof payload.presets === 'object' ? payload.presets : {};
      const nextStatus: VoiceGeneratorStatus = {
        available: Boolean(payload?.available),
        models_count: Number(payload?.models_count ?? models.length ?? 0),
        models,
        presets,
        recent_generations: Number(payload?.recent_generations ?? 0),
        output_directory: typeof payload?.output_directory === 'string' ? payload.output_directory : ""
      };

      setStatus(nextStatus);

      if (models.length > 0) {
        setSelectedModel(models[0].id);
        
        // Check if Qwen TTS is available and set voice design mode
        const hasVoiceDesign = models.some(m => m.supports_voice_design);
        if (hasVoiceDesign && payload?.qwen_tts_available) {
          setGenerationMode('voice_design');
          setShowVoiceDesign(true);
        }
      }
    } catch (error) {
      console.error('Failed to fetch voice generator status:', error);
      showMessage('error', 'Не удалось загрузить генератор голоса');
      setStatus(EMPTY_STATUS);
    } finally {
      setStatusLoading(false);
    }
  };

  const fetchHistory = async () => {
    try {
      const response = await apiClient.get('/v1/voice/history?limit=10');
      setHistory(Array.isArray(response.data?.history) ? response.data.history : []);
    } catch (error) {
      console.error('Failed to fetch history:', error);
    }
  };

  const generateVoice = async () => {
    if (!text.trim()) {
      showMessage('info', 'Введите текст для генерации голоса');
      return;
    }

    setLoading(true);
    setProgress({
      step: 0,
      totalSteps: 5,
      currentStep: 'Старт',
      progress: 0,
      status: 'preparing',
      message: 'Инициализация генерации голоса...',
      startTime: Date.now()
    });

    // Start progress simulation
    simulateProgress();

    try {
      let endpoint = '/v1/voice/generate';
      let requestBody: any = {
        text: text,
        voice_prompt: voicePrompt || undefined,
        model_id: selectedModel || undefined,
        preset: selectedPreset || undefined,
        custom_settings: showAdvanced ? {
          speed: customSpeed,
          pitch: customPitch
        } : undefined
      };

      // Use voice design endpoint if in voice design mode
      if (generationMode === 'voice_design' && voiceInstruct.trim()) {
        endpoint = '/v1/voice/voice-design';
        requestBody = {
          text: text,
          instruct: voiceInstruct,
          language: voiceLanguage,
          model_id: selectedModel || 'voice_design_1.7b'
        };
      }

      const response = await apiClient.post(endpoint, requestBody);
      const data = response.data;
      
      if (data.success && data.audio_url) {
        setCurrentAudio(data.audio_url);
        showMessage('success', 'Голос успешно сгенерирован!');
        updateProgress(5, 'Завершено', 100, 'complete', 'Генерация голоса успешно завершена');
        fetchHistory(); // Refresh history
      } else {
        updateProgress(0, 'Ошибка', 0, 'error', data.message || 'Генерация голоса не удалась');
        showMessage('error', data.message || 'Генерация голоса не удалась');
      }
    } catch (error) {
      console.error('Voice generation error:', error);
      updateProgress(0, 'Ошибка', 0, 'error', 'Не удалось сгенерировать голос');
      showMessage('error', 'Не удалось сгенерировать голос');
    } finally {
      setLoading(false);
    }
  };

  const deleteGeneration = async (filename: string) => {
    try {
      const response = await fetch(`/v1/voice/history/${filename}`, {
        method: 'DELETE'
      });
      
      if (response.ok) {
        showMessage('success', 'Генерация удалена');
        fetchHistory();
      } else {
        showMessage('error', 'Не удалось удалить генерацию');
      }
    } catch (error) {
      console.error('Delete error:', error);
      showMessage('error', 'Не удалось удалить генерацию');
    }
  };

  const loadFromHistory = (item: GenerationHistory) => {
    setText(item.text);
    setVoicePrompt(item.voice_prompt || '');
    if (item.preset) {
      setSelectedPreset(item.preset);
    }
    setCurrentAudio(item.audio_url);
  };

  const sampleTexts = [
    "Welcome to the world of interactive storytelling.",
    "The ancient castle stood majestically against the stormy sky.",
    "Hello there! I'm excited to help you on your adventure.",
    "In a land far, far away, magic still flows through the air.",
    "The wise old sage spoke in a voice weathered by time."
  ];

  const sampleVoiceInstructs = [
    "Speak in a clear, professional narrator voice with steady pace and neutral tone, suitable for audiobooks and documentaries.",
    "Use a warm, friendly tone that's approachable and conversational, perfect for dialogue and character voices.",
    "Speak with a higher-pitched, energetic voice with playful intonation that sounds youthful and enthusiastic.",
    "Use a deeper, slower voice that conveys wisdom and experience, with measured pacing and gravitas.",
    "Speak with an energetic, enthusiastic voice with dynamic intonation, perfect for announcements and presentations.",
    "Use a mysterious, whispering voice with dramatic pauses and subtle emphasis on key words.",
    "Speak in a confident, authoritative tone with clear articulation, suitable for business presentations.",
    "Use a gentle, soothing voice with soft intonation, perfect for bedtime stories or meditation guides."
  ];

  const voiceLanguages = [
    { value: 'English', label: 'Английский' },
    { value: 'Chinese', label: 'Китайский' },
    { value: 'Japanese', label: 'Японский' },
    { value: 'Korean', label: 'Корейский' },
    { value: 'German', label: 'Немецкий' },
    { value: 'French', label: 'Французский' },
    { value: 'Russian', label: 'Русский' },
    { value: 'Portuguese', label: 'Португальский' },
    { value: 'Spanish', label: 'Испанский' },
    { value: 'Italian', label: 'Итальянский' }
  ];

  const formatTime = (ms: number) => {
    const seconds = Math.floor(ms / 1000);
    return `${seconds}с`;
  };

  return (
    <div className="voice-generator">
      {statusLoading && (
        <div className="message info">
          Загрузка профиля генератора голоса...
        </div>
      )}
      {!status.available && !statusLoading && (
        <div className="message error">
          Генератор голоса недоступен. Модели TTS не найдены в: {status.output_directory || 'неизвестно'}{' '}
          <button className="ghost small" onClick={fetchStatus}>Повторить</button>
        </div>
      )}
      {message && (
        <div className={`message ${message.type}`}>
          {message.text}
        </div>
      )}
      
      <div className="voice-generator-header">
        <h1>Генератор голоса</h1>
        <div className="voice-generator-stats">
          <span className="stat">
            <strong>{status.models_count}</strong> Моделей
          </span>
          <span className="stat">
            <strong>{Object.keys(status.presets).length}</strong> Пресетов
          </span>
          {status.qwen_tts_available && (
            <span className="stat qwen-available">
              <strong>✨ Qwen TTS</strong> доступно
            </span>
          )}
        </div>
      </div>

      {/* Generation Mode Selector */}
      {status.qwen_tts_available && (
        <div className="generation-mode-selector">
          <div className="mode-tabs">
            <button
              className={`mode-tab ${generationMode === 'standard' ? 'active' : ''}`}
              onClick={() => setGenerationMode('standard')}
            >
              🎤 Стандартная генерация
            </button>
            <button
              className={`mode-tab ${generationMode === 'voice_design' ? 'active' : ''}`}
              onClick={() => setGenerationMode('voice_design')}
            >
              ✨ Дизайн голоса (Qwen)
            </button>
          </div>
          <div className="mode-description">
            {generationMode === 'standard' ? (
              <p>Используйте классический TTS с промптами и пресетами голоса</p>
            ) : (
              <p>Создавайте кастомные голоса с детальными инструкциями через Qwen TTS AI</p>
            )}
          </div>
        </div>
      )}

      {/* Progress Status Bar */}
      {(loading || progress.status !== 'idle') && (
        <div className="progress-status-bar">
          <div className="progress-header">
            <h3>Прогресс генерации</h3>
            <div className="progress-info">
              <span className="progress-step">Шаг {progress.step}/{progress.totalSteps}</span>
              {progress.estimatedTime && (
                <span className="progress-time">
                  прошло {formatTime(progress.estimatedTime)}
                </span>
              )}
            </div>
          </div>
          
          <div className="progress-content">
            <div className="progress-bar-container">
              <div 
                className={`progress-bar ${progress.status}`}
                style={{ width: `${progress.progress}%` }}
              ></div>
            </div>
            
            <div className="progress-details">
              <div className="current-step">
                <span className={`status-icon ${progress.status}`}>
                  {progress.status === 'processing' && '⚙️'}
                  {progress.status === 'complete' && '✅'}
                  {progress.status === 'error' && '❌'}
                  {progress.status === 'preparing' && '🔄'}
                </span>
                <span className="step-name">{progress.currentStep}</span>
              </div>
              <div className="progress-message">{progress.message}</div>
            </div>
          </div>
        </div>
      )}

      <div className="voice-generator-layout">
        {/* Main Generation Panel */}
        <div className="voice-generator-main">
          <div className="card">
            <div className="card-header">
              <h2>Генерация голоса</h2>
            </div>
            
            {/* Quick Sample Texts */}
            <div className="form-group">
              <label>Быстрые примеры текста:</label>
              <div className="sample-buttons">
                {sampleTexts.map((sample, index) => (
                  <button
                    key={index}
                    className="ghost small"
                    onClick={() => setText(sample)}
                    title={sample}
                  >
                    "{sample.substring(0, 30)}..."
                  </button>
                ))}
              </div>
            </div>

            {/* Text Input */}
            <div className="form-group">
              <label htmlFor="voice-text">Текст для генерации:</label>
              <textarea
                id="voice-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Введите текст, который нужно превратить в речь..."
                rows={4}
                maxLength={1000}
                className="primary-input"
              />
              <small>{text.length}/1000 символов</small>
            </div>

            {/* Voice Prompt Input - Standard Mode */}
            {generationMode === 'standard' && (
              <div className="form-group">
                <label htmlFor="voice-prompt">Описание голоса (необязательно):</label>
                <div className="voice-prompt-section">
                  <textarea
                    id="voice-prompt"
                    value={voicePrompt}
                    onChange={(e) => setVoicePrompt(e.target.value)}
                    placeholder="Опишите характеристики голоса: тон, акцент, эмоции, стиль..."
                    rows={3}
                    maxLength={500}
                    className="secondary-input"
                  />
                  <small>{voicePrompt.length}/500 символов</small>
                </div>
              </div>
            )}

            {/* Voice Design Section - Voice Design Mode */}
            {generationMode === 'voice_design' && (
              <div className="voice-design-section">
                <div className="form-group">
                  <label htmlFor="voice-instruct">Инструкции по дизайну голоса:</label>
                  <div className="voice-instruct-section">
                    <textarea
                      id="voice-instruct"
                      value={voiceInstruct}
                      onChange={(e) => setVoiceInstruct(e.target.value)}
                      placeholder="Дайте подробные инструкции для характеристик голоса: тон, темп, эмоции, стиль, акцент и т.д. Опишите, каким должен звучать голос."
                      rows={4}
                      maxLength={1000}
                      className="primary-input voice-design-input"
                    />
                    <small>{voiceInstruct.length}/1000 символов</small>
                    
                    <div className="instruct-samples">
                      <label>Примеры дизайна голоса:</label>
                      <div className="sample-buttons">
                        {sampleVoiceInstructs.map((sample, index) => (
                          <button
                            key={index}
                            className="ghost small"
                            onClick={() => setVoiceInstruct(sample)}
                            title={sample}
                          >
                            {sample.substring(0, 40)}...
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="voice-language">Язык:</label>
                  <select
                    id="voice-language"
                    value={voiceLanguage}
                    onChange={(e) => setVoiceLanguage(e.target.value)}
                    className="language-selector"
                  >
                    {voiceLanguages.map((lang) => (
                      <option key={lang.value} value={lang.value}>
                        {lang.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {/* Model and Preset Selection */}
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="voice-model">Модель голоса:</label>
                <select
                  id="voice-model"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                >
                  {status.models.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name} ({model.quality})
                      {model.supports_voice_design && ' ✨'}
                      {!model.available_locally && ' 🌐'}
                    </option>
                  ))}
                </select>
                <small>
                  ✨ = поддержка дизайна голоса, 🌐 = удалённая модель
                </small>
              </div>
              
              {generationMode === 'standard' && (
                <div className="form-group">
                  <label htmlFor="voice-preset">Пресет голоса:</label>
                  <select
                    id="voice-preset"
                    value={selectedPreset}
                    onChange={(e) => setSelectedPreset(e.target.value)}
                  >
                    <option value="">Выберите пресет</option>
                    {Object.entries(status.presets).map(([key, preset]) => (
                      <option key={key} value={key}>
                        {preset.name}
                        {preset.type === 'qwen_voice_design' && ' ✨'}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Advanced Settings - Standard Mode Only */}
            {generationMode === 'standard' && (
              <div className="form-group">
                <button
                  type="button"
                  className="ghost"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                >
                  {showAdvanced ? '▼' : '▶'} Расширенные настройки
                </button>
                
                {showAdvanced && (
                  <div className="advanced-settings">
                    <div className="form-row">
                      <div className="form-group">
                        <label htmlFor="speed-slider">Скорость: {customSpeed}</label>
                        <input
                          id="speed-slider"
                          type="range"
                          min="0.5"
                          max="2.0"
                          step="0.1"
                          value={customSpeed}
                          onChange={(e) => setCustomSpeed(parseFloat(e.target.value))}
                        />
                      </div>
                      
                      <div className="form-group">
                        <label htmlFor="pitch-slider">Высота тона: {customPitch}</label>
                        <input
                          id="pitch-slider"
                          type="range"
                          min="-1.0"
                          max="1.0"
                          step="0.1"
                          value={customPitch}
                          onChange={(e) => setCustomPitch(parseFloat(e.target.value))}
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Generate Button */}
            <div className="form-group">
              <button
                className="primary large"
                onClick={generateVoice}
                disabled={loading || !text.trim() || (generationMode === 'voice_design' && !voiceInstruct.trim())}
              >
                {loading ? 'Генерация...' : 
                 generationMode === 'voice_design' ? '✨ Дизайн голоса' : '🎤 Сгенерировать голос'}
              </button>
              
              {generationMode === 'voice_design' && !voiceInstruct.trim() && (
                <small className="validation-hint">
                  Нужны инструкции по дизайну голоса
                </small>
              )}
            </div>

            {/* Current Audio Player */}
            {currentAudio && (
              <div className="current-audio">
                <h3>Сгенерированное аудио:</h3>
                <audio controls style={{ width: '100%' }}>
                  <source src={currentAudio} type="audio/wav" />
                  Ваш браузер не поддерживает аудио.
                </audio>
                <div className="audio-actions">
                  <a
                    href={currentAudio}
                    download
                    className="ghost"
                  >
                    📥 Скачать
                  </a>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* History Panel */}
        <div className="voice-generator-sidebar">
          <div className="card">
            <div className="card-header">
              <h2>История генераций</h2>
              <button 
                className="ghost small"
                onClick={fetchHistory}
              >
                🔄 Обновить
              </button>
            </div>
            
            <div className="history-list">
              {history.length === 0 ? (
                <p className="muted">Генераций пока нет</p>
              ) : (
                history.map((item) => (
                  <div key={item.audio_filename} className="history-item">
                    <div className="history-content">
                      <div className="history-text" title={item.text}>
                        {item.text.length > 50 ? `${item.text.substring(0, 50)}...` : item.text}
                      </div>
                      {item.voice_prompt && (
                        <div className="history-prompt" title={item.voice_prompt}>
                          Голос: {item.voice_prompt.length > 40 ? `${item.voice_prompt.substring(0, 40)}...` : item.voice_prompt}
                        </div>
                      )}
                      <div className="history-meta">
                        <small>{new Date(item.timestamp).toLocaleString()}</small>
                        {item.preset && <span className="preset-tag">{item.preset}</span>}
                      </div>
                    </div>
                    <div className="history-actions">
                      <button
                        className="ghost small"
                        onClick={() => loadFromHistory(item)}
                        title="Загрузить"
                      >
                        📋
                      </button>
                      <button
                        className="ghost small"
                        onClick={() => setCurrentAudio(item.audio_url)}
                        title="Воспроизвести"
                      >
                        ▶️
                      </button>
                      <a
                        href={item.audio_url}
                        download
                        className="ghost small"
                        title="Скачать"
                      >
                        📥
                      </a>
                      <button
                        className="ghost small danger"
                        onClick={() => {
                          if (confirm('Удалить эту генерацию?')) {
                            deleteGeneration(item.audio_filename);
                          }
                        }}
                        title="Удалить"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VoiceGeneratorTab;
