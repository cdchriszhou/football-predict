"""Knockout schedule must lock tournament semifinalists / finalists."""
from service.tournament_service import (
    TournamentPrediction,
    _apply_knockout_constraints,
)


def test_apply_constraints_replaces_brazil_with_locked_semis():
    pred = TournamentPrediction(
        champion="巴西",
        runner_up="西班牙",
        semifinalists=["西班牙", "巴西", "法国", "英格兰"],
        reason="赛前看好巴西",
        model_used="test",
        confidence=0.7,
    )
    progress = {
        "semifinalists": ["西班牙", "法国", "英格兰", "阿根廷"],
        "finalists": ["西班牙", "阿根廷"],
        "champion": None,
        "runner_up": None,
        "notes": ["四强已由半决赛对阵锁定：西班牙、法国、英格兰、阿根廷"],
    }
    out = _apply_knockout_constraints(pred, progress)
    assert set(out.semifinalists) == {"西班牙", "法国", "英格兰", "阿根廷"}
    assert "巴西" not in out.semifinalists
    assert out.champion in {"西班牙", "阿根廷"}
    assert out.runner_up in {"西班牙", "阿根廷"}
    assert out.champion != out.runner_up
    assert "赛程锁定" in out.reason
    assert out.confidence >= 0.88


def test_apply_constraints_locks_finished_final():
    pred = TournamentPrediction(
        champion="法国",
        runner_up="英格兰",
        semifinalists=["法国", "英格兰", "西班牙", "阿根廷"],
        reason="旧预测",
        model_used="test",
        confidence=0.6,
    )
    progress = {
        "semifinalists": ["西班牙", "法国", "英格兰", "阿根廷"],
        "finalists": ["西班牙", "阿根廷"],
        "champion": "西班牙",
        "runner_up": "阿根廷",
        "notes": ["决赛已结束，冠军锁定：西班牙"],
    }
    out = _apply_knockout_constraints(pred, progress)
    assert out.champion == "西班牙"
    assert out.runner_up == "阿根廷"
    assert out.confidence >= 0.95
