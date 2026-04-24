import app.services.scene_composition_adapter as adapter


def test_infer_background_extras_policy_from_explicit_count():
    policy = adapter.infer_background_extras_policy(
        slide_context={"background_extras_count": 2},
        context_text="office scene",
        principal_count=2,
        requested_cast_count=2,
    )

    assert policy.allowed is True
    assert policy.min_count == 2
    assert policy.max_count == 2


def test_infer_background_extras_policy_from_unresolved_cast():
    policy = adapter.infer_background_extras_policy(
        slide_context={},
        context_text="empty hall",
        principal_count=2,
        requested_cast_count=4,
    )

    assert policy.allowed is False
    assert policy.min_count == 0
    assert policy.max_count == 0


def test_infer_background_extras_policy_disallow_flag():
    policy = adapter.infer_background_extras_policy(
        slide_context={"allow_background_extras": False, "background_extras_count": 3},
        context_text="crowd around hero",
        principal_count=1,
        requested_cast_count=1,
    )

    assert policy.allowed is False
    assert policy.max_count == 0


def test_infer_background_extras_policy_ignores_weak_crowd_mention():
    policy = adapter.infer_background_extras_policy(
        slide_context={},
        context_text="He remembers a crowd from his childhood story.",
        principal_count=1,
        requested_cast_count=1,
    )

    assert policy.allowed is False
    assert policy.max_count == 0


def test_infer_background_extras_policy_accepts_strong_crowd_signal():
    policy = adapter.infer_background_extras_policy(
        slide_context={},
        context_text="Night market with passersby in frame around the characters.",
        principal_count=2,
        requested_cast_count=2,
    )

    assert policy.allowed is True
    assert policy.max_count >= 1


def test_build_people_constraints_no_extras():
    rules = adapter.build_people_constraints(
        principal_count=2,
        has_location_reference=True,
        extras_policy=adapter.BackgroundExtrasPolicy(allowed=False),
    )
    joined = " ".join(rules).lower()

    assert "exactly 2 principal characters" in joined
    assert "do not add extra people" in joined
    assert "no bystanders" in joined
    assert "image 1" in joined


def test_build_people_constraints_with_exact_extras():
    rules = adapter.build_people_constraints(
        principal_count=1,
        has_location_reference=False,
        extras_policy=adapter.BackgroundExtrasPolicy(allowed=True, min_count=3, max_count=3),
    )
    joined = " ".join(rules).lower()

    assert "exactly 1 principal character" in joined
    assert "exactly 3 additional background extras" in joined
    assert "build background only from text" in joined


def test_ensure_english_prompt_keeps_english_text():
    text = "Use image 1 as reference and preserve layout unchanged."
    assert adapter.ensure_english_prompt(text) == text


def test_ensure_english_prompt_translates_when_cyrillic(monkeypatch):
    class _FakeTranslator:
        def translate(self, text: str) -> str:
            return "Use image 1 as reference."

    monkeypatch.setattr(adapter, "get_translator", lambda: _FakeTranslator())
    output = adapter.ensure_english_prompt("используй image 1 как референс")

    assert output == "Use image 1 as reference."


def test_build_story_action_hint_uses_slide_context_and_dialogue(monkeypatch):
    class _FakeTranslator:
        def translate(self, text: str) -> str:
            return text

    monkeypatch.setattr(adapter, "get_translator", lambda: _FakeTranslator())
    hint = adapter.build_story_action_hint(
        slide_context={
            "title": "Interrogation room",
            "exposition": "Detective leans over the table.",
            "dialogue": [{"speaker": "Detective", "text": "Show me the phone."}],
        },
        slide_visual="",
        scene_synopsis="A tense legal confrontation.",
    )

    lower = hint.lower()
    assert "interrogation room" in lower
    assert "detective leans over the table" in lower
    assert "show me the phone" in lower


def test_build_composition_guardrails_include_foreground_and_positions():
    rules = adapter.build_composition_guardrails(
        principal_count=2,
        has_location_reference=True,
        slot_positions=["left", "right"],
        action_hint="One points at evidence, one listens.",
    )
    joined = " ".join(rules).lower()

    assert "grounded actors" in joined
    assert "must interact" in joined
    assert "image 1 as an immutable background plate" in joined
    assert "slot 2" in joined
    assert "slot 3" in joined
    assert "story beat" in joined


def test_build_composition_negative_prompt_disallows_extras_for_solo():
    negative = adapter.build_composition_negative_prompt(
        principal_count=1,
        extras_policy=adapter.BackgroundExtrasPolicy(allowed=False),
    )
    lower = negative.lower()

    assert "duplicated person" in lower
    assert "merged body with background" in lower
    assert "static lineup" in lower
    assert "background extras" in lower


def test_build_slot_character_list_uses_slot_labels_only():
    text = adapter.build_slot_character_list(principal_count=2).lower()

    assert "character from image 2" in text
    assert "character from image 3" in text
    assert "distinct identity" in text


def test_enforce_slot_identity_labels_replaces_names():
    source = (
        "Place Alexey on the left. Keep Bottle of Justice on the right. "
        "Character 1 faces Character 2."
    )
    out = adapter.enforce_slot_identity_labels(
        source,
        slot2_name="Alexey",
        slot3_name="Bottle of Justice",
    )
    lower = out.lower()

    assert "alexey" not in lower
    assert "bottle of justice" not in lower
    assert "character from image 2" in lower
    assert "character from image 3" in lower


def test_normalize_composition_prompt_appends_mandatory_constraints(monkeypatch):
    class _FakeTranslator:
        def translate(self, text: str) -> str:
            return text

    monkeypatch.setattr(adapter, "get_translator", lambda: _FakeTranslator())
    normalized = adapter.normalize_composition_prompt(
        prompt="Place image 2 in scene.",
        people_constraints_text="Render exactly 1 principal character from image 2; do not duplicate this identity.",
        guardrails=["Use image 1 as an immutable background plate."],
        gritty=False,
        principal_count=1,
    )
    lower = normalized.lower()

    assert "exactly 1 principal character" in lower
    assert "immutable background plate" in lower
    assert "no extra principal characters" in lower
    assert "visible story-driven actions" in lower
    assert "preserve background plate geometry, perspective, and lighting" in lower
    assert "do not alter architecture or major props" in lower
    assert "identity lock" in lower


def test_normalize_composition_prompt_compacts_overlong_prompt(monkeypatch):
    class _FakeTranslator:
        def translate(self, text: str) -> str:
            return text

    monkeypatch.setattr(adapter, "get_translator", lambda: _FakeTranslator())
    long_prompt = " ".join(
        [
            "Compose full body scene.",
            "Preserve all unchanged elements exactly.",
            "Preserve all unchanged elements exactly.",
            "Preserve all unchanged elements exactly.",
            "Preserve all unchanged elements exactly.",
        ]
        + [f"Extra clause {idx}." for idx in range(120)]
    )
    normalized = adapter.normalize_composition_prompt(
        prompt=long_prompt,
        people_constraints_text="Render exactly 2 principal characters from image slots 2 and 3.",
        guardrails=[
            "Build a coherent background from text and keep camera layout physically consistent.",
            "Characters must perform visible story-driven actions; avoid idle standing.",
            "Image slot 2: keep this character clearly on the left half of the frame.",
            "Image slot 3: keep this character clearly on the right half of the frame.",
        ],
        gritty=False,
        principal_count=2,
    )

    assert len(normalized) <= 1600
    lower = normalized.lower()
    assert "render exactly 2 principal characters" in lower
    assert "preserve background plate geometry, perspective, and lighting" in lower
