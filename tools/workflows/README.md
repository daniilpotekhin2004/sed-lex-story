# ComfyUI Workflow Templates

This directory contains organized ComfyUI workflow configurations for different generation tasks.

## Template Categories

### Character Generation
- `character_txt2img_portrait.json` - Generate character portraits (768x1024)
- `character_img2img_variation.json` - Create character variations from existing images

### Scene Generation  
- `story_txt2img_scene.json` - Generate story scenes (1024x768)
- `txt2img_landscape.json` - General landscape generation
- `txt2img_variants.json` - Generate multiple scene variants (batch=4)

### World Building
- `world_txt2img_element.json` - Generate world elements and objects (640x480)
- `txt2img_square.json` - General square format generation

## Template Variables

All workflows support these template variables:
- `{{prompt}}` - Main generation prompt
- `{{negative_prompt}}` - Negative prompt for exclusions
- `{{character_id}}` - Character identifier for file naming
- `{{scene_id}}` - Scene identifier for file naming
- `{{entity_type}}` - World entity type (location, object, etc.)
- `{{entity_id}}` - World entity identifier
- `{{beat_id}}` - Story beat identifier
- `{{input_image}}` - Input image for img2img workflows

## Usage

These workflows are used by the backend ComfyUI client. The system automatically:
1. Loads the appropriate template based on generation type
2. Substitutes template variables with actual values
3. Applies LoRA models if specified
4. Queues the workflow for generation

## Customization

To customize workflows:
1. Copy an existing template
2. Modify node parameters (steps, CFG, dimensions, etc.)
3. Update template variables as needed
4. Test with the ComfyUI interface before deployment
