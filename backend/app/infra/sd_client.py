"""
SD Client - низкоуровневые клиенты для Stable Diffusion API.

ВАЖНО: Не используйте build_sd_client() напрямую!
Все генерации должны идти через sd_request_layer.get_sd_layer()
для автоматического перевода промптов.
"""
from __future__ import annotations

import base64
import logging
import os
from io import BytesIO
from typing import List, Optional, Union

import httpx
from PIL import Image, ImageDraw

from app.core.config import get_settings
from app.utils.sd_provider import normalize_sd_provider
from app.utils.sd_tokens import extract_lora_tokens, merge_loras, format_lora_tokens, prepend_tokens


class BaseSdClient:
    """Base class for SD clients."""

    capabilities: set[str] = set()
    provider_name: str = "unknown"

    def generate_images(
        self,
        prompt: str,
        style: str | None,
        num_images: int,
        width: int = 640,
        height: int = 480,
        negative_prompt: str | None = None,
        cfg_scale: float | None = None,
        steps: int | None = None,
        seed: int | None = None,
        sampler: str | None = None,
        scheduler: str | None = None,
        model_id: str | None = None,
        vae_id: str | None = None,
        clip_id: str | None = None,
        loader_type: str = "standard",
        loras: Optional[List[dict]] = None,
        init_images: Optional[List[Union[bytes, str]]] = None,
        denoising_strength: Optional[float] = None,
        alwayson_scripts: Optional[dict] = None,
        override_settings: Optional[dict] = None,
        mask: Optional[Union[bytes, str]] = None,
        mask_blur: Optional[int] = None,
        inpaint_full_res: Optional[bool] = None,
        inpaint_full_res_padding: Optional[int] = None,
        workflow_set: Optional[str] = None,
        workflow_task: Optional[str] = None,
    ) -> List[bytes]:
        raise NotImplementedError

    def supports(self, feature: str) -> bool:
        return feature in self.capabilities

    def controlnet_detect(
        self,
        module: str,
        images: List[Union[bytes, str]],
        processor_res: int = 512,
        threshold_a: float = 64,
        threshold_b: float = 64,
    ) -> List[bytes]:
        raise NotImplementedError

    def get_controlnet_models(self) -> List[str]:
        """Get list of available ControlNet models."""
        return []

    def get_controlnet_modules(self) -> List[str]:
        """Get list of available ControlNet preprocessor modules."""
        return []

    def find_controlnet_model(self, module_type: str) -> Optional[str]:
        """Find a matching ControlNet model for the given module type."""
        return None

    def refresh_controlnet_models(self) -> List[str]:
        """Force refresh ControlNet models cache."""
        return []

    def get_sd_models(self) -> List[dict]:
        """Get list of available SD checkpoint models."""
        return []

    def get_vae_models(self) -> List[str]:
        """Get list of available VAE models."""
        return []

    def get_samplers(self) -> List[dict]:
        """Get list of available samplers."""
        return []

    def get_schedulers(self) -> List[dict]:
        """Get list of available schedulers."""
        return []

    def get_upscalers(self) -> List[dict]:
        """Get list of available upscalers."""
        return []

    def get_loras(self) -> List[dict]:
        """Get list of available LoRA models."""
        return []

    def get_styles(self) -> List[dict]:
        """Get list of available prompt styles."""
        return []

    def get_embeddings(self) -> List[dict]:
        """Get list of available textual inversion embeddings."""
        return []

    def interrogate(self, image: Union[bytes, str], model: str = "clip") -> dict:
        """Interrogate an image to produce descriptive tags."""
        return {}

    def create_embedding(
        self,
        name: str,
        num_vectors_per_token: int = 1,
        overwrite: bool = False,
        init_text: Optional[str] = None,
    ) -> dict:
        """Create a textual inversion embedding."""
        return {}

    def refresh_embeddings(self) -> bool:
        """Refresh embedding list."""
        return False

    def get_scripts(self) -> dict:
        """Get available script info from SD WebUI."""
        return {}

    def get_options(self) -> dict:
        """Get current SD options/settings."""
        return {}

    def set_options(self, options: dict) -> bool:
        """Set SD options/settings."""
        return False

    def get_all_options(self) -> dict:
        """Get all available options for dropdowns."""
        return {
            "sd_models": self.get_sd_models(),
            "vae_models": self.get_vae_models(),
            "samplers": self.get_samplers(),
            "schedulers": self.get_schedulers(),
            "upscalers": self.get_upscalers(),
            "loras": self.get_loras(),
            "styles": self.get_styles(),
            "embeddings": self.get_embeddings(),
            "controlnet_models": self.get_controlnet_models(),
            "controlnet_modules": self.get_controlnet_modules(),
        }


