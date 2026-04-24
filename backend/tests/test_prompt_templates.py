from app.services.prompt_templates import PromptTemplateLibrary


def test_scene_prompt_translator_infers_shot_and_lighting():
    templates = PromptTemplateLibrary()
    bundle = templates.build_scene_prompt("A hero runs through neon city streets at night in the rain")

    assert "dynamic action shot" in bundle.prompt
    assert "neon city lights" in bundle.prompt
    assert "night lighting" in bundle.prompt
    assert "blurry" in bundle.negative_prompt
    assert bundle.config["shot"].startswith("dynamic")
    assert bundle.config["lighting"].startswith("neon")


def test_character_prompt_captures_traits_and_anchor():
    templates = PromptTemplateLibrary()
    prompt = templates.build_character_prompt(
        name="Rhea",
        description="cyberpunk hacker with glowing visor",
        traits=["hooded jacket", "glowing implants"],
        role="protagonist",
        anchor_token="char-rhea",
    )

    assert "cyberpunk hacker" in prompt.prompt
    assert "hooded jacket" in prompt.prompt
    assert "turnaround character sheet" in prompt.prompt
    assert "consistency tag char-rhea" in prompt.prompt
    assert "asymmetry" in prompt.negative_prompt


def test_stable_seed_remains_consistent_for_same_cast():
    templates = PromptTemplateLibrary()
    seed_a = templates.stable_seed("project-1", ["a", "b", "c"])
    seed_b = templates.stable_seed("project-1", ["c", "b", "a"])
    seed_other = templates.stable_seed("project-1", ["a", "b", "d"])

    assert seed_a == seed_b
    assert seed_a != seed_other
    assert isinstance(seed_a, int)
