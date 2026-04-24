import React, { useState, useEffect } from 'react';
import { usePWA } from '../hooks/usePWA';

/**
 * Компонент для управления PWA функциональностью
 * Показывает статус онлайн/офлайн, размер кеша, кнопку установки
 */
export function PWAManager() {
  const {
    online,
    installed,
    cacheStats,
    pwaInfo,
    clearCaches,
    updateCacheStats,
  } = usePWA();

  const [showInstallPrompt, setShowInstallPrompt] = useState(false);
  const [deferredPrompt, setDeferredPrompt] = useState<any>(null);

  useEffect(() => {
    // Обработка события установки PWA
    const handleBeforeInstallPrompt = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setShowInstallPrompt(true);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    };
  }, []);

  useEffect(() => {
    // Загрузить статистику кеша при монтировании
    updateCacheStats();
  }, [updateCacheStats]);

  const handleInstall = async () => {
    if (!deferredPrompt) return;

    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    
    if (outcome === 'accepted') {
      console.log('User accepted the install prompt');
    }
    
    setDeferredPrompt(null);
    setShowInstallPrompt(false);
  };

  const handleClearCache = async () => {
    if (confirm('Очистить все кеши? Это удалит офлайн-данные.')) {
      const success = await clearCaches();
      if (success) {
        alert('Кеши очищены');
      }
    }
  };

  return (
    <div className="pwa-manager">
      {/* Статус онлайн/офлайн */}
      <div className={`status-indicator ${online ? 'online' : 'offline'}`}>
        <span className="status-dot"></span>
        <span className="status-text">
          {online ? 'Онлайн' : 'Офлайн'}
        </span>
      </div>

      {/* Кнопка установки PWA */}
      {showInstallPrompt && !installed && (
        <button
          id="install-button"
          className="install-button"
          onClick={handleInstall}
        >
          📱 Установить приложение
        </button>
      )}

      {/* Информация о кеше */}
      {cacheStats && (
        <div className="cache-info">
          <p>Размер кеша: {cacheStats.sizeFormatted}</p>
          <button onClick={handleClearCache} className="clear-cache-button">
            🗑️ Очистить кеш
          </button>
        </div>
      )}

      {/* Информация о PWA */}
      {pwaInfo && (
        <div className="pwa-info">
          <p>
            {installed ? '✅ Установлено как PWA' : '📱 Веб-версия'}
          </p>
          {pwaInfo.serviceWorkerSupported && (
            <p>✅ Service Worker активен</p>
          )}
          {pwaInfo.notificationsSupported && (
            <p>
              {pwaInfo.notificationPermission === 'granted'
                ? '✅ Уведомления разрешены'
                : '🔔 Уведомления доступны'}
            </p>
          )}
        </div>
      )}

      <style>{`
        .pwa-manager {
          position: fixed;
          bottom: 20px;
          right: 20px;
          background: rgba(11, 16, 32, 0.95);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 12px;
          padding: 16px;
          color: white;
          font-family: system-ui, -apple-system, sans-serif;
          font-size: 14px;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
          z-index: 1000;
          max-width: 300px;
        }

        .status-indicator {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 12px;
        }

        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          animation: pulse 2s infinite;
        }

        .status-indicator.online .status-dot {
          background: #4ade80;
        }

        .status-indicator.offline .status-dot {
          background: #f87171;
        }

        @keyframes pulse {
          0%, 100% {
            opacity: 1;
          }
          50% {
            opacity: 0.5;
          }
        }

        .install-button,
        .clear-cache-button {
          width: 100%;
          padding: 10px 16px;
          margin-top: 8px;
          background: rgba(255, 255, 255, 0.1);
          border: 1px solid rgba(255, 255, 255, 0.2);
          border-radius: 8px;
          color: white;
          cursor: pointer;
          font-size: 14px;
          transition: all 0.2s;
        }

        .install-button:hover,
        .clear-cache-button:hover {
          background: rgba(255, 255, 255, 0.2);
          transform: translateY(-1px);
        }

        .cache-info,
        .pwa-info {
          margin-top: 12px;
          padding-top: 12px;
          border-top: 1px solid rgba(255, 255, 255, 0.1);
        }

        .cache-info p,
        .pwa-info p {
          margin: 4px 0;
          font-size: 13px;
          opacity: 0.9;
        }

        @media (max-width: 768px) {
          .pwa-manager {
            bottom: 10px;
            right: 10px;
            left: 10px;
            max-width: none;
          }
        }
      `}</style>
    </div>
  );
}

/**
 * Компонент индикатора офлайн-режима
 */
export function OfflineIndicator() {
  const { online } = usePWA();

  if (online) return null;

  return (
    <div className="offline-banner">
      <span>⚠️ Вы офлайн. Некоторые функции могут быть недоступны.</span>
      
      <style>{`
        .offline-banner {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          background: #f59e0b;
          color: white;
          padding: 12px;
          text-align: center;
          font-size: 14px;
          font-weight: 500;
          z-index: 9999;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        }
      `}</style>
    </div>
  );
}

/**
 * Компонент кнопки кеширования квеста
 */
interface CacheQuestButtonProps {
  questId: string;
  questTitle?: string;
}

export function CacheQuestButton({ questId, questTitle }: CacheQuestButtonProps) {
  const [cached, setCached] = useState(false);
  const [loading, setLoading] = useState(false);
  const { cacheQuest, uncacheQuest, checkQuestCache } = usePWA();

  useEffect(() => {
    checkQuestCache(questId).then(setCached);
  }, [questId, checkQuestCache]);

  const handleToggleCache = async () => {
    setLoading(true);
    try {
      if (cached) {
        await uncacheQuest(questId);
        setCached(false);
      } else {
        await cacheQuest({ questId });
        setCached(true);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleToggleCache}
      disabled={loading}
      className="cache-quest-button"
      title={cached ? 'Удалить из офлайн-доступа' : 'Сохранить для офлайн-доступа'}
    >
      {loading ? '⏳' : cached ? '📥' : '📤'}
      {' '}
      {cached ? 'Доступно офлайн' : 'Сохранить офлайн'}
      
      <style>{`
        .cache-quest-button {
          padding: 8px 16px;
          background: rgba(255, 255, 255, 0.1);
          border: 1px solid rgba(255, 255, 255, 0.2);
          border-radius: 6px;
          color: white;
          cursor: pointer;
          font-size: 13px;
          transition: all 0.2s;
        }

        .cache-quest-button:hover:not(:disabled) {
          background: rgba(255, 255, 255, 0.2);
        }

        .cache-quest-button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      `}</style>
    </button>
  );
}
