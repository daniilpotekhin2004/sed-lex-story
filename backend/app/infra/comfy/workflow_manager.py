"""
Workflow Manager - Handles loading and managing ComfyUI workflows.

Root cause: Workflow loading logic scattered in comfy_client.py
Solution: Centralized workflow management with clear responsibilities
"""
from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from .workflow_adapter import convert_complex_to_simple

logger = logging.getLogger(__name__)


class WorkflowManager:
    """Manages ComfyUI workflow templates"""
    
    def __init__(self):
        self.settings = get_settings()
        self._workflow_dir = Path(__file__).resolve().parent / "workflows"
    
    def get_workflow_dir(self) -> Path:
        """Get the workflows directory"""
        return self._workflow_dir
    
    def load_workflow_file(self, path: str | Path) -> dict:
        """Load a workflow JSON file"""
        data = Path(path).read_text(encoding="utf-8")
        return json.loads(data)
    
    def parse_output_nodes(self, workflow: dict, overrides: str = "") -> list[str]:
        """
        Extract output node IDs from workflow.
        
        Args:
            workflow: Workflow dict
            overrides: Comma-separated list of node IDs to override
        
        Returns:
            List of output node IDs
        """
        if overrides:
            nodes = [value.strip() for value in overrides.split(",") if value.strip()]
            if nodes:
                return nodes
        
        output_nodes = []
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") in {
                "SaveImage",
                "PreviewImage",
                "SaveAudio",
                "PreviewAudio",
            }:
                output_nodes.append(str(node_id))
        
        return output_nodes
    
    def load_workflow_template(
        self,
        kind: str,
        *,
        workflow_set: Optional[str] = None,
        workflow_task: Optional[str] = None,
    ) -> tuple[dict, list[str]]:
        """
        Load a workflow template.

        Precedence:
        1) Explicit env override (SD_COMFY_WORKFLOW_TXT2IMG/IMG2IMG) when workflow_set is not provided.
        2) Workflow set mapping (app/config/comfy_workflow_sets.json).
        3) Legacy defaults (sd3_5_*.json) as last resort.
        
        Args:
            kind: "txt2img" or "img2img"
            workflow_set: Optional workflow set ID
            workflow_task: Optional task type ("scene" or "character")
        
        Returns:
            (workflow_dict, output_node_ids)
        """
        workflow_task = (workflow_task or "scene").strip() or "scene"

        if kind == "img2img":
            env_path = self.settings.sd_comfy_workflow_img2img or ""
            legacy_default_path = self._workflow_dir / "sd3_5_img2img.json"
            overrides = self.settings.sd_comfy_output_nodes_img2img
            key = f"{workflow_task}_img2img"
        else:
            env_path = self.settings.sd_comfy_workflow_txt2img or ""
            legacy_default_path = self._workflow_dir / "sd3_5_txt2img.json"
            overrides = self.settings.sd_comfy_output_nodes_txt2img
            key = f"{workflow_task}_txt2img"

        # Check env override first
        if not workflow_set and env_path:
            raw_workflow = self.load_workflow_file(env_path)
        else:
            # Load workflow sets config
            cfg_path = Path(__file__).resolve().parents[2] / "config" / "comfy_workflow_sets.json"
            config: dict = {}
            try:
                with cfg_path.open("r", encoding="utf-8") as fp:
                    config = json.load(fp)
            except Exception:
                config = {}

            set_id = workflow_set or str(config.get("default") or "cloud_api")
            set_paths = (config.get("sets") or {}).get(set_id, {}).get("paths") or {}
            rel_path = set_paths.get(key)
            
            # Fallback: if a set doesn't define character templates, reuse scene ones
            if rel_path is None and workflow_task != "scene":
                rel_path = set_paths.get(key.replace(f"{workflow_task}_", "scene_"))
            
            if rel_path:
                default_path = self._workflow_dir / str(rel_path)
            else:
                default_path = legacy_default_path

            if default_path.exists():
                raw_workflow = self.load_workflow_file(str(default_path))
            else:
                raise FileNotFoundError(f"ComfyUI workflow template not found: {default_path}")

        # Convert complex format to simple if needed
        workflow = convert_complex_to_simple(raw_workflow)
        output_nodes = self.parse_output_nodes(workflow, overrides)
        
        return workflow, output_nodes
    
    def load_workflow(
        self,
        path: str,
        *,
        output_nodes: Optional[list[str]] = None
    ) -> tuple[dict, list[str]]:
        """
        Load a workflow file (simple or UI export) and return (workflow, output_nodes).
        
        Args:
            path: Path to workflow file
            output_nodes: Optional list of output node IDs to override
        
        Returns:
            (workflow_dict, output_node_ids)
        """
        raw_workflow = self.load_workflow_file(path)
        workflow = convert_complex_to_simple(raw_workflow)
        nodes = output_nodes or self.parse_output_nodes(workflow, "")
        return workflow, nodes
