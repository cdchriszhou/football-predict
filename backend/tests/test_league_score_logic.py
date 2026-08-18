"""League score-prediction must not reuse World Cup knockout / group-MD3 heuristics."""
from service.match_context import analyze_match_context, build_group_context
from service.rule_engine import RuleEngine
from data.worldcup_group_standings import format_group_situation
from llm.base_client import BaseLLMClient, PredictionInput


def _club(name: str, rank: int, tactic: str = "传控") -> dict:
    pct = max(0.0, 1.0 - (rank - 1) / 19.0)
    base = 62 + pct * 28
    return {
        "name": name,
        "rank": rank,
        "attack": round(base + pct * 6),
        "defend": round(base - (1 - pct) * 4),
        "midfield": round(base),
        "speed": round(base - 2),
        "physical": round(base - 1),
        "tactic": tactic,
    }


def _league_ctx(stage: str = "第1轮", matchday: int = 1) -> dict:
    return build_group_context(
        stage, "", matchday, "巴萨", "马拉加", 1, 20, home_side_override="a",
    )


def test_league_round_is_not_worldcup_knockout_in_rule_engine():
    engine = RuleEngine()
    barca = _club("巴萨", 1)
    malaga = _club("马拉加", 20, "防守反击")
    league = engine.evaluate(barca, malaga, group_context=_league_ctx("第1轮", 1))
    knockout = engine.evaluate(
        barca, malaga,
        group_context={"stage": "1/8决赛", "rank_gap": 19},
    )
    assert league.expected_a + league.expected_b > knockout.expected_a + knockout.expected_b
    assert league.draw_rate < knockout.draw_rate


def test_league_round_3_is_not_group_matchday_three():
    ctx = _league_ctx("第3轮", 3)
    assert ctx["is_final_group_match"] is False
    analysis = analyze_match_context(
        _club("巴萨", 1),
        _club("皇马", 2),
        ctx,
    )
    joined = "".join(analysis.alerts)
    assert "默契" not in joined
    assert "末轮" not in joined
    assert "淘汰赛" not in joined


def test_league_defensive_underdog_not_extra_time_alert():
    ctx = _league_ctx("第1轮", 1)
    analysis = analyze_match_context(
        _club("巴萨", 1, "传控"),
        _club("赫塔费", 14, "铁桶防守"),
        ctx,
    )
    assert not any("淘汰赛" in a or "加时" in a or "点球" in a for a in analysis.alerts)


def test_league_prompt_does_not_include_knockout_instructions():
    class _Dummy(BaseLLMClient):
        async def predict(self, input):
            return None

        def model_name(self):
            return "dummy"

    prompt = _Dummy().build_prompt(PredictionInput(
        match_id=1,
        team_a=_club("巴萨", 1),
        team_b=_club("马拉加", 20),
        group_context=_league_ctx("第1轮", 1),
    ))
    assert "俱乐部联赛" in prompt
    assert "不要套用世界杯淘汰赛" in prompt
    assert "拖入加时赛" not in prompt
    assert format_group_situation(_league_ctx("第2轮", 2), "巴萨", "马拉加") == ""


def test_worldcup_group_md3_collusion_still_applies():
    ctx = build_group_context(
        "小组赛", "A", 3, "巴西", "克罗地亚", 5, 12,
    )
    assert ctx["is_final_group_match"] is True
    analysis = analyze_match_context(
        {"name": "巴西", "rank": 5, "tactic": "传控"},
        {"name": "克罗地亚", "rank": 12, "tactic": "防反"},
        ctx,
    )
    assert analysis.draw_adjustment > 0
