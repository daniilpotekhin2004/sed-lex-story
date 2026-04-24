# ComfyUI workflow sets

This project ships **four ready-to-use ComfyUI workflow sets**. Each set contains
templates for the same logical operations so the backend can switch them **without
changing the API**.

Workflow sets live in:

`backend/app/infra/comfy/workflows/sets/<set_id>/`.

The active workflow for a request is selected by the **pipeline profile** via
`workflow_set` (see `backend/app/config/pipeline_profiles.json`).

## Included sets

### 1) `qwen`
Balanced quality, Qwen GGUF workflows.

Files:
- `scene_txt2img.json`
- `scene_img2img.json`
- `character_txt2img.json`
- `character_img2img.json`

### 2) `flux4bit`
FLUX GGUF templates (intended for 4-bit quantized UNet GGUF).

Files:
- `scene_txt2img.json`
- `scene_img2img.json`
- `character_txt2img.json`
- `character_img2img.json`

### 3) `mixed_cn_ipadapter`
Mixed scene workflow with **ControlNet + IP-Adapter**.

Files:
- `scene_txt2img.json`
- `scene_img2img.json`
- `character_txt2img.json` (fallback)
- `character_img2img.json` (fallback)

Notes:
- The backend understands **A1111-style** `alwayson_scripts.controlnet.args` and
  maps the *first* ControlNet unit and the *first* IP-Adapter unit to these
  workflows.
- If a request contains `alwayson_scripts.controlnet`, the backend auto-forces
  `workflow_set=mixed_cn_ipadapter` (even if a different set was selected).

### 4) `fast`
Fast/lightweight templates for testing & prototyping.

Files:
- `scene_txt2img.json`
- `scene_img2img.json`
- `character_txt2img.json`
- `character_img2img.json`

## How to select

Use an existing API field: `pipeline_profile_id`.

This archive adds a few ready profiles:
- `scene_flux4bit`
- `scene_mixed_cn_ipadapter`
- `scene_fast`
- `character_flux4bit`
- `character_fast`

You can also add your own profiles by copying any existing one and setting
`workflow_set` to one of: `qwen`, `flux4bit`, `mixed_cn_ipadapter`, `fast`.

## Workflow mapping config

The mapping from `(workflow_set, workflow_task, kind)` to a workflow JSON file is
stored in:

`backend/app/config/comfy_workflow_sets.json`.
