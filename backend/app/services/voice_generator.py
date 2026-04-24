"""
Voice Generator Service - Standalone TTS Tool

Provides comprehensive text-to-speech functionality independent of characters.
"""

import os
import logging
import json
from pathlib import Path
from app.core.asset_paths import asset_paths
from typing import Optional, Dict, Any, List
import subprocess
import tempfile
import uuid
from datetime import datetime
import sys

logger = logging.getLogger(__name__)

# Add tools directory to path for imports
tools_path = Path(__file__).parent.parent.parent.parent / "tools"
if str(tools_path) not in sys.path:
    sys.path.insert(0, str(tools_path))

# Also add ComfyUI venv to path for Qwen TTS dependencies
comfyui_venv = Path("F:/ComfyUI/.venv")
if comfyui_venv.exists():
    site_packages = comfyui_venv / "Lib" / "site-packages"
    if site_packages.exists() and str(site_packages) not in sys.path:
        sys.path.insert(0, str(site_packages))

try:
    from tts_output_bridge import tts_bridge
    from qwen_tts_service import qwen_tts_service
    QWEN_TTS_AVAILABLE = qwen_tts_service.is_available() if qwen_tts_service else False
    if QWEN_TTS_AVAILABLE:
        logger.info("Qwen TTS service loaded successfully")
    else:
        logger.warning("Qwen TTS service loaded but not available (models not found)")
except ImportError as e:
    tts_bridge = None
    qwen_tts_service = None
    QWEN_TTS_AVAILABLE = False
    logger.warning(f"Qwen TTS service not available: {e}")
except BaseException as e:
    tts_bridge = None
    qwen_tts_service = None
    QWEN_TTS_AVAILABLE = False
    logger.error(f"Error initializing Qwen TTS service: {e}")

