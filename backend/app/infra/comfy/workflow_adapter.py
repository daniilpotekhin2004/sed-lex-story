"""
Workflow Adapter - Converts complex ComfyUI workflow formats to simple format.

Root cause: ComfyUI exports workflows in complex node-based format
Solution: Adapter pattern to normalize workflows to simple dict format
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class QwenWorkflowAdapter:
    """Adapter to make Qwen GGUF workflows work with ComfyUI client"""
    
    def __init__(self, workflow: dict):
        self.workflow = workflow
        self.node_mapping = self._analyze_nodes()
    
    def _analyze_nodes(self) -> dict:
        """Analyze workflow to find key nodes"""
        mapping = {
            "model_loader": None,
            "clip_loader": None, 
            "vae_loader": None,
            "positive_prompt": None,
            "negative_prompt": None,
            "latent_image": None,
            "sampler": None,
            "vae_decode": None,
            "save_image": None
        }
        
        for node_id, node in self.workflow.items():
            class_type = node.get("class_type", "")
            
            if class_type == "UnetLoaderGGUF":
                mapping["model_loader"] = node_id
            elif class_type == "CLIPLoaderGGUF":
                mapping["clip_loader"] = node_id
            elif class_type == "VaeGGUF":
                mapping["vae_loader"] = node_id
            elif class_type == "TextEncodeQwenImageEditPlus":
                prompt_text = node.get("inputs", {}).get("prompt", "")
                if "worst quality" in prompt_text.lower() or "low quality" in prompt_text.lower():
                    mapping["negative_prompt"] = node_id
                else:
                    mapping["positive_prompt"] = node_id
            elif class_type == "EmptyLatentImage":
                mapping["latent_image"] = node_id
            elif class_type == "KSampler":
                mapping["sampler"] = node_id
            elif class_type == "VAEDecode":
                mapping["vae_decode"] = node_id
            elif class_type == "SaveImage":
                mapping["save_image"] = node_id
        
        return mapping
    
    def update_prompt(self, positive_prompt: str, negative_prompt: Optional[str] = None):
        """Update prompt texts in the workflow"""
        if self.node_mapping["positive_prompt"]:
            node_id = self.node_mapping["positive_prompt"]
            self.workflow[node_id]["inputs"]["prompt"] = positive_prompt
        
        if self.node_mapping["negative_prompt"] and negative_prompt:
            node_id = self.node_mapping["negative_prompt"]
            self.workflow[node_id]["inputs"]["prompt"] = negative_prompt
    
    def update_dimensions(self, width: int, height: int, batch_size: int = 1):
        """Update image dimensions"""
        if self.node_mapping["latent_image"]:
            node_id = self.node_mapping["latent_image"]
            self.workflow[node_id]["inputs"]["width"] = width
            self.workflow[node_id]["inputs"]["height"] = height
            self.workflow[node_id]["inputs"]["batch_size"] = batch_size
    
    def update_sampler_settings(
        self,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        seed: Optional[int] = None,
        sampler_name: Optional[str] = None,
        scheduler: Optional[str] = None,
        denoise: Optional[float] = None
    ):
        """Update sampler settings"""
        if self.node_mapping["sampler"]:
            node_id = self.node_mapping["sampler"]
            inputs = self.workflow[node_id]["inputs"]
            
            if steps is not None:
                inputs["steps"] = steps
            if cfg is not None:
                inputs["cfg"] = cfg
            if seed is not None:
                inputs["seed"] = seed
            if sampler_name is not None:
                inputs["sampler_name"] = sampler_name
            if scheduler is not None:
                inputs["scheduler"] = scheduler
            if denoise is not None:
                inputs["denoise"] = denoise
    
    def update_filename_prefix(self, prefix: str):
        """Update output filename prefix"""
        if self.node_mapping["save_image"]:
            node_id = self.node_mapping["save_image"]
            self.workflow[node_id]["inputs"]["filename_prefix"] = prefix
    
    def get_workflow(self) -> dict:
        """Get the adapted workflow"""
        return self.workflow


def convert_complex_to_simple(workflow: dict) -> dict:
    """
    Convert complex ComfyUI workflow format to simple format.
    
    Complex format has 'nodes' array, simple format is flat dict.
    """
    if "nodes" not in workflow:
        # Already simple format
        return workflow
    
    # Convert nodes array to dict keyed by node ID
    simple = {}
    for node in workflow.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", ""))
        if not node_id:
            continue
        simple[node_id] = node
    
    return simple
