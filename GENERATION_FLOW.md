# Character Asset Generation Flow

## When "Generate Required Assets" is Pressed

### Step 1: Initial Sketch (txt2img)

**Call:**
```python
client.generate_images(
    prompt="portrait close-up, 85mm lens, studio lighting, [character description]",
    style=None,
    num_images=1,
    width=768,
    height=1024,
    negative_prompt="blur, low resolution, bad anatomy, deformed, extra limbs",
    cfg_scale=7.0,
    steps=9,
    seed=<random>,
    sampler="dpmpp_2m",
    scheduler="karras",
    model_id=None,  # Will use cloud default (GGUF filtered out)
    vae_id="FLUX1\\ae.safetensors",
    clip_id=None,
    loader_type="standard",
    loras=[],
    workflow_set="cloud_api",  # Forced for cloud
    workflow_task="character",
)
```

**Workflow Used:** `backend/app/infra/comfy/workflows/sets/cloud_api/character_txt2img.json`

**Workflow Structure:**
```json
{
  "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-dev-fp8.safetensors"}},
  "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry, low quality, deformed", "clip": ["1", 1]}},
  "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
  "5": {"class_type": "KSampler", "inputs": {
    "seed": 0,
    "steps": 28,
    "cfg": 1.0,
    "sampler_name": "lms",
    "scheduler": "beta",
    "denoise": 1,
    "model": ["1", 0],
    "positive": ["9", 0],
    "negative": ["3", 0],
    "latent_image": ["4", 0]
  }},
  "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
  "7": {"class_type": "PreviewImage", "inputs": {"images": ["6", 0]}},
  "8": {"class_type": "DualCLIPLoader", "inputs": {
    "clip_name1": "clip_l.safetensors",
    "clip_name2": "t5xxl_fp8_e4m3fn_scaled.safetensors",
    "type": "flux",
    "device": "default"
  }},
  "9": {"class_type": "CLIPTextEncodeFlux", "inputs": {
    "clip_l": "",  # Will be filled with style text
    "t5xxl": "",   # Will be filled with description text
    "guidance": 3.5,
    "clip": ["8", 0]
  }}
}
```

**What Gets Sent to Cloud:**
- Node 9 (CLIPTextEncodeFlux) gets `clip_l` and `t5xxl` filled with split prompt
- Node 5 (KSampler) gets `seed` updated
- Output node: Node 7 (PreviewImage)

---

### Step 2-5: Reference Views (img2img)

For each view: `complex`, `full_front`, `full_side`, `full_back`

**Call:**
```python
client.generate_images(
    prompt="Generate a clean full-body reference view of character shown in the picture, keeping face details, age, identity, outfit and hairstyle consistent, they must be same. \nfull body, front view, standing, neutral pose, feet visible, solo, one person, centered, studio lighting, clean plain background\nPRESERVE_IDENTITY: same person, exact same face, same facial features, same hairstyle\nsame outfit, same clothing, consistent character design\n[character description]",
    style=None,
    num_images=1,
    width=768,
    height=1024,
    negative_prompt="blur, low resolution, bad anatomy, deformed, extra limbs",
    cfg_scale=7.0,
    steps=9,
    seed=<random + i>,
    sampler="dpmpp_2m",
    scheduler="karras",
    model_id=None,  # Will use cloud default (GGUF filtered out)
    vae_id="FLUX1\\ae.safetensors",
    clip_id=None,
    loader_type="standard",
    loras=[],
    init_images=[<sketch_bytes>],  # The sketch from Step 1
    denoising_strength=0.65,
    workflow_set="cloud_api",  # Forced for cloud
    workflow_task="character",
)
```

**Workflow Used:** `backend/app/infra/comfy/workflows/sets/cloud_api/character_img2img.json`

**Workflow Structure:**
```json
{
  "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-dev-fp8.safetensors"}},
  "2": {"class_type": "LoadImage", "inputs": {"image": "__INPUT_IMAGE__"}},
  "3": {"class_type": "VAEEncode", "inputs": {"pixels": ["2", 0], "vae": ["1", 2]}},
  "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry, low quality, deformed", "clip": ["1", 1]}},
  "5": {"class_type": "DualCLIPLoader", "inputs": {
    "clip_name1": "clip_l.safetensors",
    "clip_name2": "t5xxl_fp8_e4m3fn_scaled.safetensors",
    "type": "flux",
    "device": "default"
  }},
  "6": {"class_type": "CLIPTextEncodeFlux", "inputs": {
    "clip_l": "",  # Will be filled with style text
    "t5xxl": "",   # Will be filled with description text
    "guidance": 5.0,
    "clip": ["5", 0]
  }},
  "7": {"class_type": "KSampler", "inputs": {
    "seed": 0,
    "steps": 44,
    "cfg": 5.0,
    "sampler_name": "euler",
    "scheduler": "simple",
    "denoise": 0.65,
    "model": ["1", 0],
    "positive": ["6", 0],
    "negative": ["4", 0],
    "latent_image": ["3", 0]
  }},
  "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
  "9": {"class_type": "PreviewImage", "inputs": {"images": ["8", 0]}}
}
```

**What Gets Sent to Cloud:**
- Sketch image uploaded first via `/api/upload/image`
- Node 2 (LoadImage) gets `image` set to uploaded filename
- Node 6 (CLIPTextEncodeFlux) gets `clip_l` and `t5xxl` filled with split prompt
- Node 7 (KSampler) gets `seed` updated
- Output node: Node 9 (PreviewImage)

---

## Key Parameters

### txt2img (Sketch):
- **Steps:** 28
- **CFG:** 1.0
- **Guidance:** 3.5
- **Denoise:** 1.0 (full generation)

### img2img (Reference Views):
- **Steps:** 44
- **CFG:** 5.0
- **Guidance:** 5.0
- **Denoise:** 0.65 (preserve 35% of input)

---

## Prompt Structure

### Sketch Prompt:
```
portrait close-up, 85mm lens, studio lighting, [character description]
```

### Reference View Prompts:
```
Generate a clean full-body reference view of character shown in the picture, keeping face details, age, identity, outfit and hairstyle consistent, they must be same. 
[view-specific: "full body, front view, standing, neutral pose, feet visible, solo, one person, centered, studio lighting, clean plain background"]
PRESERVE_IDENTITY: same person, exact same face, same facial features, same hairstyle
same outfit, same clothing, consistent character design
[character description]
```

---

## Cloud API Behavior

1. **GGUF Models Filtered:** Any GGUF model in pipeline profile is set to `None`, cloud uses default
2. **Workflow Set Forced:** `workflow_set` is forced to `"cloud_api"` when `_is_cloud=True`
3. **Loader Type Reset:** `loader_type="gguf"` is changed to `"standard"`
4. **Image Upload:** Init images are uploaded to cloud storage before workflow submission
5. **Output Node:** Uses `PreviewImage` instead of `SaveImage`
6. **Polling:** Waits 10s for job registration, then polls every 2s with max 20 consecutive 404s (40s timeout)

---

## Total Generations

1 sketch + 4 reference views = **5 total generations** per character
