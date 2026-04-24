.voice-generator {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.voice-generator-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
}

.voice-generator-unavailable {
  text-align: center;
  padding: 60px 20px;
}

.voice-generator-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
}

.voice-generator-stats {
  display: flex;
  gap: 20px;
}

.stat {
  padding: 8px 12px;
  background: var(--color-bg-secondary);
  border-radius: 6px;
  font-size: 14px;
}

.voice-generator-layout {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 30px;
}

@media (max-width: 768px) {
  .voice-generator-layout {
    grid-template-columns: 1fr;
  }
}

.voice-generator-main {
  min-width: 0;
}

.voice-generator-sidebar {
  min-width: 0;
}

.sample-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.sample-buttons button {
  font-size: 12px;
  padding: 4px 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

@media (max-width: 600px) {
  .form-row {
    grid-template-columns: 1fr;
  }
}

.advanced-settings {
  margin-top: 15px;
  padding: 15px;
  background: var(--color-bg-secondary);
  border-radius: 6px;
}

.current-audio {
  margin-top: 20px;
  padding: 20px;
  background: var(--color-bg-accent);
  border-radius: 6px;
}

.current-audio h3 {
  margin: 0 0 15px 0;
  font-size: 16px;
}

.audio-actions {
  margin-top: 10px;
}

.history-list {
  max-height: 500px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 12px;
  border-bottom: 1px solid var(--color-border);
  gap: 10px;
}

.history-item:last-child {
  border-bottom: none;
}

.history-content {
  flex: 1;
  min-width: 0;
}

.history-text {
  font-size: 14px;
  line-height: 1.4;
  margin-bottom: 5px;
  word-break: break-word;
}

.history-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.preset-tag {
  background: var(--color-primary);
  color: white;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
}

.history-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.history-actions button,
.history-actions a {
  padding: 4px 6px;
  font-size: 12px;
  min-width: auto;
}

.message {
  padding: 12px 16px;
  border-radius: 6px;
  margin-bottom: 20px;
  font-weight: 500;
}

.message.success {
  background: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.message.error {
  background: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

.message.info {
  background: #d1ecf1;
  color: #0c5460;
  border: 1px solid #bee5eb;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid var(--color-border);
  border-top: 4px solid var(--color-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 15px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* Dark theme adjustments */
[data-theme="dark"] .message.success {
  background: #1e4620;
  color: #a3d9a5;
  border-color: #2d5a2f;
}

[data-theme="dark"] .message.error {
  background: #4a1e1e;
  color: #f5a3a3;
  border-color: #5a2d2d;
}

[data-theme="dark"] .message.info {
  background: #1e3a4a;
  color: #a3d1f5;
  border-color: #2d4a5a;
}


/* Progress Status Bar */
.progress-status-bar {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 30px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.progress-header h3 {
  margin: 0;
  font-size: 18px;
  color: var(--color-text-primary);
}

.progress-info {
  display: flex;
  gap: 15px;
  font-size: 14px;
  color: var(--color-text-secondary);
}

.progress-step {
  font-weight: 600;
}

.progress-time {
  color: var(--color-primary);
}

.progress-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.progress-bar-container {
  width: 100%;
  height: 8px;
  background: var(--color-bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-bar.preparing {
  background: linear-gradient(90deg, #fbbf24, #f59e0b);
}

.progress-bar.processing {
  background: linear-gradient(90deg, #3b82f6, #1d4ed8);
  animation: pulse 2s infinite;
}

.progress-bar.complete {
  background: linear-gradient(90deg, #10b981, #059669);
}

.progress-bar.error {
  background: linear-gradient(90deg, #ef4444, #dc2626);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.progress-details {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.current-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.status-icon {
  font-size: 16px;
}

.step-name {
  color: var(--color-text-primary);
}

.progress-message {
  font-size: 14px;
  color: var(--color-text-secondary);
  font-style: italic;
}

/* Enhanced Input Styling */
.primary-input {
  border: 2px solid var(--color-primary);
  border-radius: 6px;
  padding: 12px;
  font-size: 16px;
  line-height: 1.5;
  transition: border-color 0.2s ease;
}

.primary-input:focus {
  outline: none;
  border-color: var(--color-primary-dark);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.secondary-input {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 10px;
  font-size: 14px;
  line-height: 1.4;
  transition: border-color 0.2s ease;
}

.secondary-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
}

.voice-prompt-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.prompt-samples {
  margin-top: 10px;
}

.prompt-samples label {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 5px;
  display: block;
}

/* Enhanced History Items */
.history-prompt {
  font-size: 12px;
  color: var(--color-text-secondary);
  font-style: italic;
  margin-top: 3px;
  line-height: 1.3;
}

.history-actions button:nth-child(1) {
  background: var(--color-bg-accent);
}

.history-actions button:nth-child(1):hover {
  background: var(--color-primary);
  color: white;
}

/* Responsive Enhancements */
@media (max-width: 768px) {
  .progress-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  
  .progress-details {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  
  .voice-prompt-section .sample-buttons {
    grid-template-columns: 1fr;
  }
}

/* Enhanced Form Styling */
.form-group label {
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 8px;
  display: block;
}

.form-group small {
  color: var(--color-text-secondary);
  font-size: 12px;
  margin-top: 5px;
  display: block;
}

/* Button Enhancements */
.primary.large {
  padding: 15px 30px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 8px;
  transition: all 0.2s ease;
}

.primary.large:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}

.primary.large:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Dark Theme Enhancements */
[data-theme="dark"] .progress-status-bar {
  background: var(--color-bg-primary);
  border-color: var(--color-border-dark);
}

[data-theme="dark"] .primary-input {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

[data-theme="dark"] .secondary-input {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}
/* Voice Design Features */
.generation-mode-selector {
  background: var(--color-bg-secondary);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 30px;
  border: 1px solid var(--color-border);
}

.mode-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 15px;
  background: var(--color-bg-tertiary);
  border-radius: 6px;
  padding: 4px;
}

.mode-tab {
  flex: 1;
  padding: 12px 20px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-weight: 500;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 14px;
}

.mode-tab:hover {
  background: var(--color-bg-accent);
  color: var(--color-text-primary);
}

.mode-tab.active {
  background: var(--color-primary);
  color: white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.mode-description {
  text-align: center;
  color: var(--color-text-secondary);
  font-size: 14px;
  line-height: 1.4;
}

.voice-design-section {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.05), rgba(147, 51, 234, 0.05));
  border: 2px solid rgba(59, 130, 246, 0.2);
  border-radius: 8px;
  padding: 20px;
  margin: 15px 0;
}

.voice-design-input {
  background: rgba(255, 255, 255, 0.9);
  border: 2px solid var(--color-primary);
  font-family: inherit;
  resize: vertical;
}

[data-theme="dark"] .voice-design-input {
  background: rgba(0, 0, 0, 0.3);
  color: var(--color-text-primary);
}

.voice-instruct-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.instruct-samples {
  margin-top: 15px;
}

.instruct-samples label {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
  display: block;
  font-weight: 500;
}

.instruct-samples .sample-buttons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 8px;
}

.instruct-samples .sample-buttons button {
  text-align: left;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1.3;
  max-width: none;
  white-space: normal;
  height: auto;
  min-height: 40px;
}

.language-selector {
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-size: 14px;
  cursor: pointer;
}

.language-selector:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
}

.validation-hint {
  color: var(--color-error, #ef4444);
  font-style: italic;
  margin-top: 8px;
}

.qwen-available {
  background: linear-gradient(135deg, #10b981, #059669);
  color: white;
  font-weight: 600;
}

/* Enhanced Model Selection */
.form-group select option {
  padding: 8px;
}

/* Voice Design History Items */
.history-item.voice-design {
  border-left: 4px solid var(--color-primary);
  background: rgba(59, 130, 246, 0.02);
}

.history-instruct {
  font-size: 11px;
  color: var(--color-primary);
  font-weight: 500;
  margin-top: 2px;
  line-height: 1.2;
}

/* Responsive Voice Design */
@media (max-width: 768px) {
  .mode-tabs {
    flex-direction: column;
  }
  
  .mode-tab {
    text-align: center;
  }
  
  .voice-design-section {
    padding: 15px;
    margin: 10px 0;
  }
  
  .instruct-samples .sample-buttons {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .generation-mode-selector {
    padding: 15px;
  }
  
  .voice-design-section {
    padding: 12px;
  }
}

/* Enhanced Progress for Voice Design */
.progress-status-bar.voice-design {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.05), rgba(147, 51, 234, 0.05));
  border-color: rgba(59, 130, 246, 0.3);
}

.progress-bar.voice-design {
  background: linear-gradient(90deg, #8b5cf6, #7c3aed);
}

/* Accessibility Enhancements */
.mode-tab:focus {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.voice-design-input:focus {
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1);
}

/* Animation for Mode Switch */
.voice-design-section {
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}