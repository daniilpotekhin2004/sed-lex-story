import pytest

from app.domain.models import Project, ScenarioGraph, SceneNode, StyleProfile, CharacterPreset, SceneNodeCharacter
from app.infra.db import SessionLocal
from app.services.prompt_engine import PromptEngine


@pytest.mark.asyncio
async def test_prompt_engine_includes_style_and_characters():
    async with SessionLocal() as session:
        project = Project(name="Prompt Project")
        session.add(project)
        await session.flush()

        style = StyleProfile(
            project_id=project.id,
            name="Anime",
            base_prompt="anime style, vibrant",
            negative_prompt="low quality",
            resolution={"width": 720, "height": 480},
            cfg_scale=8.0,
            steps=28,
        )
        session.add(style)
        await session.flush()
        project.style_profile_id = style.id

        graph = ScenarioGraph(project_id=project.id, title="G1", description="graph")
        session.add(graph)
        await session.flush()

        scene = SceneNode(
            graph_id=graph.id,
            title="Scene 1",
            content="A hero enters the courtroom",
            synopsis="Hero introduction",
            scene_type="story",
        )
        session.add(scene)
        await session.flush()

        preset = CharacterPreset(
            name="Hero",
            description="Brave student",
            appearance_prompt="brave student lawyer with glasses",
            negative_prompt="blurry face",
        )
        session.add(preset)
        await session.flush()

        scene_char = SceneNodeCharacter(
            scene_id=scene.id,
            character_preset_id=preset.id,
            scene_context="holding legal documents",
            position="center",
            importance=0.9,
        )
        session.add(scene_char)
        await session.commit()

        engine = PromptEngine(session)
        bundle = await engine.build_for_scene(scene.id)
        assert bundle is not None
        assert "anime style" in bundle.prompt
        assert "brave student lawyer with glasses" in bundle.prompt
        assert bundle.negative_prompt and "low quality" in bundle.negative_prompt
        assert bundle.config["width"] == 720
        assert bundle.config["cfg_scale"] == 8.0


@pytest.mark.asyncio
async def test_prompt_engine_builds_template_when_no_style():
    async with SessionLocal() as session:
        project = Project(name="Template Project")
        session.add(project)
        await session.flush()

        graph = ScenarioGraph(project_id=project.id, title="G1", description="graph")
        session.add(graph)
        await session.flush()

        scene = SceneNode(
            graph_id=graph.id,
            title="Scene 1",
            content="Detective walks through rain-soaked neon street",
            synopsis="Tense opening",
            scene_type="story",
        )
        session.add(scene)
        await session.commit()

        engine = PromptEngine(session)
        bundle = await engine.build_for_scene(scene.id)

        assert bundle is not None
        assert "cinematic" in bundle.prompt.lower()
        assert "neon" in bundle.prompt
        assert bundle.config["shot"]
        assert bundle.negative_prompt


@pytest.mark.asyncio
async def test_prompt_engine_respects_character_consistency_seed():
    async with SessionLocal() as session:
        project = Project(name="Consistency Project")
        session.add(project)
        await session.flush()

        style = StyleProfile(
            project_id=project.id,
            name="Cinematic",
            seed_policy="character-consistent",
        )
        session.add(style)
        await session.flush()
        project.style_profile_id = style.id

        graph = ScenarioGraph(project_id=project.id, title="G1", description="graph")
        session.add(graph)
        await session.flush()

        scene1 = SceneNode(
            graph_id=graph.id,
            title="Scene 1",
            content="Detective questions a witness in a diner",
            synopsis="Calm talk",
            scene_type="story",
        )
        scene2 = SceneNode(
            graph_id=graph.id,
            title="Scene 2",
            content="Detective walks outside after the talk",
            synopsis="Reflective",
            scene_type="story",
        )
        session.add_all([scene1, scene2])
        await session.flush()

        hero = CharacterPreset(
            name="Detective",
            description="Experienced investigator",
            appearance_prompt="grizzled detective with trench coat and fedora",
        )
        session.add(hero)
        await session.flush()

        sc1 = SceneNodeCharacter(
            scene_id=scene1.id,
            character_preset_id=hero.id,
            scene_context="inside diner booth",
            position="center",
        )
        sc2 = SceneNodeCharacter(
            scene_id=scene2.id,
            character_preset_id=hero.id,
            scene_context="sidewalk at night",
            position="left",
        )
        session.add_all([sc1, sc2])
        await session.commit()

        engine = PromptEngine(session)
        bundle_one = await engine.build_for_scene(scene1.id)
        bundle_two = await engine.build_for_scene(scene2.id)

        assert bundle_one.config["seed"] == bundle_two.config["seed"]
        assert bundle_one.config["seed"] is not None