def _encode_image(value: Union[bytes, str]) -> str:
    if isinstance(value, str):
        return value.split(",", 1)[1] if value.startswith("data:") else value
    return base64.b64encode(value).decode()


class HttpSdClient(BaseSdClient):
    """HTTP client for real Stable Diffusion WebUI API."""

    capabilities = {
        "txt2img",
        "img2img",
        "inpaint",
        "alwayson_scripts",
        "controlnet_detect",
        "interrogate",
        "models",
        "vae",
        "samplers",
        "schedulers",
        "upscalers",
        "loras",
        "styles",
        "embeddings",
        "options",
    }
    provider_name = "a1111"
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.logger = logging.getLogger(__name__)
        self._cn_models_cache: Optional[List[str]] = None
        self._cn_modules_cache: Optional[List[str]] = None

    def get_controlnet_models(self, force_refresh: bool = False) -> List[str]:
        """Get list of available ControlNet models."""
        if self._cn_models_cache is not None and not force_refresh:
            return self._cn_models_cache
        
        try:
            url = f"{self.base_url}/controlnet/model_list"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            
            models = data.get("model_list", [])
            # Filter out "None" placeholder
            models = [m for m in models if m and m.lower() != "none"]
            self._cn_models_cache = models
            self.logger.info(f"ControlNet models available: {len(models)} - {models}")
            return models
        except Exception as e:
            self.logger.warning(f"Failed to get ControlNet models: {e}")
            return []

    def refresh_controlnet_models(self) -> List[str]:
        """Force refresh ControlNet models cache."""
        self._cn_models_cache = None
        self._cn_modules_cache = None
        return self.get_controlnet_models(force_refresh=True)

    def get_controlnet_modules(self) -> List[str]:
        """Get list of available ControlNet preprocessor modules."""
        if self._cn_modules_cache is not None:
            return self._cn_modules_cache
        
        try:
            url = f"{self.base_url}/controlnet/module_list"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            
            modules = data.get("module_list", [])
            self._cn_modules_cache = modules
            self.logger.info(f"ControlNet modules available: {len(modules)}")
            return modules
        except Exception as e:
            self.logger.warning(f"Failed to get ControlNet modules: {e}")
            return []

    def find_controlnet_model(self, module_type: str) -> Optional[str]:
        """Find a matching ControlNet model for the given module type."""
        models = self.get_controlnet_models()
        if not models:
            return None
        
        # Map module types to model name patterns
        patterns = {
            "openpose": ["openpose", "pose"],
            "openpose_full": ["openpose", "pose"],
            "canny": ["canny"],
            "depth": ["depth"],
            "depth_midas": ["depth"],
            "lineart": ["lineart"],
            "lineart_anime": ["lineart_anime", "lineart"],
            "softedge": ["softedge", "hed"],
            "scribble": ["scribble"],
            "seg": ["seg"],
            "ip-adapter": ["ip-adapter", "ipadapter"],
            "ip-adapter-face": ["ip-adapter-face", "ipadapter-face", "ip-adapter"],
            "reference": ["reference"],
        }
        
        search_patterns = patterns.get(module_type.lower().replace("_", "-"), [module_type])
        
        for pattern in search_patterns:
            for model in models:
                if pattern.lower() in model.lower():
                    return model
        
        return None

    def get_sd_models(self) -> List[dict]:
        """Get list of available SD checkpoint models."""
        try:
            url = f"{self.base_url}/sdapi/v1/sd-models"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            
            models = []
            for item in data:
                models.append({
                    "title": item.get("title", ""),
                    "model_name": item.get("model_name", ""),
                    "hash": item.get("hash", ""),
                    "sha256": item.get("sha256", ""),
                    "filename": item.get("filename", ""),
                })
            self.logger.info(f"SD models available: {len(models)}")
            return models
        except Exception as e:
            self.logger.warning(f"Failed to get SD models: {e}")
            return []

    def get_vae_models(self) -> List[str]:
        """Get list of available VAE models."""
        try:
            url = f"{self.base_url}/sdapi/v1/sd-vae"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            
            vae_list = [item.get("model_name", "") for item in data if item.get("model_name")]
            # Add special options
            vae_list = ["Automatic", "None"] + vae_list
            self.logger.info(f"VAE models available: {len(vae_list)}")
            return vae_list
        except Exception as e:
            self.logger.warning(f"Failed to get VAE models: {e}")
            return ["Automatic", "None"]

    def get_samplers(self) -> List[dict]:
        """Get list of available samplers."""
        try:
            url = f"{self.base_url}/sdapi/v1/samplers"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            
            samplers = []
            for item in data:
                samplers.append({
                    "name": item.get("name", ""),
                    "aliases": item.get("aliases", []),
                })
            self.logger.info(f"Samplers available: {len(samplers)}")
            return samplers
        except Exception as e:
            self.logger.warning(f"Failed to get samplers: {e}")
            return []

    def get_schedulers(self) -> List[dict]:
        """Get list of available schedulers."""
        try:
            url = f"{self.base_url}/sdapi/v1/schedulers"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            
            schedulers = []
            for item in data:
                schedulers.append({
                    "name": item.get("name", ""),
                    "label": item.get("label", item.get("name", "")),
                })
            self.logger.info(f"Schedulers available: {len(schedulers)}")
            return schedulers
        except Exception as e:
            self.logger.warning(f"Failed to get schedulers: {e}")
            return []

    def get_upscalers(self) -> List[dict]:
        """Get list of available upscalers."""
        try:
            url = f"{self.base_url}/sdapi/v1/upscalers"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            
            upscalers = []
            for item in data:
                upscalers.append({
                    "name": item.get("name", ""),
                    "model_name": item.get("model_name"),
                    "model_path": item.get("model_path"),
                    "model_url": item.get("model_url"),
                    "scale": item.get("scale"),
                })
            self.logger.info(f"Upscalers available: {len(upscalers)}")
            return upscalers
        except Exception as e:
            self.logger.warning(f"Failed to get upscalers: {e}")
            return []

    def get_loras(self) -> List[dict]:
        """Get list of available LoRA models."""
        try:
            url = f"{self.base_url}/sdapi/v1/loras"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            
            loras = []
            for item in data:
                loras.append({
                    "name": item.get("name", ""),
                    "alias": item.get("alias", ""),
                    "path": item.get("path", ""),
                })
            self.logger.info(f"LoRAs available: {len(loras)}")
            return loras
        except Exception as e:
            self.logger.warning(f"Failed to get LoRAs: {e}")
            return []

    def get_styles(self) -> List[dict]:
        """Get list of available prompt styles."""
        try:
            url = f"{self.base_url}/sdapi/v1/prompt-styles"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            
            styles = []
            for item in data:
                styles.append({
                    "name": item.get("name", ""),
                    "prompt": item.get("prompt", ""),
                    "negative_prompt": item.get("negative_prompt", ""),
                })
            self.logger.info(f"Styles available: {len(styles)}")
            return styles
        except Exception as e:
            self.logger.warning(f"Failed to get styles: {e}")
            return []

    def get_embeddings(self) -> List[dict]:
        """Get list of available textual inversion embeddings."""
        try:
            url = f"{self.base_url}/sdapi/v1/embeddings"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
            embeddings = []
            for name, info in (data.get("loaded", {}) or {}).items():
                embeddings.append({
                    "name": name,
                    "vectors": info.get("vectors"),
                    "step": info.get("step"),
                })
            return embeddings
        except Exception as e:
            self.logger.warning(f"Failed to get embeddings: {e}")
            return []

    def interrogate(self, image: Union[bytes, str], model: str = "clip") -> dict:
        """Interrogate an image via SD WebUI API."""
        payload = {
            "image": _encode_image(image),
            "model": model,
        }
        url = f"{self.base_url}/sdapi/v1/interrogate"
        with httpx.Client(timeout=60) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    def create_embedding(
        self,
        name: str,
        num_vectors_per_token: int = 1,
        overwrite: bool = False,
        init_text: Optional[str] = None,
    ) -> dict:
        """Create a textual inversion embedding via SD WebUI API."""
        payload = {
            "name": name,
            "num_vectors_per_token": num_vectors_per_token,
            "overwrite_old": overwrite,
        }
        if init_text:
            payload["init_text"] = init_text
        url = f"{self.base_url}/sdapi/v1/create/embedding"
        with httpx.Client(timeout=60) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    def refresh_embeddings(self) -> bool:
        """Refresh embedding list."""
        try:
            url = f"{self.base_url}/sdapi/v1/refresh-embeddings"
            with httpx.Client(timeout=60) as client:
                response = client.post(url)
                response.raise_for_status()
            self.logger.info("Refreshed embeddings")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to refresh embeddings: {e}")
            return False

    def get_scripts(self) -> dict:
        """Get available script info from SD WebUI."""
        try:
            url = f"{self.base_url}/sdapi/v1/script-info"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            self.logger.warning(f"Failed to get script info: {e}")
            return {}

    def get_options(self) -> dict:
        """Get current SD options/settings."""
        try:
            url = f"{self.base_url}/sdapi/v1/options"
            with httpx.Client(timeout=30) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            self.logger.warning(f"Failed to get options: {e}")
            return {}

    def set_options(self, options: dict) -> bool:
        """Set SD options/settings."""
        try:
            url = f"{self.base_url}/sdapi/v1/options"
            with httpx.Client(timeout=30) as client:
                response = client.post(url, json=options)
                response.raise_for_status()
            self.logger.info(f"Set SD options: {list(options.keys())}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to set options: {e}")
            return False

    def refresh_models(self) -> bool:
        """Refresh SD models list."""
        try:
            url = f"{self.base_url}/sdapi/v1/refresh-checkpoints"
            with httpx.Client(timeout=60) as client:
                response = client.post(url)
                response.raise_for_status()
            self.logger.info("Refreshed SD checkpoints")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to refresh checkpoints: {e}")
            return False

    def refresh_vae(self) -> bool:
        """Refresh VAE models list."""
        try:
            url = f"{self.base_url}/sdapi/v1/refresh-vae"
            with httpx.Client(timeout=60) as client:
                response = client.post(url)
                response.raise_for_status()
            self.logger.info("Refreshed VAE models")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to refresh VAE: {e}")
            return False

    def refresh_loras(self) -> bool:
        """Refresh LoRA models list."""
        try:
            url = f"{self.base_url}/sdapi/v1/refresh-loras"
            with httpx.Client(timeout=60) as client:
                response = client.post(url)
                response.raise_for_status()
            self.logger.info("Refreshed LoRA models")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to refresh LoRAs: {e}")
            return False

    def generate_images(
        self,
        prompt: str,
        style: str | None,
        num_images: int,
        width: int = 640,
        height: int = 480,
        negative_prompt: str | None = None,
        cfg_scale: float | None = None,
        steps: int | None = None,
        seed: int | None = None,
        sampler: str | None = None,
        scheduler: str | None = None,
        model_id: str | None = None,
        vae_id: str | None = None,
        clip_id: str | None = None,
        loader_type: str = "standard",
        loras: Optional[List[dict]] = None,
        init_images: Optional[List[Union[bytes, str]]] = None,
        denoising_strength: Optional[float] = None,
        alwayson_scripts: Optional[dict] = None,
        override_settings: Optional[dict] = None,
        mask: Optional[Union[bytes, str]] = None,
        mask_blur: Optional[int] = None,
        inpaint_full_res: Optional[bool] = None,
        inpaint_full_res_padding: Optional[int] = None,
        workflow_set: Optional[str] = None,
        workflow_task: Optional[str] = None,
    ) -> List[bytes]:
        prompt_text = prompt if style is None else f"{prompt}, style::{style}"
        cleaned_prompt, prompt_loras = extract_lora_tokens(prompt_text)
        merged_loras = merge_loras(prompt_loras, loras)
        if merged_loras:
            prompt_text = prepend_tokens(cleaned_prompt, format_lora_tokens(merged_loras))
        else:
            prompt_text = cleaned_prompt

        override_settings_final = dict(override_settings or {})
        if model_id:
            override_settings_final.setdefault("sd_model_checkpoint", model_id)
        if vae_id:
            override_settings_final.setdefault("sd_vae", vae_id)
        payload = {
            "prompt": prompt_text,
            "negative_prompt": negative_prompt,
            "cfg_scale": cfg_scale,
            "steps": steps,
            "width": width,
            "height": height,
            "batch_size": num_images,
            "n_iter": 1,
            "seed": seed if seed is not None else -1,
        }
        if alwayson_scripts:
            payload["alwayson_scripts"] = alwayson_scripts
        if override_settings_final:
            payload["override_settings"] = override_settings_final
        if sampler:
            payload["sampler_name"] = sampler
        if scheduler:
            payload["scheduler"] = scheduler
        url = f"{self.base_url}/sdapi/v1/txt2img"

        if init_images:
            encoded: List[str] = []
            for img in init_images:
                encoded.append(_encode_image(img))
            payload["init_images"] = encoded
            payload["denoising_strength"] = denoising_strength if denoising_strength is not None else 0.45
            if mask is not None:
                payload["mask"] = _encode_image(mask)
            if mask_blur is not None:
                payload["mask_blur"] = mask_blur
            if inpaint_full_res is not None:
                payload["inpaint_full_res"] = inpaint_full_res
            if inpaint_full_res_padding is not None:
                payload["inpaint_full_res_padding"] = inpaint_full_res_padding
            url = f"{self.base_url}/sdapi/v1/img2img"

        self.logger.info(f"SD Request: {url}, prompt='{prompt[:50]}...', batch={num_images}")
        
        with httpx.Client(timeout=120) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        images: List[bytes] = []
        for img_b64 in data.get("images", []):
            if "," in img_b64:
                img_b64 = img_b64.split(",", 1)[1]
            images.append(base64.b64decode(img_b64))
        
        self.logger.info(f"SD Response: {len(images)} images generated")
        return images

    def controlnet_detect(
        self,
        module: str,
        images: List[Union[bytes, str]],
        processor_res: int = 512,
        threshold_a: float = 64,
        threshold_b: float = 64,
    ) -> List[bytes]:
        payload = {
            "controlnet_input_images": [_encode_image(img) for img in images],
            "controlnet_module": module,
            "controlnet_processor_res": processor_res,
            "controlnet_threshold_a": threshold_a,
            "controlnet_threshold_b": threshold_b,
        }
        url = f"{self.base_url}/controlnet/detect"
        self.logger.info(f"ControlNet detect: {module}, images={len(images)}")
        with httpx.Client(timeout=120) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        raw = data.get("images") or data.get("image") or data.get("result") or []
        if isinstance(raw, str):
            raw = [raw]
        decoded: List[bytes] = []
        for img_b64 in raw:
            if not isinstance(img_b64, str):
                continue
            if "," in img_b64:
                img_b64 = img_b64.split(",", 1)[1]
            try:
                decoded.append(base64.b64decode(img_b64))
            except Exception:
                continue
        if decoded:
            return decoded

        # Fallback: return original inputs as bytes if no processed images were provided.
        fallback: List[bytes] = []
        for img in images:
            if isinstance(img, str):
                try:
                    fallback.append(base64.b64decode(img.split(",", 1)[1] if img.startswith("data:") else img))
                except Exception:
                    continue
            else:
                fallback.append(img)
        return fallback


