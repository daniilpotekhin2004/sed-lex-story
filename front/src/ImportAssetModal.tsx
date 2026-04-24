.generation-status {
  margin: 8px 0;
}

.generation-progress {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.progress-bar {
  width: 100%;
  height: 4px;
  background: rgba(0, 0, 0, 0.1);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #8b5cf6);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.progress-stage {
  font-size: 12px;
  color: #666;
  font-style: italic;
}

.generation-error {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 4px;
  color: #dc2626;
  font-size: 14px;
}

.error-icon {
  font-size: 16px;
}

.error-message {
  flex: 1;
}

/* Generation Button Styles */
.generation-button-container {
  position: relative;
}

.generation-button {
  position: relative;
  transition: all 0.2s ease;
}

.generation-button.generating {
  opacity: 0.8;
  cursor: not-allowed;
}

.button-generating {
  display: flex;
  align-items: center;
  gap: 8px;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top: 2px solid currentColor;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* Dark theme support */
[data-theme="dark"] .progress-bar {
  background: rgba(255, 255, 255, 0.1);
}

[data-theme="dark"] .progress-stage {
  color: #999;
}

[data-theme="dark"] .generation-error {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.3);
  color: #f87171;
}