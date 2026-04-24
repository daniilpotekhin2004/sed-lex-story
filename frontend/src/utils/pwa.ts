/**
 * PWA Utilities для LexQuest
 * Управление service worker, кешированием и офлайн-функциональностью
 */

export interface CacheStats {
  size: number;
  sizeFormatted: string;
}

export interface QuestCacheOptions {
  questId: string;
  includeImages?: boolean;
}

/**
 * Проверить, установлено ли приложение как PWA
 */
export function isPWAInstalled(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    (window.navigator as any).standalone === true ||
    document.referrer.includes('android-app://')
  );
}

/**
 * Проверить, доступен ли service worker
 */
export function isServiceWorkerSupported(): boolean {
  return 'serviceWorker' in navigator;
}

/**
 * Получить активный service worker
 */
export function getServiceWorker(): ServiceWorkerRegistration | null {
  return navigator.serviceWorker.controller
    ? navigator.serviceWorker.getRegistration().then((reg) => reg || null)
    : null;
}

/**
 * Отправить сообщение service worker
 */
export async function sendMessageToSW(message: any): Promise<void> {
  if (!isServiceWorkerSupported()) {
    throw new Error('Service Worker not supported');
  }

  const registration = await navigator.serviceWorker.ready;
  if (registration.active) {
    registration.active.postMessage(message);
  }
}

/**
 * Кешировать квест для офлайн-доступа
 */
export async function cacheQuest(options: QuestCacheOptions): Promise<void> {
  await sendMessageToSW({
    type: 'CACHE_QUEST',
    questId: options.questId,
    includeImages: options.includeImages ?? true,
  });
}

/**
 * Очистить все кеши
 */
export async function clearAllCaches(): Promise<void> {
  await sendMessageToSW({
    type: 'CLEAR_CACHE',
  });
}

/**
 * Получить размер кешей
 */
export async function getCacheSize(): Promise<CacheStats> {
  return new Promise((resolve, reject) => {
    if (!isServiceWorkerSupported()) {
      reject(new Error('Service Worker not supported'));
      return;
    }

    const messageChannel = new MessageChannel();
    
    messageChannel.port1.onmessage = (event) => {
      if (event.data && event.data.type === 'CACHE_SIZE') {
        const size = event.data.size;
        resolve({
          size,
          sizeFormatted: formatBytes(size),
        });
      }
    };

    navigator.serviceWorker.ready.then((registration) => {
      if (registration.active) {
        registration.active.postMessage(
          { type: 'GET_CACHE_SIZE' },
          [messageChannel.port2]
        );
      }
    });
  });
}

/**
 * Проверить, онлайн ли приложение
 */
export function isOnline(): boolean {
  return navigator.onLine;
}

/**
 * Подписаться на изменения онлайн-статуса
 */
export function subscribeToOnlineStatus(
  callback: (online: boolean) => void
): () => void {
  const handleOnline = () => callback(true);
  const handleOffline = () => callback(false);

  window.addEventListener('online', handleOnline);
  window.addEventListener('offline', handleOffline);

  return () => {
    window.removeEventListener('online', handleOnline);
    window.removeEventListener('offline', handleOffline);
  };
}

/**
 * Проверить, закеширован ли квест
 */
export async function isQuestCached(questId: string): Promise<boolean> {
  if (!('caches' in window)) {
    return false;
  }

  try {
    const cache = await caches.open('lexquest-api-v2.0.0');
    const response = await cache.match(`/api/quests/${questId}`);
    return !!response;
  } catch (error) {
    console.error('Error checking quest cache:', error);
    return false;
  }
}

/**
 * Получить список закешированных квестов
 */
export async function getCachedQuests(): Promise<string[]> {
  if (!('caches' in window)) {
    return [];
  }

  try {
    const cache = await caches.open('lexquest-api-v2.0.0');
    const requests = await cache.keys();
    
    const questIds = requests
      .map((request) => {
        const match = request.url.match(/\/api\/quests\/([a-f0-9]+)/);
        return match ? match[1] : null;
      })
      .filter((id): id is string => id !== null);

    return [...new Set(questIds)];
  } catch (error) {
    console.error('Error getting cached quests:', error);
    return [];
  }
}

/**
 * Удалить квест из кеша
 */
export async function uncacheQuest(questId: string): Promise<void> {
  if (!('caches' in window)) {
    return;
  }

  try {
    const cacheNames = await caches.keys();
    
    for (const cacheName of cacheNames) {
      const cache = await caches.open(cacheName);
      const requests = await cache.keys();
      
      for (const request of requests) {
        if (request.url.includes(`/quests/${questId}`)) {
          await cache.delete(request);
        }
      }
    }
  } catch (error) {
    console.error('Error uncaching quest:', error);
  }
}

/**
 * Обновить service worker
 */
export async function updateServiceWorker(): Promise<void> {
  if (!isServiceWorkerSupported()) {
    return;
  }

  const registration = await navigator.serviceWorker.ready;
  await registration.update();
}

/**
 * Запросить разрешение на уведомления
 */
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!('Уведомление' in window)) {
    throw new Error('Notifications not supported');
  }

  if (Notification.permission === 'granted') {
    return 'granted';
  }

  if (Notification.permission !== 'denied') {
    return await Notification.requestPermission();
  }

  return Notification.permission;
}

/**
 * Показать уведомление
 */
export async function showNotification(
  title: string,
  options?: NotificationOptions
): Promise<void> {
  const permission = await requestNotificationPermission();
  
  if (permission === 'granted') {
    const registration = await navigator.serviceWorker.ready;
    await registration.showNotification(title, {
      icon: '/icons/icon-192.png',
      badge: '/icons/badge-72.png',
      ...options,
    });
  }
}

/**
 * Проверить, можно ли установить PWA
 */
export function canInstallPWA(): boolean {
  return !isPWAInstalled() && 'BeforeInstallPromptEvent' in window;
}

/**
 * Форматировать байты в читаемый формат
 */
function formatBytes(bytes: number, decimals: number = 2): string {
  if (bytes === 0) return '0 Bytes';

  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];

  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

/**
 * Получить информацию о PWA
 */
export interface PWAInfo {
  isInstalled: boolean;
  isOnline: boolean;
  canInstall: boolean;
  serviceWorkerSupported: boolean;
  notificationsSupported: boolean;
  notificationPermission: NotificationPermission | null;
}

export async function getPWAInfo(): Promise<PWAInfo> {
  return {
    isInstalled: isPWAInstalled(),
    isOnline: isOnline(),
    canInstall: canInstallPWA(),
    serviceWorkerSupported: isServiceWorkerSupported(),
    notificationsSupported: 'Уведомление' in window,
    notificationPermission: 'Уведомление' in window ? Notification.permission : null,
  };
}