class PoeSdClient(BaseSdClient):
    """OpenAI-compatible Poe image client."""

    capabilities = {"txt2img", "img2img", "models"}
    provider_name = "poe_api"

    def __init__(self, base_url: str, api_key: str, model: str, *, quality: str = "low"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip() or "GPT-Image-1"
        self.quality = (quality or "low").strip().lower() or "low"
        self.logger = logging.getLogger(__name__)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
        }

    def _resolve_size(self, width: int, height: int) -> str:
        ratio = (width or 1024) / max(height or 1024, 1)
        options = {
            "1024x1024": 1.0,
            "1536x1024": 1.5,
            "1024x1536": 1024 / 1536,
        }
        return min(options, key=lambda item: abs(options[item] - ratio))

    def _resolve_quality(self, steps: Optional[int]) -> str:
        if steps is None:
            return self.quality
        if steps >= 36:
            return "high"
        if steps >= 24:
            return "medium"
        return "low"

    def _compose_prompt(self, prompt: str, style: str | None, negative_prompt: str | None) -> str:
        parts = [prompt.strip()]
        if style:
            parts.append(f"Style guidance: {style.strip()}")
        if negative_prompt:
            parts.append(f"Avoid: {negative_prompt.strip()}")
        return "\n".join(part for part in parts if part)

    def _download_remote_image(self, url: str) -> bytes:
        with httpx.Client(timeout=120) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content

    def _parse_image_response(self, data: dict) -> List[bytes]:
        images: List[bytes] = []
        for item in data.get("data", []):
            if not isinstance(item, dict):
                continue
            b64_json = item.get("b64_json")
            if isinstance(b64_json, str) and b64_json:
                images.append(base64.b64decode(b64_json))
                continue
            url = item.get("url")
            if isinstance(url, str) and url:
                images.append(self._download_remote_image(url))
        if not images:
            raise RuntimeError("Poe image API returned no images")
        return images

    def generate_images(
        self,
        prompt: str,
        style: str | None,
        num_images: int,
        width: int = 640,
        height: int = 480,
        negative_prompt: str | None = None,
        cfg_scale: float | None = None,
        steps: int | None = None,
        seed: int | None = None,
        sampler: str | None = None,
        scheduler: str | None = None,
        model_id: str | None = None,
        vae_id: str | None = None,
        clip_id: str | None = None,
        loader_type: str = "standard",
        loras: Optional[List[dict]] = None,
        init_images: Optional[List[Union[bytes, str]]] = None,
        denoising_strength: Optional[float] = None,
        alwayson_scripts: Optional[dict] = None,
        override_settings: Optional[dict] = None,
        mask: Optional[Union[bytes, str]] = None,
        mask_blur: Optional[int] = None,
        inpaint_full_res: Optional[bool] = None,
        inpaint_full_res_padding: Optional[int] = None,
        workflow_set: Optional[str] = None,
        workflow_task: Optional[str] = None,
    ) -> List[bytes]:
        if not self.api_key:
            raise RuntimeError("Poe image API key is missing")

        payload = {
            "model": (model_id or self.model).strip() or self.model,
            "prompt": self._compose_prompt(prompt, style, negative_prompt),
            "n": max(1, min(num_images or 1, 4)),
            "size": self._resolve_size(width, height),
            "quality": self._resolve_quality(steps),
            "response_format": "b64_json",
        }
        if seed is not None:
            payload["seed"] = seed

        self.logger.info(
            "Poe image request: model=%s size=%s quality=%s n=%s",
            payload["model"],
            payload["size"],
            payload["quality"],
            payload["n"],
        )

        with httpx.Client(timeout=180) as client:
            if init_images:
                first_image = init_images[0]
                if isinstance(first_image, str):
                    encoded = first_image.split(",", 1)[1] if first_image.startswith("data:") else first_image
                    image_bytes = base64.b64decode(encoded)
                else:
                    image_bytes = first_image
                response = client.post(
                    f"{self.base_url}/images/edits",
                    headers=self._headers(),
                    data={key: str(value) for key, value in payload.items() if key != "response_format"},
                    files={"image": ("image.png", image_bytes, "image/png")},
                )
            else:
                response = client.post(
                    f"{self.base_url}/images/generations",
                    headers=self._headers(),
                    json=payload,
                )
            response.raise_for_status()
            data = response.json()

        return self._parse_image_response(data)

    def get_sd_models(self) -> List[dict]:
        model = self.model
        return [{"title": model, "model_name": model, "filename": model}]

    def get_options(self) -> dict:
        return {
            "sd_model_checkpoint": self.model,
            "poe_quality": self.quality,
        }


