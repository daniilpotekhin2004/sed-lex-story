# ComfyUI Cloud API Workflow Set

This workflow set is designed for **ComfyUI Cloud API** (https://cloud.comfy.org).

## Key Differences from Local Workflows

1. **Standard Nodes Only**: Uses `CheckpointLoaderSimple`, `CLIPTextEncode`, `KSampler`, `VAEDecode`, `SaveImage`
2. **No GGUF Loaders**: Cloud API doesn't support `UnetLoaderGGUF` or `CLIPLoaderGGUF`
3. **No Custom Nodes**: Only built-in ComfyUI nodes are available
4. **API Key Authentication**: Requires `X-API-Key` header (no prefix)

## Configuration

Set these in `backend/.env`:

```env
SD_PROVIDER=comfy_api
SD_COMFY_API_URL=https://cloud.comfy.org/api
SD_COMFY_API_KEY=your_api_key_here
SD_COMFY_API_KEY_HEADER=X-API-Key
```

## Workflow Files

- `scene_txt2img.json` - Text-to-image for scenes
- `scene_img2img.json` - Image-to-image for scenes
- `character_txt2img.json` - Text-to-image for characters
- `character_img2img.json` - Image-to-image for characters

All workflows use SDXL base model by default (`sd_xl_base_1.0.safetensors`).

## Usage

The backend automatically selects this workflow set when `SD_PROVIDER=comfy_api`.

To explicitly use it:
```python
client.generate_images(
    prompt="your prompt",
    workflow_set="cloud_api",
    workflow_task="scene"  # or "character"
)
```
