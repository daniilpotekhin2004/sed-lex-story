import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useCallback } from 'react';
import toast from 'react-hot-toast';

interface GenerationState {
  isGenerating: boolean;
  progress?: number;
  stage?: string;
  error?: string;
}

interface UseAsyncGenerationOptions {
  onSuccess?: (data: any) => void;
  onError?: (error: any) => void;
  showToast?: boolean;
}

/**
 * Hook for non-blocking generation operations.
 * 
 * Root cause: Synchronous await calls block UI thread during generation.
 * Fix: Use React Query mutations with local state management for responsive UI.
 */

// Simple notification replacement for react-hot-toast
const notify = {
  success: (message: string) => {
    console.log('✅', message);
    // Could be replaced with a proper notification system later
  },
  error: (message: string) => {
    console.error('❌', message);
    // Could be replaced with a proper notification system later
  }
};

export function useAsyncGeneration<TData = any, TVariables = any>(
  mutationFn: (variables: TVariables) => Promise<TData>,
  options: UseAsyncGenerationOptions = {}
) {
  const queryClient = useQueryClient();
  const [localState, setLocalState] = useState<GenerationState>({
    isGenerating: false
  });

  const mutation = useMutation({
    mutationFn,
    onMutate: () => {
      // Set local loading state immediately (non-blocking)
      setLocalState({
        isGenerating: true,
        progress: 0,
        stage: 'Starting generation...'
      });
    },
    onSuccess: (data) => {
      setLocalState({
        isGenerating: false,
        progress: 100,
        stage: 'Завершено'
      });
      
      if (options.showToast !== false) {
        notify.success('Generation completed successfully');
      }
      
      options.onSuccess?.(data);
      
      // Invalidate related queries to refresh UI
      queryClient.invalidateQueries();
    },
    onError: (error: any) => {
      const errorMessage = error?.response?.data?.detail || error?.message || 'Generation failed';
      
      setLocalState({
        isGenerating: false,
        error: errorMessage
      });
      
      if (options.showToast !== false) {
        notify.error(errorMessage);
      }
      
      options.onError?.(error);
    }
  });

  const generateAsync = useCallback((variables: TVariables) => {
    // Start generation without blocking UI
    mutation.mutate(variables);
  }, [mutation]);

  const reset = useCallback(() => {
    setLocalState({
      isGenerating: false
    });
    mutation.reset();
  }, [mutation]);

  return {
    generateAsync,
    reset,
    isGenerating: localState.isGenerating || mutation.isPending,
    progress: localState.progress,
    stage: localState.stage,
    error: localState.error || mutation.error,
    data: mutation.data,
    isSuccess: mutation.isSuccess,
    isError: mutation.isError
  };
}

/**
 * Hook for character generation operations.
 */
export function useCharacterGeneration() {
  return {
    sketch: useAsyncGeneration(
      async (presetId: string) => {
        const { generateCharacterSketch } = await import('../api/characters');
        return generateCharacterSketch(presetId);
      },
      { showToast: true }
    ),
    
    sheet: useAsyncGeneration(
      async ({ presetId, overrides }: { presetId: string; overrides?: any }) => {
        const { generateCharacterSheet } = await import('../api/characters');
        return generateCharacterSheet(presetId, overrides);
      },
      { showToast: true }
    ),
    
    multiview: useAsyncGeneration(
      async (presetId: string) => {
        const { generateCharacterRepresentation } = await import('../api/characters');
        return generateCharacterRepresentation(presetId, {
          task_type: 'character_multiview',
          workflow_set: 'custom'
        });
      },
      { showToast: true }
    )
  };
}

/**
 * Hook for scene generation operations.
 */
export function useSceneGeneration() {
  return useAsyncGeneration(
    async ({ sceneId, options }: { sceneId: string; options?: any }) => {
      const { generateSceneImage } = await import('../api/generation');
      return generateSceneImage(sceneId, options || { use_prompt_engine: true, num_variants: 1 });
    },
    { showToast: true }
  );
}

/**
 * Hook for voice generation operations.
 */
export function useVoiceGeneration() {
  return useAsyncGeneration(
    async (payload: { text: string; voice_profile?: string; language?: string }) => {
      const { generateVoicePreview } = await import('../api/ai');
      return generateVoicePreview(payload);
    },
    { showToast: true }
  );
}