class VoiceGeneratorService:
    """Standalone voice generation service"""
    
    def __init__(self):
        self.models_dir = Path("F:/ComfyUI/models/TTS")
        self.tts_app_path = self.models_dir / "tts_app.py"
        self.python_path = Path("F:/ComfyUI/.venv/Scripts/python.exe")
        self.output_dir = Path("assets/generated/audio/voice")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Voice presets for different use cases
        self.voice_presets = {
            "narrator": {
                "name": "Narrator",
                "description": "Professional narrator voice for storytelling",
                "speed": 1.0,
                "pitch": 0.0,
                "emotion": "neutral"
            },
            "character_male": {
                "name": "Male Character",
                "description": "Male character voice for dialogue",
                "speed": 1.1,
                "pitch": -0.2,
                "emotion": "confident"
            },
            "character_female": {
                "name": "Female Character", 
                "description": "Female character voice for dialogue",
                "speed": 1.0,
                "pitch": 0.2,
                "emotion": "friendly"
            },
            "child": {
                "name": "Child Voice",
                "description": "Young character voice",
                "speed": 1.2,
                "pitch": 0.5,
                "emotion": "playful"
            },
            "elder": {
                "name": "Elder Voice",
                "description": "Wise elder character voice",
                "speed": 0.9,
                "pitch": -0.3,
                "emotion": "wise"
            }
        }
        
    def is_available(self) -> bool:
        """Check if voice generator is available"""
        return (
            self.models_dir.exists() and 
            self.tts_app_path.exists() and 
            self.python_path.exists()
        )
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available TTS models"""
        models = []
        
        # Get Qwen TTS models if available
        if QWEN_TTS_AVAILABLE and qwen_tts_service and qwen_tts_service.is_available():
            qwen_models = qwen_tts_service.get_available_models()
            for model in qwen_models:
                models.append({
                    'id': model['id'],
                    'name': model['name'],
                    'info': model['description'],
                    'type': 'qwen_tts',
                    'quality': 'high',
                    'supports_voice_design': model['supports_voice_design'],
                    'available_locally': model['available_locally']
                })
        
        # Fallback to legacy TTS if no Qwen models
        if not models and self.is_available():
            try:
                result = subprocess.run([
                    str(self.python_path), str(self.tts_app_path)
                ], capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'model (' in line:
                            name = line.split('(')[0].strip()
                            info = line.split('(')[1].split(')')[0]
                            models.append({
                                'id': name.lower().replace(' ', '_'),
                                'name': name,
                                'info': info,
                                'type': 'legacy',
                                'quality': 'medium',
                                'supports_voice_design': False,
                                'available_locally': True
                            })
            except Exception as e:
                logger.error(f"Error getting legacy TTS models: {e}")
                
        return models
    
    def get_voice_presets(self) -> Dict[str, Any]:
        """Get available voice presets"""
        presets = self.voice_presets.copy()
        
        # Add Qwen TTS voice design presets if available
        if QWEN_TTS_AVAILABLE and qwen_tts_service and qwen_tts_service.is_available():
            qwen_presets = qwen_tts_service.get_voice_presets()
            for preset_id, preset_data in qwen_presets.items():
                presets[f"qwen_{preset_id}"] = {
                    "name": preset_data["name"],
                    "description": f"Qwen TTS: {preset_data['instruct'][:100]}...",
                    "type": "qwen_voice_design",
                    "instruct": preset_data["instruct"],
                    "language": preset_data["language"]
                }
        
        return presets
    
    def generate_voice(self, 
                      text: str, 
                      voice_prompt: Optional[str] = None,
                      model_id: Optional[str] = None,
                      preset: Optional[str] = None,
                      custom_settings: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Generate voice with advanced options"""
        
        if not text or not text.strip():
            logger.error("Empty text provided")
            return {
                'success': False,
                'message': 'Text cannot be empty'
            }
        
        # Try Qwen TTS first if available
        if QWEN_TTS_AVAILABLE and qwen_tts_service and qwen_tts_service.is_available():
            return self._generate_with_qwen_tts(text, voice_prompt, model_id, preset, custom_settings)
        
        # Fallback to legacy TTS
        if self.is_available():
            return self._generate_with_legacy_tts(text, voice_prompt, model_id, preset, custom_settings)
        
        logger.error("No TTS service available")
        return {
            'success': False,
            'message': 'No TTS service available'
        }
    
    def _generate_with_qwen_tts(self, 
                               text: str, 
                               voice_prompt: Optional[str] = None,
                               model_id: Optional[str] = None,
                               preset: Optional[str] = None,
                               custom_settings: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Generate voice using Qwen TTS"""
        try:
            # Use voice_prompt as instruct for voice design
            instruct = voice_prompt or "Speak in a clear, natural voice with good pacing and intonation."
            language = "English"  # Default language
            qwen_model_id = model_id or "voice_design_1.7b"
            
            # Handle preset
            if preset and preset.startswith("qwen_"):
                preset_name = preset[5:]  # Remove "qwen_" prefix
                result = qwen_tts_service.generate_with_preset(text, preset_name, qwen_model_id)
            else:
                # Apply custom settings
                if custom_settings:
                    if 'language' in custom_settings:
                        language = custom_settings['language']
                    if 'instruct' in custom_settings:
                        instruct = custom_settings['instruct']
                
                result = qwen_tts_service.generate_voice_design(
                    text=text,
                    instruct=instruct,
                    language=language,
                    model_id=qwen_model_id
                )
            
            if result and result.get('success'):
                logger.info(f"Qwen TTS generation successful: {result['audio_path']}")
                return result
            else:
                error_msg = result.get('message', 'Qwen TTS generation failed') if result else 'Unknown error'
                logger.error(f"Qwen TTS generation failed: {error_msg}")
                return {
                    'success': False,
                    'message': error_msg
                }
                
        except Exception as e:
            logger.error(f"Qwen TTS generation error: {e}")
            return {
                'success': False,
                'message': f'Qwen TTS error: {str(e)}'
            }
    
    def _generate_with_legacy_tts(self, 
                                 text: str, 
                                 voice_prompt: Optional[str] = None,
                                 model_id: Optional[str] = None,
                                 preset: Optional[str] = None,
                                 custom_settings: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Generate voice using legacy TTS system"""
        try:
            # Generate unique filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"voice_{timestamp}_{uuid.uuid4().hex[:8]}.wav"
            output_path = self.output_dir / output_filename
            
            # Prepare generation parameters
            generation_params = {
                'text': text,
                'voice_prompt': voice_prompt,
                'model_id': model_id,
                'preset': preset,
                'output_path': str(output_path),
                'timestamp': timestamp
            }
            
            # Apply preset settings if specified
            if preset and preset in self.voice_presets:
                preset_config = self.voice_presets[preset]
                generation_params.update(preset_config)
            
            # Apply custom settings
            if custom_settings:
                generation_params.update(custom_settings)
            
            # Use TTS bridge for proper output handling
            if tts_bridge:
                bridge_result = tts_bridge.generate_with_bridge(text, output_filename)
                
                if bridge_result['success']:
                    logger.info(f"TTS bridge generation successful: {bridge_result['output_path']}")
                    
                    # Create metadata file
                    metadata = {
                        'text': text,
                        'voice_prompt': voice_prompt,
                        'model_id': model_id,
                        'preset': preset,
                        'generation_params': generation_params,
                        'timestamp': timestamp,
                        'file_size': Path(bridge_result['output_path']).stat().st_size if Path(bridge_result['output_path']).exists() else 0,
                        'duration_estimate': len(text) * 0.1  # Rough estimate
                    }
                    
                    metadata_path = Path(bridge_result['output_path']).with_suffix('.json')
                    metadata_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
                    
                    return {
                        'success': True,
                        'audio_path': bridge_result['output_path'],
                        'audio_url': f"/api/v1/voice/audio/{output_filename}",
                        'metadata': metadata,
                        'message': 'Voice generated successfully'
                    }
                else:
                    logger.error(f"TTS bridge generation failed: {bridge_result['message']}")
                    return {
                        'success': False,
                        'message': bridge_result['message']
                    }
            else:
                # Fallback to direct TTS call
                cmd = [
                    str(self.python_path), 
                    str(self.tts_app_path),
                    text
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, 
                                      cwd=str(self.models_dir))
                
                if result.returncode == 0:
                    # Create metadata file
                    metadata = {
                        'text': text,
                        'voice_prompt': voice_prompt,
                        'model_id': model_id,
                        'preset': preset,
                        'generation_params': generation_params,
                        'timestamp': timestamp,
                        'file_size': output_path.stat().st_size if output_path.exists() else 0,
                        'duration_estimate': len(text) * 0.1  # Rough estimate
                    }
                    
                    metadata_path = output_path.with_suffix('.json')
                    metadata_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
                    
                    logger.info(f"Voice generation successful: {output_path}")
                    
                    return {
                        'success': True,
                        'audio_path': str(output_path),
                        'audio_url': f"/api/v1/voice/audio/{output_filename}",
                        'metadata': metadata,
                        'message': 'Voice generated successfully'
                    }
                else:
                    logger.error(f"Voice generation failed: {result.stderr}")
                    return {
                        'success': False,
                        'message': f'Generation failed: {result.stderr}'
                    }
                
        except Exception as e:
            logger.error(f"Legacy TTS generation error: {e}")
            return {
                'success': False,
                'message': f'Generation error: {str(e)}'
            }
    
    def get_generation_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent voice generations"""
        try:
            history = []
            
            # Scan output directory for generated files
            for audio_file in sorted(self.output_dir.glob("*.wav"), 
                                   key=lambda x: x.stat().st_mtime, reverse=True):
                if len(history) >= limit:
                    break
                
                metadata_file = audio_file.with_suffix('.json')
                
                if metadata_file.exists():
                    try:
                        metadata = json.loads(metadata_file.read_text(encoding='utf-8'))
                        metadata['audio_filename'] = audio_file.name
                        metadata['audio_url'] = f"/api/v1/voice/audio/{audio_file.name}"
                        history.append(metadata)
                    except Exception as e:
                        logger.warning(f"Failed to read metadata for {audio_file}: {e}")
                        
            return history
            
        except Exception as e:
            logger.error(f"Error getting generation history: {e}")
            return []
    
    def delete_generation(self, filename: str) -> bool:
        """Delete a generated voice file"""
        try:
            audio_path = self.output_dir / filename
            metadata_path = audio_path.with_suffix('.json')
            
            if audio_path.exists():
                audio_path.unlink()
            if metadata_path.exists():
                metadata_path.unlink()
                
            return True
            
        except Exception as e:
            logger.error(f"Error deleting generation {filename}: {e}")
            return False
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get comprehensive service status"""
        models = self.get_available_models()
        history = self.get_generation_history(5)  # Last 5 generations
        
        # Get Qwen TTS status if available
        qwen_status = {}
        if QWEN_TTS_AVAILABLE and qwen_tts_service:
            qwen_status = qwen_tts_service.get_service_status()
        
        return {
            'available': self.is_available() or (QWEN_TTS_AVAILABLE and qwen_tts_service and qwen_tts_service.is_available()),
            'qwen_tts_available': QWEN_TTS_AVAILABLE and qwen_tts_service and qwen_tts_service.is_available(),
            'legacy_tts_available': self.is_available(),
            'models_count': len(models),
            'models': models,
            'presets': self.get_voice_presets(),
            'recent_generations': len(history),
            'output_directory': str(self.output_dir),
            'models_directory': str(self.models_dir),
            'qwen_status': qwen_status
        }
    
    def generate_voice_design(self, 
                            text: str,
                            instruct: str,
                            language: str = "English",
                            model_id: str = "voice_design_1.7b") -> Optional[Dict[str, Any]]:
        """Generate voice using Qwen TTS voice design with fallback error handling"""
        
        # Root cause: Qwen TTS model loading fails due to pad_token_id configuration issue
        # Fix: Provide graceful fallback with detailed error information
        
        if not QWEN_TTS_AVAILABLE or not qwen_tts_service:
            return {
                'success': False,
                'message': 'Qwen TTS service not available - library not installed',
                'error_type': 'service_unavailable',
                'fallback_suggestion': 'Install Qwen TTS dependencies or use alternative TTS'
            }
        
        if not qwen_tts_service.is_available():
            return {
                'success': False,
                'message': 'Qwen TTS service not available - models not found',
                'error_type': 'models_unavailable',
                'fallback_suggestion': 'Download Qwen TTS models or check model paths'
            }
        
        try:
            # Try Qwen TTS generation
            result = qwen_tts_service.generate_voice_design(text, instruct, language, model_id)
            
            if result and result.get('success'):
                return result
            else:
                # Qwen TTS failed, provide detailed error
                error_msg = result.get('message', 'Unknown error') if result else 'No result returned'
                logger.error(f"Qwen TTS generation failed: {error_msg}")
                
                return {
                    'success': False,
                    'message': f'Qwen TTS generation failed: {error_msg}',
                    'error_type': 'generation_failed',
                    'fallback_suggestion': 'Check Qwen TTS model configuration and logs',
                    'original_error': error_msg
                }
                
        except Exception as e:
            logger.error(f"Qwen TTS generation exception: {e}")
            
            # Check if it's the known pad_token_id error
            if 'pad_token_id' in str(e):
                return {
                    'success': False,
                    'message': 'Qwen TTS model configuration error (pad_token_id missing)',
                    'error_type': 'config_error',
                    'fallback_suggestion': 'Run tools/fix_qwen_tts_pad_token_config.py to fix model config',
                    'technical_details': str(e)
                }
            else:
                return {
                    'success': False,
                    'message': f'Voice generation failed: {str(e)}',
                    'error_type': 'exception',
                    'fallback_suggestion': 'Check backend logs for detailed error information',
                    'technical_details': str(e)
                }
    
    def generate_batch_voice_design(self,
                                  texts: List[str],
                                  instructs: List[str],
                                  languages: List[str],
                                  model_id: str = "voice_design_1.7b") -> Optional[Dict[str, Any]]:
        """Generate multiple voices in batch using Qwen TTS"""
        if not QWEN_TTS_AVAILABLE or not qwen_tts_service or not qwen_tts_service.is_available():
            return {
                'success': False,
                'message': 'Qwen TTS batch generation not available'
            }
        
        return qwen_tts_service.generate_batch_voice_design(texts, instructs, languages, model_id)

# Global voice generator service instance
voice_generator = VoiceGeneratorService()
