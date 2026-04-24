# Root cause: Parameter substitution was scattered across multiple methods
# with unclear precedence and overriding behavior.
# Solution: Centralized, explicit parameter handling with clear rules.

"""
Workflow Parameter Management

This module provides a single, transparent way to handle workflow parameters.

RULES:
1. Workflow JSON files are the SOURCE OF TRUTH for all parameters
2. Only substitute parameters that are explicitly marked for substitution
3. Never override parameters unless explicitly requested
4. Make all substitutions visible and traceable
"""

from typing import Dict, Any, Optional, List
from copy import deepcopy


class WorkflowParams:
    """
    Manages parameter substitution for ComfyUI workflows.
    
    Parameters are categorized:
    - REQUIRED: Must be substituted (prompts, seeds, input images)
    - OPTIONAL: Only substitute if explicitly provided (steps, sampler)
    - PRESERVED: Never override (guidance for FLUX workflows)
    """
    
    # Node types that should NEVER have their guidance overridden
    PRESERVE_GUIDANCE_NODES = {
        "CLIPTextEncodeFlux",  # FLUX txt2img - guidance in workflow JSON
        "FluxGuidance",  # FLUX workflows - guidance in workflow JSON
    }
    
    # Node types where guidance CAN be overridden (currently none - all preserved)
    OVERRIDE_GUIDANCE_NODES = {
        "FluxKontextProImageNode",  # FLUX img2img with dynamic guidance
    }
    
    def __init__(self, workflow: Dict[str, Any]):
        """Initialize with a workflow template (will be deep copied)."""
        self.workflow = deepcopy(workflow)
    
    def set_prompts(self, prompt: str, negative_prompt: Optional[str] = None) -> None:
        """
        Set prompts in the workflow.
        
        For FLUX workflows with DualCLIPLoader:
        - Splits prompt into style (clip_l) and description (t5xxl)
        
        For standard workflows:
        - Sets first CLIPTextEncode as positive
        - Sets second CLIPTextEncode as negative
        """
        # Check for Qwen-specific nodes
        has_qwen = self._has_node_type("TextEncodeQwenImageEditPlus") or self._has_node_type("TextEncodeQwenImageEdit")
        # Check for FLUX-specific nodes
        has_flux_encode = self._has_node_type("CLIPTextEncodeFlux")
        has_kontext = self._has_node_type("FluxKontextProImageNode")

        if has_qwen:
            # Qwen image edit workflow: TextEncodeQwenImageEditPlus nodes are wired into KSampler positive/negative.
            pos_node = None
            neg_node = None
            for node in self.workflow.values():
                if not isinstance(node, dict):
                    continue
                if node.get("class_type") != "KSampler":
                    continue
                inputs = node.get("inputs", {})
                pos_ref = inputs.get("positive")
                neg_ref = inputs.get("negative")
                if isinstance(pos_ref, list) and pos_ref:
                    pos_node = self.workflow.get(str(pos_ref[0]))
                if isinstance(neg_ref, list) and neg_ref:
                    neg_node = self.workflow.get(str(neg_ref[0]))
                if pos_node or neg_node:
                    break

            def _set_qwen_prompt(node: Optional[Dict[str, Any]], value: str) -> None:
                if not isinstance(node, dict):
                    return
                if node.get("class_type") not in {"TextEncodeQwenImageEditPlus", "TextEncodeQwenImageEdit"}:
                    return
                node.setdefault("inputs", {})["prompt"] = value

            _set_qwen_prompt(pos_node, prompt)
            if negative_prompt is not None:
                _set_qwen_prompt(neg_node, negative_prompt)
            elif neg_node is not None:
                _set_qwen_prompt(neg_node, "")

            # Fallback: if KSampler wiring not found, set first/second Qwen nodes
            if pos_node is None:
                qwen_nodes = self._get_nodes_by_type("TextEncodeQwenImageEditPlus") or self._get_nodes_by_type("TextEncodeQwenImageEdit")
                if qwen_nodes:
                    self._set_text_input(qwen_nodes[0], prompt)
                if len(qwen_nodes) > 1 and negative_prompt is not None:
                    self._set_text_input(qwen_nodes[1], negative_prompt)
                elif len(qwen_nodes) > 1 and negative_prompt is None:
                    self._set_text_input(qwen_nodes[1], "")
            return
        
        if has_flux_encode:
            # FLUX txt2img: split prompt for dual CLIP
            style, description = self._split_prompt_for_flux(prompt)
            for node in self.workflow.values():
                if self._is_node_type(node, "CLIPTextEncodeFlux"):
                    node.setdefault("inputs", {})["clip_l"] = style
                    node.setdefault("inputs", {})["t5xxl"] = description
            
            # Negative prompt goes to CLIPTextEncode nodes
            if negative_prompt:
                for node in self.workflow.values():
                    if self._is_node_type(node, "CLIPTextEncode"):
                        self._set_text_input(node, negative_prompt)
        
        elif has_kontext:
            # FLUX img2img: single prompt field with negative appended
            # Root cause: FluxKontextProImageNode has no separate negative input
            # Solution: Append negative as text in the prompt with newline separator
            for node in self.workflow.values():
                if self._is_node_type(node, "FluxKontextProImageNode"):
                    if negative_prompt:
                        # Format: "positive prompt\nnegative: negative prompt"
                        combined_prompt = f"{prompt}\n{negative_prompt}"
                    else:
                        combined_prompt = prompt
                    node.setdefault("inputs", {})["prompt"] = combined_prompt
        
        else:
            # Standard workflows: first node = positive, second = negative
            encode_nodes = self._get_nodes_by_type("CLIPTextEncode")
            if encode_nodes:
                self._set_text_input(encode_nodes[0], prompt)
            if len(encode_nodes) > 1 and negative_prompt:
                self._set_text_input(encode_nodes[1], negative_prompt)
    
    def set_seed(self, seed: int) -> None:
        """Set seed in all relevant nodes."""
        for node in self.workflow.values():
            if not isinstance(node, dict):
                continue
            
            class_type = node.get("class_type", "")
            inputs = node.setdefault("inputs", {})
            
            if class_type == "KSampler" and "seed" in inputs:
                inputs["seed"] = seed
            elif class_type == "RandomNoise" and "noise_seed" in inputs:
                inputs["noise_seed"] = seed
            elif class_type == "FluxKontextProImageNode" and "seed" in inputs:
                inputs["seed"] = seed
    
    def set_dimensions(self, width: int, height: int, batch_size: int = 1) -> None:
        """Set image dimensions."""
        for node in self.workflow.values():
            if not isinstance(node, dict):
                continue
            
            class_type = node.get("class_type", "")
            inputs = node.setdefault("inputs", {})
            
            if class_type == "EmptyLatentImage":
                inputs["width"] = width
                inputs["height"] = height
                inputs["batch_size"] = batch_size
            elif class_type in {"Flux2Scheduler", "EmptyFlux2LatentImage"}:
                if "width" in inputs:
                    inputs["width"] = width
                if "height" in inputs:
                    inputs["height"] = height
                if "batch_size" in inputs and class_type == "EmptyFlux2LatentImage":
                    inputs["batch_size"] = batch_size
    
    def set_sampling_params(
        self,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        sampler: Optional[str] = None,
        scheduler: Optional[str] = None,
        denoise: Optional[float] = None,
    ) -> None:
        """
        Set sampling parameters (only if provided).
        
        Note: cfg parameter is for SDXL/SD1.5 workflows (KSampler).
        FLUX workflows use guidance in CLIPTextEncodeFlux (preserved from JSON).
        """
        for node in self.workflow.values():
            if not isinstance(node, dict):
                continue
            
            class_type = node.get("class_type", "")
            inputs = node.setdefault("inputs", {})
            
            if class_type == "KSampler":
                if steps is not None and "steps" in inputs:
                    inputs["steps"] = steps
                if cfg is not None and "cfg" in inputs:
                    inputs["cfg"] = cfg
                if sampler is not None and "sampler_name" in inputs:
                    inputs["sampler_name"] = sampler
                if scheduler is not None and "scheduler" in inputs:
                    inputs["scheduler"] = scheduler
                if denoise is not None and "denoise" in inputs:
                    inputs["denoise"] = denoise
            
            elif class_type == "KSamplerSelect":
                if sampler is not None:
                    inputs["sampler_name"] = sampler
            
            elif class_type == "Flux2Scheduler":
                if steps is not None and "steps" in inputs:
                    inputs["steps"] = steps
            
            elif class_type == "FluxKontextProImageNode":
                if steps is not None and "steps" in inputs:
                    inputs["steps"] = steps
    
    def set_guidance(self, guidance: float) -> None:
        """
        Set guidance ONLY for nodes that support dynamic guidance.
        
        IMPORTANT: CLIPTextEncodeFlux guidance is NEVER overridden.
        It's set in the workflow JSON and should not be changed.
        """
        for node in self.workflow.values():
            if not isinstance(node, dict):
                continue
            
            class_type = node.get("class_type", "")
            
            # Skip nodes where guidance should be preserved
            if class_type in self.PRESERVE_GUIDANCE_NODES:
                continue
            
            # Only override for specific node types
            if class_type in self.OVERRIDE_GUIDANCE_NODES:
                inputs = node.setdefault("inputs", {})
                if "guidance" in inputs:
                    inputs["guidance"] = guidance
    
    def set_input_image(self, image_placeholder: str) -> None:
        """Set input image for img2img workflows."""
        for node in self.workflow.values():
            if self._is_node_type(node, "LoadImage"):
                node.setdefault("inputs", {})["image"] = image_placeholder

    def set_input_images(self, image_map: Dict[str, str]) -> None:
        """Set multiple input images for workflows with several LoadImage nodes."""
        if not image_map:
            return
        for node in self.workflow.values():
            if not self._is_node_type(node, "LoadImage"):
                continue
            inputs = node.setdefault("inputs", {})
            current = inputs.get("image")
            if isinstance(current, str) and current in image_map:
                inputs["image"] = image_map[current]
    
    def set_model(self, model_name: str, vae_name: Optional[str] = None) -> None:
        """Set model and VAE names."""
        for node in self.workflow.values():
            if not isinstance(node, dict):
                continue
            
            class_type = node.get("class_type", "")
            inputs = node.setdefault("inputs", {})
            
            if class_type in {"CheckpointLoaderSimple", "CheckpointLoader"}:
                inputs["ckpt_name"] = model_name
                if vae_name and "vae_name" in inputs:
                    inputs["vae_name"] = vae_name
            
            elif class_type in {"UnetLoaderGGUF", "UnetLoaderGGUFAdvanced"}:
                inputs["unet_name"] = model_name
            
            elif class_type == "VAELoader" and vae_name:
                inputs["vae_name"] = vae_name
    
    def get_workflow(self) -> Dict[str, Any]:
        """Return the modified workflow."""
        return self.workflow
    
    # Helper methods
    
    def _has_node_type(self, class_type: str) -> bool:
        """Check if workflow contains a node of given type."""
        return any(
            isinstance(node, dict) and node.get("class_type") == class_type
            for node in self.workflow.values()
        )
    
    def _is_node_type(self, node: Any, class_type: str) -> bool:
        """Check if node is of given type."""
        return isinstance(node, dict) and node.get("class_type") == class_type
    
    def _get_nodes_by_type(self, class_type: str) -> List[Dict[str, Any]]:
        """Get all nodes of given type, sorted by node ID."""
        nodes = []
        for node_id in sorted(
            self.workflow.keys(),
            key=lambda v: int(v) if str(v).isdigit() else str(v)
        ):
            node = self.workflow[node_id]
            if self._is_node_type(node, class_type):
                nodes.append(node)
        return nodes
    
    def _set_text_input(self, node: Dict[str, Any], text: str) -> None:
        """Set text in a node (handles 'text' or 'prompt' field)."""
        inputs = node.setdefault("inputs", {})
        if "text" in inputs:
            inputs["text"] = text
        elif "prompt" in inputs:
            inputs["prompt"] = text
        else:
            inputs["text"] = text
    
    def _split_prompt_for_flux(self, prompt: str) -> tuple[str, str]:
        """
        Split prompt for FLUX dual CLIP.
        
        CLIP-L: Style keywords (short, focused)
        T5: Detailed description (full prompt)
        """
        parts = [p.strip() for p in prompt.split(",")]
        
        # First 8 parts = style (CLIP-L)
        # All parts = description (T5)
        style = ", ".join(parts[:8]) if len(parts) > 8 else prompt
        description = prompt
        
        return style, description
