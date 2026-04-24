import app.services.ai_form_fill as ai_form_fill


def test_extract_json_prefers_sequence_object():
    text = (
        'noise {"foo": 1} more noise '
        '{"sequence": {"slides": [{"id": "s1", "title": "Beat"}]}} trailing'
    )
    parsed = ai_form_fill._extract_json(text)

    assert isinstance(parsed, dict)
    assert "sequence" in parsed
    assert isinstance(parsed["sequence"], dict)


def test_context_has_crowd_hints_requires_presence_signal():
    assert ai_form_fill._context_has_crowd_hints("He remembers a crowd from years ago.") is False
    assert ai_form_fill._context_has_crowd_hints("Rainy street with passersby in frame around them.") is True


def test_normalize_scene_sequence_payload_trims_text_and_disables_extras_without_crowd():
    sequence = {
        "slides": [
            {
                "id": "s1",
                "title": "T" * 250,
                "exposition": "E" * 700,
                "thought": "I" * 500,
                "dialogue": [{"speaker": "S" * 120, "text": "D" * 340}],
                "allow_background_extras": True,
                "background_extras_count": 4,
            }
        ]
    }
    normalized = ai_form_fill._normalize_scene_sequence_payload(
        sequence,
        context="Interior office with two people talking.",
    )
    slide = normalized["slides"][0]

    assert len(slide["title"]) <= ai_form_fill._SEQUENCE_TEXT_LIMITS["title"] + 3
    assert len(slide["exposition"]) <= ai_form_fill._SEQUENCE_TEXT_LIMITS["exposition"] + 3
    assert len(slide["thought"]) <= ai_form_fill._SEQUENCE_TEXT_LIMITS["thought"] + 3
    assert slide["allow_background_extras"] is False
    assert "background_extras_count" not in slide
    assert isinstance(slide["dialogue"], list)
    assert slide["dialogue"]
    assert len(slide["dialogue"][0]["speaker"]) <= ai_form_fill._DIALOGUE_SPEAKER_LIMIT + 3
    assert len(slide["dialogue"][0]["text"]) <= ai_form_fill._DIALOGUE_TEXT_LIMIT + 3
