"""
TTS Service for LexQuest Design Studio
"""

import os
import logging
from pathlib import Path
from app.core.asset_paths import asset_paths
from typing import Optional, Dict, Any, List
import subprocess
import tempfile
import uuid

logger = logging.getLogger(__name__)

class TTSService:
    """Text-to-Speech service using local models"""
    
    def __init__(self):
        self.models_dir = Path("F:/ComfyUI/models/TTS")
        self.tts_app_path = self.models_dir / "tts_app.py"
        self.python_path = Path("F:/ComfyUI/.venv/Scripts/python.exe")
        
    def is_available(self) -> bool:
        """Check if TTS service is available"""
        return (
            self.models_dir.exists() and 
            self.tts_app_path.exists() and 
            self.python_path.exists()
        )
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available TTS models"""
        if not self.is_available():
            return []
        
        try:
            result = subprocess.run([
                str(self.python_path), str(self.tts_app_path)
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                models = []
                for line in result.stdout.split('\n'):
                    if 'model (' in line:
                        name = line.split('(')[0].strip()
                        info = line.split('(')[1].split(')')[0]
                        models.append({
                            'name': name,
                            'info': info,
                            'type': 'local'
                        })
                return models
            else:
                logger.error(f"Failed to get models: {result.stderr}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting TTS models: {e}")
            return []
    
    def synthesize_speech(self, text: str, voice_id: Optional[str] = None) -> Optional[str]:
        """Synthesize speech from text"""
        if not self.is_available():
            logger.error("TTS service not available")
            return None
        
        try:
            # Use unified assets directory structure
            output_dir = Path("assets/generated/audio/voice")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_filename = f"tts_{uuid.uuid4().hex[:8]}.wav"
            output_path = output_dir / output_filename
            
            result = subprocess.run([
                str(self.python_path), 
                str(self.tts_app_path),
                text
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                logger.info(f"TTS synthesis successful")
                return str(output_path)
            else:
                logger.error(f"TTS synthesis failed: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"TTS synthesis error: {e}")
            return None
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get TTS service status"""
        models = self.get_available_models()
        
        return {
            'available': self.is_available(),
            'models_count': len(models),
            'models': models,
            'models_dir': str(self.models_dir)
        }

# Global TTS service instance
tts_service = TTSService()
