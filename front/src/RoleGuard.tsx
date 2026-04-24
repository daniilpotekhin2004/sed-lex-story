import React, { useState, useEffect } from 'react';
import { Button, Select, Input, Card, message, Spin } from 'antd';
import { AudioOutlined, LoadingOutlined } from '@ant-design/icons';

const { TextArea } = Input;
const { Option } = Select;

interface TTSModel {
  name: string;
  info: string;
  type: string;
}

interface TTSStatus {
  available: boolean;
  models_count: number;
  models: TTSModel[];
  models_dir: string;
}

const TTSComponent: React.FC = () => {
  const [status, setStatus] = useState<TTSStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState('');
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [audioUrl, setAudioUrl] = useState<string>('');
  const audioType = audioUrl.endsWith(".wav")
    ? "audio/wav"
    : audioUrl.endsWith(".ogg")
      ? "audio/ogg"
      : "audio/mpeg";

  useEffect(() => {
    fetchTTSStatus();
  }, []);

  const fetchTTSStatus = async () => {
    try {
      const response = await fetch('/api/v1/tts/status');
      const data = await response.json();
      setStatus(data);
      
      if (data.models.length > 0) {
        setSelectedModel(data.models[0].name);
      }
    } catch (error) {
      console.error('Failed to fetch TTS status:', error);
      message.error('Не удалось загрузить сервис TTS');
    }
  };

  const synthesizeSpeech = async () => {
    if (!text.trim()) {
      message.warning('Введите текст для синтеза');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('/api/v1/tts/synthesize', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: text,
          voice_id: selectedModel || undefined,
        }),
      });

      const data = await response.json();
      
      if (data.success && data.audio_url) {
        setAudioUrl(data.audio_url);
        message.success('Речь успешно сгенерирована!');
      } else {
        message.error(data.message || 'Синтез речи не удался');
      }
    } catch (error) {
      console.error('TTS synthesis error:', error);
      message.error('Не удалось синтезировать речь');
    } finally {
      setLoading(false);
    }
  };

  if (!status) {
    return <Spin size="large" />;
  }

  if (!status.available) {
    return (
      <Card title="Текст‑в‑речь" className="tts-component">
        <div style={{ textAlign: 'center', padding: '20px' }}>
          <p>Сервис TTS недоступен</p>
          <p>Каталог моделей: {status.models_dir}</p>
          <Button onClick={fetchTTSStatus}>Повторить</Button>
        </div>
      </Card>
    );
  }

  return (
    <Card title="Текст‑в‑речь" className="tts-component">
      <div style={{ marginBottom: '16px' }}>
        <label>Модель голоса:</label>
        <Select
          value={selectedModel}
          onChange={setSelectedModel}
          style={{ width: '100%', marginTop: '8px' }}
          placeholder="Выберите модель голоса"
        >
          {status.models.map((model) => (
            <Option key={model.name} value={model.name}>
              {model.name} ({model.info})
            </Option>
          ))}
        </Select>
      </div>

      <div style={{ marginBottom: '16px' }}>
        <label>Текст для озвучивания:</label>
        <TextArea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Введите текст для преобразования в речь..."
          rows={4}
          style={{ marginTop: '8px' }}
        />
      </div>

      <div style={{ marginBottom: '16px' }}>
        <Button
          type="primary"
          icon={loading ? <LoadingOutlined /> : <AudioOutlined />}
          onClick={synthesizeSpeech}
          loading={loading}
          disabled={!text.trim()}
        >
          Сгенерировать речь
        </Button>
      </div>

      {audioUrl && (
        <div style={{ marginTop: '16px' }}>
          <label>Сгенерированное аудио:</label>
          <audio controls style={{ width: '100%', marginTop: '8px' }}>
            <source src={audioUrl} type={audioType} />
            Ваш браузер не поддерживает аудио.
          </audio>
        </div>
      )}

      <div style={{ marginTop: '16px', fontSize: '12px', color: '#666' }}>
        Доступно моделей: {status.models_count}
      </div>
    </Card>
  );
};

export default TTSComponent;
