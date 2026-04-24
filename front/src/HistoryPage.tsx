import { useState, useEffect, useCallback } from 'react';
import {
  isPWAInstalled,
  isOnline,
  subscribeToOnlineStatus,
  cacheQuest,
  getCacheSize,
  clearAllCaches,
  isQuestCached,
  getCachedQuests,
  uncacheQuest,
  getPWAInfo,
  type CacheStats,
  type PWAInfo,
  type QuestCacheOptions,
} from '../utils/pwa';

/**
 * Hook для работы с PWA функциональностью
 */
export function usePWA() {
  const [online, setOnline] = useState(isOnline());
  const [installed, setInstalled] = useState(isPWAInstalled());
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [pwaInfo, setPWAInfo] = useState<PWAInfo | null>(null);

  // Подписка на изменения онлайн-статуса
  useEffect(() => {
    const unsubscribe = subscribeToOnlineStatus(setOnline);
    return unsubscribe;
  }, []);

  // Загрузка информации о PWA
  useEffect(() => {
    getPWAInfo().then(setPWAInfo);
  }, []);

  // Обновление статистики кеша
  const updateCacheStats = useCallback(async () => {
    try {
      const stats = await getCacheSize();
      setCacheStats(stats);
    } catch (error) {
      console.error('Failed to get cache stats:', error);
    }
  }, []);

  // Кеширование квеста
  const cacheQuestData = useCallback(async (options: QuestCacheOptions) => {
    try {
      await cacheQuest(options);
      await updateCacheStats();
      return true;
    } catch (error) {
      console.error('Failed to cache quest:', error);
      return false;
    }
  }, [updateCacheStats]);

  // Очистка кешей
  const clearCaches = useCallback(async () => {
    try {
      await clearAllCaches();
      await updateCacheStats();
      return true;
    } catch (error) {
      console.error('Failed to clear caches:', error);
      return false;
    }
  }, [updateCacheStats]);

  // Проверка кеша квеста
  const checkQuestCache = useCallback(async (questId: string) => {
    try {
      return await isQuestCached(questId);
    } catch (error) {
      console.error('Failed to check quest cache:', error);
      return false;
    }
  }, []);

  // Получение списка закешированных квестов
  const getCachedQuestsList = useCallback(async () => {
    try {
      return await getCachedQuests();
    } catch (error) {
      console.error('Failed to get cached quests:', error);
      return [];
    }
  }, []);

  // Удаление квеста из кеша
  const removeQuestFromCache = useCallback(async (questId: string) => {
    try {
      await uncacheQuest(questId);
      await updateCacheStats();
      return true;
    } catch (error) {
      console.error('Failed to uncache quest:', error);
      return false;
    }
  }, [updateCacheStats]);

  return {
    // Состояние
    online,
    installed,
    cacheStats,
    pwaInfo,

    // Методы
    cacheQuest: cacheQuestData,
    clearCaches,
    checkQuestCache,
    getCachedQuests: getCachedQuestsList,
    uncacheQuest: removeQuestFromCache,
    updateCacheStats,
  };
}

/**
 * Hook для отслеживания онлайн-статуса
 */
export function useOnlineStatus() {
  const [online, setOnline] = useState(isOnline());

  useEffect(() => {
    const unsubscribe = subscribeToOnlineStatus(setOnline);
    return unsubscribe;
  }, []);

  return online;
}

/**
 * Hook для кеширования квеста
 */
export function useQuestCache(questId: string | null) {
  const [cached, setCached] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!questId) {
      setCached(false);
      return;
    }

    isQuestCached(questId).then(setCached);
  }, [questId]);

  const cache = useCallback(async () => {
    if (!questId) return false;

    setLoading(true);
    try {
      await cacheQuest({ questId });
      setCached(true);
      return true;
    } catch (error) {
      console.error('Failed to cache quest:', error);
      return false;
    } finally {
      setLoading(false);
    }
  }, [questId]);

  const uncache = useCallback(async () => {
    if (!questId) return false;

    setLoading(true);
    try {
      await uncacheQuest(questId);
      setCached(false);
      return true;
    } catch (error) {
      console.error('Failed to uncache quest:', error);
      return false;
    } finally {
      setLoading(false);
    }
  }, [questId]);

  return {
    cached,
    loading,
    cache,
    uncache,
  };
}
