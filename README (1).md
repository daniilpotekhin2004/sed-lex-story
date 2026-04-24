{
  "id": "step3-qwen-scene",
  "revision": 0,
  "last_node_id": 15,
  "last_link_id": 18,
  "nodes": [
    {
      "id": 1,
      "type": "UnetLoaderGGUF",
      "pos": [
        -420,
        -40
      ],
      "size": [
        270,
        113.328125
      ],
      "flags": {},
      "order": 0,
      "mode": 0,
      "inputs": [],
      "outputs": [
        {
          "name": "MODEL",
          "type": "MODEL",
          "links": [
            1
          ]
        }
      ],
      "properties": {
        "Node name for S&R": "UnetLoaderGGUF"
      },
      "widgets_values": [
        "qwen-rapid-nsfw-v9.0-Q4_K_M.gguf"
      ],
      "color": "#322",
      "bgcolor": "#533"
    },
    {
      "id": 2,
      "type": "CLIPLoaderGGUF",
      "pos": [
        -420,
        100
      ],
      "size": [
        270,
        148
      ],
      "flags": {},
      "order": 1,
      "mode": 0,
      "inputs": [],
      "outputs": [
        {
          "name": "CLIP",
          "type": "CLIP",
          "links": [
            2
          ]
        }
      ],
      "properties": {
        "Node name for S&R": "CLIPLoaderGGUF"
      },
      "widgets_values": [
        "Qwen2.5-VL-7B-Instruct-abliterated.Q8_0.gguf",
        "qwen_image"
      ],
      "color": "#322",
      "bgcolor": "#533"
    },
    {
      "id": 3,
      "type": "VAELoader",
      "pos": [
        -420,
        280
      ],
      "size": [
        270,
        113.328125
      ],
      "flags": {},
      "order": 2,
      "mode": 0,
      "inputs": [],
      "outputs": [
        {
          "name": "VAE",
          "type": "VAE",
          "links": [
            3,
            4
          ]
        }
      ],
      "properties": {
        "Node name for S&R": "VAELoader"
      },
      "widgets_values": [
        "qwen-image\\\\qwen_image_vae.safetensors"
      ],
      "color": "#322",
      "bgcolor": "#533"
    },
    {
      "id": 4,
      "type": "LoraLoader",
      "pos": [
        -420,
        420
      ],
      "size": [
        270,
        201.328125
      ],
      "flags": {},
      "order": 3,
      "mode": 0,
      "inputs": [
        {
          "name": "model",
          "type": "MODEL",
          "link": 1
        },
        {
          "name": "clip",
          "type": "CLIP",
          "link": 2
        }
      ],
      "outputs": [
        {
          "name": "MODEL",
          "type": "MODEL",
          "links": [
            5
          ]
        },
        {
          "name": "CLIP",
          "type": "CLIP",
          "links": [
            6,
            7
          ]
        }
      ],
      "properties": {
        "Node name for S&R": "LoraLoader"
      },
      "widgets_values": [
        "ultra_realistic_hyperdetailed_qwen.safetensors",
        1.0,
        0.4
      ],
      "color": "#322",
      "bgcolor": "#533"
    },
    {
      "id": 5,
      "type": "LoadImage",
      "pos": [
        -100,
        700
      ],
      "size": [
        493.75,
        846.71875
      ],
      "flags": {},
      "order": 4,
      "mode": 0,
      "inputs": [],
      "outputs": [
        {
          "name": "IMAGE",
          "type": "IMAGE",
          "links": [
            8
          ]
        },
        {
          "name": "MASK",
          "type": "MASK",
          "links": null
        }
      ],
      "properties": {
        "Node name for S&R": "LoadImage"
      },
      "widgets_values": [
        "{{reference_image}}",
        "image"
      ],
      "color": "#322",
      "bgcolor": "#533"
    },
    {
      "id": 6,
      "type": "CLIPTextEncode",
      "pos": [
        420,
        100
      ],
      "size": [
        520,
        240
      ],
      "flags": {},
      "order": 5,
      "mode": 0,
      "inputs": [
        {
          "name": "clip",
          "type": "CLIP",
          "link": 6
        }
      ],
      "outputs": [
        {
          "name": "CONDITIONING",
          "type": "CONDITIONING",
          "links": [
            9
          ]
        }
      ],
      "properties": {
        "Node name for S&R": "CLIPTextEncode"
      },
      "widgets_values": [
        "{{scene_prompt}}"
      ],
      "title": "Scene Prompt",
      "color": "#232",
      "bgcolor": "#353"
    },
    {
      "id": 7,
      "type": "CLIPTextEncode",
      "pos": [
        420,
        380
      ],
      "size": [
        520,
        240
      ],
      "flags": {},
      "order": 6,
      "mode": 0,
      "inputs": [
        {
          "name": "clip",
          "type": "CLIP",
          "link": 7
        }
      ],
      "outputs": [
        {
          "name": "CONDITIONING",
          "type": "CONDITIONING",
          "links": [
            10
          ]
        }
      ],
      "properties": {
        "Node name for S&R": "CLIPTextEncode"
      },
      "widgets_values": [
        "{{negative_prompt}}"
      ],
      "title": "Negative Prompt",
      "color": "#322",
      "bgcolor": "#533"
    },
    {
      "id": 8,
      "type": "VAEEncode",
      "pos": [
        420,
        660
      ],
      "size": [
        225,
        121.1875
      ],
      "flags": {},
      "order": 7,
      "mode": 0,
      "inputs": [
        {
          "name": "pixels",
          "type": "IMAGE",
          "link": 8
        },
        {
          "name": "vae",
          "type": "VAE",
          "link": 3
        }
      ],
      "outputs": [
        {
          "name": "LATENT",
          "type": "LATENT",
          "links": [
            11
          ]
        }
      ],
      "properties": {
        "Node name for S&R": "VAEEncode"
      },
      "widgets_values": []
    },
    {
      "id": 9,
      "type": "KSampler",
      "pos": [
        980,
        100
      ],
      "size": [
        362.3125,
        380.375
      ],
      "flags": {},
      "order": 8,
      "mode": 0,
      "inputs": [
        {
          "name": "model",
          "type": "MODEL",
          "link": 5
        },
        {
          "name": "positive",
          "type": "CONDITIONING",
          "link": 9
        },
        {
          "name": "negative",
          "type": "CONDITIONING",
          "link": 10
        },
        {
          "name": "latent_image",
          "type": "LATENT",
          "link": 11
        }
      ],
      "outputs": [
        {
          "name": "LATENT",
          "type": "LATENT",
          "links": [
            12
          ]
        }
      ],
      "properties": {
        "Node name for S&R": "KSampler"
      },
      "widgets_values": [
        -1,
        "randomize",
        9,
        1.0,
        "euler",
        "beta",
        0.65
      ]
    },
    {
      "id": 10,
      "type": "VAEDecode",
      "pos": [
        1380,
        120
      ],
      "size": [
        225,
        121.1875
      ],
      "flags": {},
      "order": 9,
      "mode": 0,
      "inputs": [
        {
          "name": "samples",
          "type": "LATENT",
          "link": 12
        },
        {
          "name": "vae",
          "type": "VAE",
          "link": 4
        }
      ],
      "outputs": [
        {
          "name": "IMAGE",
          "type": "IMAGE",
          "links": [
            13,
            14
          ]
        }
      ],
      "properties": {
        "Node name for S&R": "VAEDecode"
      },
      "widgets_values": []
    },
    {
      "id": 11,
      "type": "SaveImage",
      "pos": [
        1640,
        60
      ],
      "size": [
        420,
        420
      ],
      "flags": {},
      "order": 10,
      "mode": 0,
      "inputs": [
        {
          "name": "images",
          "type": "IMAGE",
          "link": 13
        }
      ],
      "outputs": [],
      "properties": {
        "Node name for S&R": "SaveImage"
      },
      "widgets_values": [
        "lwq/characters/{{character_id}}/step3_scene"
      ]
    },
    {
      "id": 12,
      "type": "PreviewImage",
      "pos": [
        1640,
        520
      ],
      "size": [
        420,
        310
      ],
      "flags": {},
      "order": 11,
      "mode": 0,
      "inputs": [
        {
          "name": "images",
          "type": "IMAGE",
          "link": 14
        }
      ],
      "outputs": [],
      "properties": {
        "Node name for S&R": "PreviewImage"
      },
      "widgets_values": []
    }
  ],
  "links": [
    [
      1,
      1,
      0,
      4,
      0,
      "MODEL"
    ],
    [
      2,
      2,
      0,
      4,
      1,
      "CLIP"
    ],
    [
      3,
      3,
      0,
      8,
      1,
      "VAE"
    ],
    [
      4,
      3,
      0,
      10,
      1,
      "VAE"
    ],
    [
      5,
      4,
      0,
      9,
      0,
      "MODEL"
    ],
    [
      6,
      4,
      1,
      6,
      0,
      "CLIP"
    ],
    [
      7,
      4,
      1,
      7,
      0,
      "CLIP"
    ],
    [
      8,
      5,
      0,
      8,
      0,
      "IMAGE"
    ],
    [
      9,
      6,
      0,
      9,
      1,
      "CONDITIONING"
    ],
    [
      10,
      7,
      0,
      9,
      2,
      "CONDITIONING"
    ],
    [
      11,
      8,
      0,
      9,
      3,
      "LATENT"
    ],
    [
      12,
      9,
      0,
      10,
      0,
      "LATENT"
    ],
    [
      13,
      10,
      0,
      11,
      0,
      "IMAGE"
    ],
    [
      14,
      10,
      0,
      12,
      0,
      "IMAGE"
    ]
  ],
  "groups": [
    {
      "title": "Step 1 - Load Character Reference",
      "bounding": [
        -140,
        640,
        560,
        920
      ],
      "color": "#3f789e",
      "font_size": 24
    },
    {
      "title": "Step 2 - Scene Generation",
      "bounding": [
        380,
        40,
        620,
        600
      ],
      "color": "#3f789e",
      "font_size": 24
    },
    {
      "title": "Step 3 - Output",
      "bounding": [
        1320,
        40,
        780,
        820
      ],
      "color": "#3f789e",
      "font_size": 24
    }
  ],
  "config": {},
  "extra": {
    "ds": {
      "scale": 0.85,
      "offset": [
        200,
        -50
      ]
    },
    "frontendVersion": "1.23.4"
  },
  "version": 0.4
}