
# ComfyUI 3-Step Character Workflow Usage

## Overview
These workflows use the verified Qwen model stack for consistent character generation:

- **Model**: qwen-rapid-nsfw-v9.0-Q4_K_M.gguf
- **CLIP**: Qwen2.5-VL-7B-Instruct-abliterated.Q8_0.gguf  
- **LoRA**: ultra_realistic_hyperdetailed_qwen.safetensors
- **VAE**: qwen-image\qwen_image_vae.safetensors

## Step 1: High-Quality Reference Portrait
**File**: `comfy_workflow_step1_hq_reference.json`

**Purpose**: Generate initial character portrait from text description
**Parameters**:
- Resolution: 768x1024 (portrait)
- Steps: 9, CFG: 1.0, Denoise: 1.0
- Sampler: euler, Scheduler: beta

**Usage**:
1. Load workflow in ComfyUI
2. Replace `{{prompt}}` with character description
3. Replace `{{negative_prompt}}` with negative terms
4. Replace `{{character_id}}` with unique character ID
5. Generate image

## Step 2: Multi-View Generation
**File**: `comfy_workflow_step2_multiview_generation.json`

**Purpose**: Generate front, back, and side views using Step 1 as reference
**Parameters**:
- Resolution: 768x1024 (portrait)
- Steps: 9, CFG: 1.0, Denoise: 0.78 (img2img)
- Uses reference image from Step 1

**Usage**:
1. Load workflow in ComfyUI
2. Load Step 1 output image in LoadImage node
3. Replace prompt placeholders:
   - `{{front_view_prompt}}`
   - `{{back_view_prompt}}`
   - `{{side_view_prompt}}`
4. Replace `{{character_id}}` with same ID from Step 1
5. Generate all three views

## Step 3: Scene Generation
**File**: `comfy_workflow_step3_scene_generation.json`

**Purpose**: Place character in cinematic scene
**Parameters**:
- Resolution: 1024x768 (landscape)
- Steps: 9, CFG: 1.0, Denoise: 0.65
- Uses character reference for consistency

**Usage**:
1. Load workflow in ComfyUI
2. Load character reference (from Step 1 or 2)
3. Replace `{{scene_prompt}}` with scene description
4. Replace `{{character_id}}` with same ID
5. Generate scene

## Parameter Placeholders

All workflows use these placeholder patterns:
- `{{prompt}}` - Main generation prompt
- `{{negative_prompt}}` - Negative prompt
- `{{character_id}}` - Unique character identifier
- `{{reference_image}}` - Reference image filename
- `{{front_view_prompt}}` - Front view specific prompt
- `{{back_view_prompt}}` - Back view specific prompt  
- `{{side_view_prompt}}` - Side view specific prompt
- `{{scene_prompt}}` - Scene generation prompt

## Model Requirements

Ensure these files are in your ComfyUI models directories:
- `models/unet/qwen-rapid-nsfw-v9.0-Q4_K_M.gguf`
- `models/clip/Qwen2.5-VL-7B-Instruct-abliterated.Q8_0.gguf`
- `models/loras/ultra_realistic_hyperdetailed_qwen.safetensors`
- `models/vae/qwen-image/qwen_image_vae.safetensors`

## Integration with Backend

These workflows are designed to work with the 2-step character creation system:
1. Backend calls Step 1 for initial portrait
2. Backend calls Step 2 using Step 1 output as reference
3. Optional: Backend calls Step 3 for scene generation

The parameter placeholders will be replaced by the ComfyUI client integration.