class MockSdClient(BaseSdClient):
    """Mock client for testing without real SD."""

    capabilities = {
        "txt2img",
        "img2img",
        "inpaint",
        "alwayson_scripts",
        "controlnet_detect",
        "interrogate",
        "models",
        "vae",
        "samplers",
        "schedulers",
        "upscalers",
        "loras",
        "styles",
        "embeddings",
        "options",
    }
    provider_name = "mock"
    
    def generate_images(
        self,
        prompt: str,
        style: str | None,
        num_images: int,
        width: int = 640,
        height: int = 480,
        negative_prompt: str | None = None,
        cfg_scale: float | None = None,
        steps: int | None = None,
        seed: int | None = None,
        sampler: str | None = None,
        scheduler: str | None = None,
        model_id: str | None = None,
        vae_id: str | None = None,
        clip_id: str | None = None,
        loader_type: str = "standard",
        loras: Optional[List[dict]] = None,
        init_images: Optional[List[Union[bytes, str]]] = None,
        denoising_strength: Optional[float] = None,
        alwayson_scripts: Optional[dict] = None,
        override_settings: Optional[dict] = None,
        mask: Optional[Union[bytes, str]] = None,
        mask_blur: Optional[int] = None,
        inpaint_full_res: Optional[bool] = None,
        inpaint_full_res_padding: Optional[int] = None,
        workflow_set: Optional[str] = None,
        workflow_task: Optional[str] = None,
    ) -> List[bytes]:
        images: List[bytes] = []
        for idx in range(num_images):
            img = Image.new("RGB", (width, height), color=(40 + idx * 10, 80, 140))
            draw = ImageDraw.Draw(img)
            label = (
                f"MOCK: {prompt[:35]}\n"
                f"style={style or 'default'}\n"
                f"cfg={cfg_scale or 7} steps={steps or 20}\n"
                f"variant={idx + 1}/{num_images}"
            )
            draw.text((16, 16), label, fill=(255, 255, 255))
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            images.append(buffer.getvalue())
        return images

    def controlnet_detect(
        self,
        module: str,
        images: List[Union[bytes, str]],
        processor_res: int = 512,
        threshold_a: float = 64,
        threshold_b: float = 64,
    ) -> List[bytes]:
        decoded: List[bytes] = []
        for img in images:
            if isinstance(img, str):
                try:
                    decoded.append(base64.b64decode(img.split(",", 1)[1] if img.startswith("data:") else img))
                except Exception:
                    continue
            else:
                decoded.append(img)
        return decoded


