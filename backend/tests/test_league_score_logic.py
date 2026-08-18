"""League score-prediction must not reuse World Cup knockout / group-MD3 heuristics."""
from service.match_context import analyze_match_context, build_group_context
from service.rule_engine import RuleEngine
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


def test_empty_stage_prompt_defaults_to_league():
    class _Dummy(BaseLLMClient):
        async def predict(self, input):
            return None

        def model_name(self):
            return "dummy"

    prompt = _Dummy().build_prompt(PredictionInput(
        match_id=1,
        team_a=_club("巴萨", 1),
        team_b=_club("马拉加", 20),
        group_context=_league_ctx("联赛", 1),
    ))
    assert "五大联赛" in prompt
    assert "FIFA排名" not in prompt
    assert "淘汰赛特殊考量" not in prompt


def test_production_score_path_does_not_load_worldcup_group_data():
    import inspect
    import service.prediction_service as ps
    import api.predictions as api_pred
    import service.sporttery_plan_service as plan
    import service.sporttery_resolve as resolve

    for mod in (ps, api_pred, plan):
        src = inspect.getsource(mod)
        assert "load_group_standings" not in src
        assert "enrich_knockout_outlook" not in src
        assert "load_group_fifa_ranks" not in src
        assert "worldcup_group_standings" not in src

    resolve_src = inspect.getsource(resolve)
    assert "世界杯" not in resolve_src
    assert "World Cup" not in resolve_src


def test_score_job_defaults_are_premier_league():
    import inspect
    from data.competitions import DEFAULT_COMPETITION
    from service.batch_predict_job import run_batch_predict_job, start_batch_predict_job
    from service.sporttery_plan_service import get_today_sporttery_plan, _find_db_match

    assert DEFAULT_COMPETITION == "premier-league"
    assert inspect.signature(run_batch_predict_job).parameters["competition_slug"].default == "premier-league"
    assert inspect.signature(start_batch_predict_job).parameters["competition_slug"].default == "premier-league"
    assert inspect.signature(get_today_sporttery_plan).parameters["competition_slug"].default == "premier-league"
    assert inspect.signature(_find_db_match).parameters["competition_slug"].default == "premier-league"

