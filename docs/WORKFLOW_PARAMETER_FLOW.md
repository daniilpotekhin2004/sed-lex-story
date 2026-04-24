# Workflow Parameter Flow

## Overview

This document explains how parameters flow from workflow JSON files to ComfyUI API calls.

**Root Cause of Previous Bugs**: Parameters were being overridden in multiple places with unclear precedence, making it impossible to control values like `guidance`.

**Solution**: Single source of truth with explicit, transparent parameter handling.

## The Flow

```
Workflow JSON File
    ↓
WorkflowParams (workflow_params.py)
    ↓
ComfyUI API Call
```

## 1. Workflow JSON Files (Source of Truth)

Location: `backend/app/infra/comfy/workflows/sets/cloud_api/`

Example: `character_txt2img.json`
```json
{
  "9": {
    "inputs": {
      "clip_l": "",
      "t5xxl": "",
      "guidance": 3,  ← This is the source of truth
      "clip": ["8", 0]
    },
    "class_type": "CLIPTextEncodeFlux"
  }
}
```

**Rule**: Workflow JSON files contain ALL parameters. Only substitute what's explicitly marked for substitution.

## 2. WorkflowParams Class

Location: `backend/app/infra/workflow_params.py`

This class handles parameter substitution with clear rules:

### Parameter Categories

**REQUIRED** (always substituted):
- `prompts` - User's text prompt
- `seed` - Random seed for generation
- `model` - Model and VAE names
- `input_image` - For img2img workflows

**OPTIONAL** (only if provided):
- `steps` - Sampling steps
- `sampler` - Sampler algorithm
- `scheduler` - Scheduler type
- `denoise` - Denoising strength

**PRESERVED** (never overridden):
- `guidance` for `CLIPTextEncodeFlux` nodes
- Any parameter not explicitly set

### Usage Example

```python
from app.infra.workflow_params import WorkflowParams

# Load workflow template
template = load_workflow_json("character_txt2img.json")

# Create params handler
params = WorkflowParams(template)

# Set REQUIRED parameters
params.set_prompts("a warrior character", "blurry, low quality")
params.set_seed(12345)
params.set_model("flux1-dev-fp8.safetensors")

# For cloud API: DON'T set guidance - it's in the JSON
# For local: Can optionally set sampling params
params.set_sampling_params(steps=28, sampler="lms")

# Get final workflow
workflow = params.get_workflow()
```

## 3. ComfyClient Integration

Location: `backend/app/infra/comfy_client.py`

### txt2img Workflow

```python
def _build_txt2img_workflow(self, *, prompt, seed, model_name, ...):
    template, output_nodes = self._load_workflow_template("txt2img", ...)
    
    params = WorkflowParams(template)
    params.set_prompts(prompt, negative_prompt)
    params.set_seed(seed)
    params.set_model(model_name, vae_name)
    
    if self._is_cloud and workflow_set == "cloud_api":
        # Cloud API: minimal substitution
        # guidance stays at 3 (from JSON)
        return params.get_workflow(), output_nodes
    
    # Local: full control
    params.set_dimensions(width, height, batch_size)
    params.set_sampling_params(steps, sampler, scheduler, denoise=1.0)
    
    return params.get_workflow(), output_nodes
```

### img2img Workflow

```python
def _build_img2img_workflow(self, *, prompt, seed, input_image, ...):
    template, output_nodes = self._load_workflow_template("img2img", ...)
    
    params = WorkflowParams(template)
    params.set_prompts(prompt, negative_prompt)
    params.set_seed(seed)
    params.set_model(model_name, vae_name)
    params.set_input_image(input_image)
    
    if self._is_cloud and workflow_set == "cloud_api":
        # Cloud API: minimal substitution
        # guidance stays at 5 (from JSON)
        return params.get_workflow(), output_nodes
    
    # Local: full control
    params.set_sampling_params(steps, sampler, scheduler, denoise)
    
    return params.get_workflow(), output_nodes
```

## 4. Configuration Files

Location: `backend/app/config/character_view_config.json`

```json
{
  "default_workflow": {
    "initial_generation": {
      "workflow_set": "custom",
      "workflow_task": "character_txt2img",
      "steps": 44,
      "guidance": 5,  ← This is IGNORED for cloud_api workflows
      "width": 832,
      "height": 1216
    }
  }
}
```

**Important**: The `guidance` value in config files is NOT used for cloud_api workflows. The workflow JSON file is the source of truth.

## Debugging Parameter Issues

### Check the Flow

1. **Workflow JSON**: What's the guidance value in the JSON file?
   ```bash
   cat backend/app/infra/comfy/workflows/sets/cloud_api/character_txt2img.json | grep guidance
   ```

2. **WorkflowParams**: Is it being preserved?
   - Check `PRESERVE_GUIDANCE_NODES` in `workflow_params.py`
   - `CLIPTextEncodeFlux` should be in this list

3. **ComfyClient**: Is it calling WorkflowParams correctly?
   - For cloud_api: Should NOT call `set_guidance()`
   - Should only set prompts, seed, model, input_image

4. **API Request**: Check the actual request sent to ComfyUI
   - Look in `backend/log/sd_requests/` for logged requests
   - Verify guidance value matches workflow JSON

### Common Issues

**Issue**: Guidance is 1.0 instead of 3
- **Cause**: `cfg_scale` parameter being passed and overriding
- **Fix**: Don't call `set_guidance()` for cloud_api workflows

**Issue**: Prompts not being set
- **Cause**: Wrong node type detection
- **Fix**: Check `_has_node_type()` logic in WorkflowParams

**Issue**: Seed not changing
- **Cause**: Seed not being set for correct node type
- **Fix**: Check `set_seed()` handles both KSampler and RandomNoise

## Migration Notes

### Old Code (Removed)
- `_apply_common_inputs()` - Scattered parameter overrides
- `_apply_prompt_only_for_cloud()` - Unclear precedence
- `_apply_seed_only_for_cloud()` - Duplicate logic

### New Code
- `WorkflowParams` - Single, transparent parameter handler
- Clear separation: cloud_api vs local workflows
- Explicit preservation of workflow JSON values

## Best Practices

1. **Always check workflow JSON first** - It's the source of truth
2. **Use WorkflowParams for all substitutions** - Don't manipulate workflow dict directly
3. **Document why parameters are preserved** - Add comments explaining the reasoning
4. **Test with actual API calls** - Check logged requests to verify values
5. **Keep cloud_api minimal** - Only substitute what's absolutely necessary

## Summary

The new system makes parameter flow transparent and predictable:

- **Workflow JSON** = Source of truth for all parameters
- **WorkflowParams** = Explicit, traceable substitution
- **ComfyClient** = Minimal, clear integration
- **No hidden overrides** = What you see is what you get

This eliminates the "guidance is 1 instead of 3" class of bugs by making the entire flow visible and controllable.
