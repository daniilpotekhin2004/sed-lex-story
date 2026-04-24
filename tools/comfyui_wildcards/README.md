# ComfyUI Character Sheet Wildcards Setup

## Quick Setup

1. **Copy wildcard files to ComfyUI:**
   ```
   Copy all .txt files from this directory to:
   ComfyUI/web/extensions/wildcards/
   ```

2. **Use in ComfyUI nodes:**
   - For random generation: `{__character_sheet_main__}`
   - For specific views: Use the three prompts below

## Three Main Prompts for Character Sheet Nodes

### Front View Node:
```
Full-body front view of the character, {__pose_type__}, {__gaze_direction__}, {__action_detail__}, {__facial_expression__}, {__body_language__}, {__outfit_detail__}, clean white background, professional character design, consistent lighting, make sure the entire body is visible. Keep the character's appearance perfectly consistent.
```

### Back View Node:
```
Full-body back view of the character, {__pose_type__}, rear perspective, {__action_detail__}, {__body_language__}, {__outfit_detail__}, clean white background, professional character design, consistent lighting, make sure the entire body is visible. Keep the character's appearance perfectly consistent.
```

### Side View Node:
```
Full-body side view of the character, {__pose_type__}, profile perspective, {__action_detail__}, {__body_language__}, {__outfit_detail__}, clean white background, professional character design, consistent lighting, make sure the entire body is visible. Keep the character's appearance perfectly consistent.
```

## Available Wildcards

- `{__pose_type__}` - Character pose variations
- `{__gaze_direction__}` - Where character is looking
- `{__action_detail__}` - What character is doing
- `{__facial_expression__}` - Facial expression
- `{__body_language__}` - Overall body posture
- `{__outfit_detail__}` - Clothing style
- `{__lighting_mood__}` - Lighting variations
- `{__art_style__}` - Art style variations

## Consistency Tips

1. **Use same seed** across all three views for character consistency
2. **Keep outfit and facial features** consistent by using same character description
3. **Only randomize pose and angle** for variety while maintaining character identity

## File Structure
```
ComfyUI/web/extensions/wildcards/
├── character_sheet_main.txt
├── pose_type.txt
├── gaze_direction.txt
├── action_detail.txt
├── facial_expression.txt
├── body_language.txt
├── outfit_detail.txt
├── lighting_mood.txt
└── art_style.txt
```