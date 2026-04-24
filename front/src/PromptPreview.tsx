import React from 'react';
import './GenerationStatus.css';

interface GenerationStatusProps {
  isGenerating: boolean;
  progress?: number;
  stage?: string;
  error?: string;
  className?: string;
}

/**
 * Non-blocking generation status component.
 * 
 * Shows loading state for individual operations without freezing the entire UI.
 */
export const GenerationStatus: React.FC<GenerationStatusProps> = ({
  isGenerating,
  progress,
  stage,
  error,
  className = ''
}) => {
  if (!isGenerating && !error) {
    return null;
  }

  return (
    <div className={`generation-status ${className}`}>
      {isGenerating && (
        <div className="generation-progress">
          <div className="progress-bar">
            <div 
              className="progress-fill" 
              style={{ width: `${progress || 0}%` }}
            />
          </div>
          {stage && (
            <div className="progress-stage">{stage}</div>
          )}
        </div>
      )}
      
      {error && (
        <div className="generation-error">
          <span className="error-icon">⚠️</span>
          <span className="error-message">{error}</span>
        </div>
      )}
    </div>
  );
};

/**
 * Inline generation button with built-in status.
 */
interface GenerationButtonProps {
  onClick: () => void;
  isGenerating: boolean;
  disabled?: boolean;
  children: React.ReactNode;
  className?: string;
  stage?: string;
}

export const GenerationButton: React.FC<GenerationButtonProps> = ({
  onClick,
  isGenerating,
  disabled,
  children,
  className = '',
  stage
}) => {
  return (
    <div className="generation-button-container">
      <button
        onClick={onClick}
        disabled={disabled || isGenerating}
        className={`generation-button ${className} ${isGenerating ? 'generating' : ''}`}
      >
        {isGenerating ? (
          <div className="button-generating">
            <div className="spinner" />
            <span>{stage || "Генерация..."}</span>
          </div>
        ) : (
          children
        )}
      </button>
    </div>
  );
};