class RouterSdClient(BaseSdClient):
    """Route SD requests to a primary provider, with optional fallback."""

    def __init__(
        self,
        primary: BaseSdClient,
        fallback: Optional[BaseSdClient] = None,
        *,
        primary_name: str = "primary",
        fallback_name: str = "fallback",
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.primary_name = primary_name
        self.fallback_name = fallback_name
        self.provider_name = getattr(primary, "provider_name", primary_name)
        self.logger = logging.getLogger(__name__)

    def _supports(self, client: BaseSdClient, features: set[str]) -> bool:
        return all(client.supports(feature) for feature in features)

    def supports(self, feature: str) -> bool:
        if self.primary.supports(feature):
            return True
        return bool(self.fallback and self.fallback.supports(feature))

    def _pick(self, features: set[str], *, purpose: str) -> BaseSdClient:
        if self._supports(self.primary, features):
            return self.primary
        if self.fallback and self._supports(self.fallback, features):
            missing = sorted(feature for feature in features if not self.primary.supports(feature))
            self.logger.info(
                "Routing SD request to fallback provider for %s (missing: %s)",
                purpose,
                ", ".join(missing) if missing else "unknown",
            )
            return self.fallback
        missing = sorted(feature for feature in features if not self.primary.supports(feature))
        raise RuntimeError(
            f"SD provider '{self.primary_name}' lacks features for {purpose}: {', '.join(missing) or 'unknown'}"
        )

    def generate_images(
        self,
        prompt: str,
        style: str | None,
        num_images: int,
        width: int = 640,
        height: int = 480,
        negative_prompt: str | None = None,
        cfg_scale: float | None = None,
        steps: int | None = None,
        seed: int | None = None,
        sampler: str | None = None,
        scheduler: str | None = None,
        model_id: str | None = None,
        vae_id: str | None = None,
        clip_id: str | None = None,
        loader_type: str = "standard",
        loras: Optional[List[dict]] = None,
        init_images: Optional[List[Union[bytes, str]]] = None,
        denoising_strength: Optional[float] = None,
        alwayson_scripts: Optional[dict] = None,
        override_settings: Optional[dict] = None,
        mask: Optional[Union[bytes, str]] = None,
        mask_blur: Optional[int] = None,
        inpaint_full_res: Optional[bool] = None,
        inpaint_full_res_padding: Optional[int] = None,
        workflow_set: Optional[str] = None,
        workflow_task: Optional[str] = None,
    ) -> List[bytes]:
        features = {"txt2img"}
        if init_images:
            features.add("img2img")
        if mask is not None or mask_blur is not None or inpaint_full_res is not None or inpaint_full_res_padding is not None:
            features.add("inpaint")
        if alwayson_scripts or override_settings:
            features.add("alwayson_scripts")

        client = self._pick(features, purpose="generation")
        return client.generate_images(
            prompt=prompt,
            style=style,
            num_images=num_images,
            width=width,
            height=height,
            negative_prompt=negative_prompt,
            cfg_scale=cfg_scale,
            steps=steps,
            seed=seed,
            sampler=sampler,
            scheduler=scheduler,
            model_id=model_id,
            vae_id=vae_id,
            clip_id=clip_id,
            loader_type=loader_type,
            loras=loras,
            init_images=init_images,
            denoising_strength=denoising_strength,
            alwayson_scripts=alwayson_scripts,
            override_settings=override_settings,
            mask=mask,
            mask_blur=mask_blur,
            inpaint_full_res=inpaint_full_res,
            inpaint_full_res_padding=inpaint_full_res_padding,
            workflow_set=workflow_set,
            workflow_task=workflow_task,
        )

    def controlnet_detect(
        self,
        module: str,
        images: List[Union[bytes, str]],
        processor_res: int = 512,
        threshold_a: float = 64,
        threshold_b: float = 64,
    ) -> List[bytes]:
        client = self._pick({"controlnet_detect"}, purpose="controlnet_detect")
        return client.controlnet_detect(
            module=module,
            images=images,
            processor_res=processor_res,
            threshold_a=threshold_a,
            threshold_b=threshold_b,
        )

    def get_controlnet_models(self) -> List[str]:
        client = self._pick({"controlnet_detect"}, purpose="controlnet_models")
        return client.get_controlnet_models()

    def get_controlnet_modules(self) -> List[str]:
        client = self._pick({"controlnet_detect"}, purpose="controlnet_modules")
        return client.get_controlnet_modules()

    def find_controlnet_model(self, module_type: str) -> Optional[str]:
        client = self._pick({"controlnet_detect"}, purpose="controlnet_model_lookup")
        return client.find_controlnet_model(module_type)

    def interrogate(self, image: Union[bytes, str], model: str = "clip") -> dict:
        client = self._pick({"interrogate"}, purpose="interrogate")
        return client.interrogate(image=image, model=model)

    def get_sd_models(self) -> List[dict]:
        client = self._pick({"models"}, purpose="sd_models")
        return client.get_sd_models()

    def get_vae_models(self) -> List[str]:
        client = self._pick({"vae"}, purpose="vae_models")
        return client.get_vae_models()

    def get_samplers(self) -> List[dict]:
        client = self._pick({"samplers"}, purpose="samplers")
        return client.get_samplers()

    def get_schedulers(self) -> List[dict]:
        client = self._pick({"schedulers"}, purpose="schedulers")
        return client.get_schedulers()

    def get_upscalers(self) -> List[dict]:
        client = self._pick({"upscalers"}, purpose="upscalers")
        return client.get_upscalers()

    def get_loras(self) -> List[dict]:
        client = self._pick({"loras"}, purpose="loras")
        return client.get_loras()

    def get_styles(self) -> List[dict]:
        client = self._pick({"styles"}, purpose="styles")
        return client.get_styles()

    def get_embeddings(self) -> List[dict]:
        client = self._pick({"embeddings"}, purpose="embeddings")
        return client.get_embeddings()

    def get_options(self) -> dict:
        client = self._pick({"options"}, purpose="options")
        return client.get_options()

    def set_options(self, options: dict) -> bool:
        client = self._pick({"options"}, purpose="options")
        return client.set_options(options)

def _build_comfy_headers(api_key: Optional[str], header_name: Optional[str], prefix: Optional[str]) -> dict:
    if not api_key:
        return {}
    api_key = api_key.strip()
    if not api_key:
        return {}
    header = (header_name or "X-API-Key").strip() or "X-API-Key"
    prefix_value = (prefix or "").strip()
    if prefix_value and api_key.startswith(prefix_value):
        value = api_key
    elif prefix_value:
        value = f"{prefix_value}{api_key}"
    else:
        value = api_key
    return {header: value}


def build_sd_client(
    provider_override: Optional[str] = None,
    *,
    comfy_api_key: Optional[str] = None,
    comfy_url_override: Optional[str] = None,
    poe_api_key: Optional[str] = None,
    poe_url_override: Optional[str] = None,
    poe_model_override: Optional[str] = None,
) -> BaseSdClient:
    """
    Build appropriate SD client based on environment.
    
    ВАЖНО: Используйте get_sd_layer() из sd_request_layer.py вместо этой функции!
    Эта функция предназначена только для внутреннего использования SDRequestLayer.
    """
    settings = get_settings()
    # Force re-read from environment to bypass settings cache
    sd_url = os.environ.get("SD_API_URL", settings.sd_api_url).strip()
    sd_mock = os.environ.get("SD_MOCK_MODE", str(settings.sd_mock_mode)).strip().lower() in ("true", "1", "yes")

    if sd_mock:
        logging.getLogger(__name__).info("Using MockSdClient (SD_MOCK_MODE=true)")
        return MockSdClient()

    provider_override_norm = normalize_sd_provider(provider_override)
    provider_raw = provider_override_norm or os.environ.get("SD_PROVIDER", settings.sd_provider)
    provider = normalize_sd_provider(provider_raw) or "a1111"
    fallback = os.environ.get("SD_FALLBACK_PROVIDER", settings.sd_fallback_provider).strip().lower() or ""

    if provider == "auto":
        provider = "comfy" if os.environ.get("SD_COMFY_URL", settings.sd_comfy_url).strip() else "a1111"

    if provider in {"a1111", "forge", "webui"}:
        logging.getLogger(__name__).info(f"Using HttpSdClient at {sd_url}")
        return HttpSdClient(sd_url)

    if provider in {"comfy", "comfyui", "comfy_api"}:
        from app.infra.comfy_client import ComfySdClient

        if provider == "comfy_api":
            comfy_url = (
                comfy_url_override
                or os.environ.get("SD_COMFY_API_URL", settings.sd_comfy_api_url).strip()
                or os.environ.get("SD_COMFY_URL", settings.sd_comfy_url).strip()
            )
        else:
            comfy_url = comfy_url_override or os.environ.get("SD_COMFY_URL", settings.sd_comfy_url).strip()
        api_key = (
            comfy_api_key
            or os.environ.get("SD_COMFY_API_KEY", settings.sd_comfy_api_key)
            or None
        )
        header_name = os.environ.get("SD_COMFY_API_KEY_HEADER", settings.sd_comfy_api_key_header)
        prefix = os.environ.get("SD_COMFY_API_KEY_PREFIX", settings.sd_comfy_api_key_prefix)
        headers = _build_comfy_headers(api_key, header_name, prefix)
        if fallback in {"a1111", "forge", "webui"}:
            logging.getLogger(__name__).info(
                "ComfyUI provider selected; ignoring fallback '%s' to keep workflow-based generation.",
                fallback,
            )
        return ComfySdClient(comfy_url, headers=headers)

    if provider == "poe_api":
        poe_url = poe_url_override or os.environ.get("SD_POE_API_URL", settings.sd_poe_api_url).strip()
        api_key = poe_api_key or os.environ.get("SD_POE_API_KEY", settings.sd_poe_api_key or "") or ""
        model = poe_model_override or os.environ.get("SD_POE_MODEL", settings.sd_poe_model).strip()
        quality = os.environ.get("SD_POE_QUALITY", settings.sd_poe_quality).strip()
        logging.getLogger(__name__).info("Using PoeSdClient at %s with model %s", poe_url, model)
        return PoeSdClient(poe_url, api_key, model, quality=quality)

    logging.getLogger(__name__).info(f"Unknown SD provider '{provider}', falling back to HttpSdClient at {sd_url}")
    return HttpSdClient(sd_url)
