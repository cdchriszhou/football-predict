"""Unit tests for multi-model digital lottery AI fusion (no network)."""

from service.digital_ai import fuse_ai_picks, model_display_name


def test_fuse_prefers_consensus():
    model_results = [
        {
            "model": "deepseek",
            "parsed": {
                "picks": [
                    {"digits": [1, 2, 3], "confidence": 0.7, "reason": "ds-a"},
                    {"digits": [4, 5, 6], "confidence": 0.6, "reason": "ds-b"},
                ]
            },
        },
        {
            "model": "qwen",
            "parsed": {
                "picks": [
                    {"digits": [1, 2, 3], "confidence": 0.65, "reason": "qw-a"},
                    {"digits": [7, 8, 9], "confidence": 0.9, "reason": "qw-b"},
                ]
            },
        },
        {
            "model": "glm",
            "parsed": {
                "picks": [
                    {"digits": [1, 2, 3], "confidence": 0.55, "reason": "glm-a"},
                ]
            },
        },
    ]

    def validate(item):
        digits = item.get("digits")
        if not isinstance(digits, list) or len(digits) != 3:
            return None
        return [int(x) for x in digits]

    def build_rec(digits, conf, reason, models):
        return {
            "digits": digits,
            "display": " ".join(map(str, digits)),
            "confidence": conf,
            "reason": reason,
            "bets": 1,
            "mode": "direct",
            "label": "AI",
        }

    out = fuse_ai_picks(
        model_results,
        extract_items=lambda p: p.get("picks") or [],
        validate_item=validate,
        build_rec=build_rec,
        limit=3,
    )
    assert len(out) == 3
    assert out[0]["digits"] == [1, 2, 3]
    assert set(out[0]["models"]) == {"deepseek", "qwen", "glm"}
    assert "多模型共识" in out[0]["reason"]
    assert out[0]["confidence"] >= 0.7  # consensus boost


def test_model_display_name():
    assert model_display_name("deepseek") == "DeepSeek"
    assert model_display_name("qwen") == "Qwen"
    assert model_display_name("glm") == "GLM"
