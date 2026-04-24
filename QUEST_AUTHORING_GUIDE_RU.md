# PipelineProfile v1

Purpose
- Single source of truth for SD parameters (model/vae/sampler/scheduler/steps/cfg/resolution/seed/loras).
- Versioned profiles to keep outputs reproducible.

Config file
- Location: `backend/app/config/pipeline_profiles.json`
- Override path: `PIPELINE_PROFILE_PATH` in `.env`

Schema (JSON)
```
{
  "defaults": {
    "scene": { "profile_id": "sd35_default", "version": 1 },
    "character_ref": { "profile_id": "sd35_character_ref", "version": 1 }
  },
  "profiles": [
    {
      "profile_id": "sd35_default",
      "version": 1,
      "model_checkpoint": "sd3.5_large.safetensors",
      "vae": "",
      "sampler": "dpmpp_2m",
      "scheduler": "karras",
      "steps": 28,
      "cfg_scale": 5.0,
      "width": 640,
      "height": 480,
      "seed_policy": "random",
      "loras": []
    }
  ]
}
```

Seed policy
- `fixed`: uses the profile `seed` if provided, else a stable hash of profile id/version.
- `random`: random per request, but still logged.
- `derived`: stable hash. For characters: `character_id + slot + profile_version`.

LoRA handling
- Requests pass `loras` as list of `{name, weight}`.
- Legacy `<lora:...>` tokens are parsed into `loras` and stripped for ComfyUI.
- A1111 path re-inserts tokens for compatibility.

Adding a new profile
1) Add a new entry in `backend/app/config/pipeline_profiles.json`.
2) Increment `version` for changes; keep old versions for reproducibility.
3) Optionally update `defaults` to point a kind (scene/character_ref/world_preview) to the new version.

Regression runner
- Edit `pipeline_regression_cases.json` (set real LoRA filename).
- Record hashes:
  - `python test_pipeline_regression.py --record`
- Verify:
  - `python test_pipeline_regression.py`
