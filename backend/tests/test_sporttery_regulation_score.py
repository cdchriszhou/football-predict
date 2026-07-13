# -*- coding: utf-8 -*-
"""Sporttery CRS uses regulation-time scores only."""
from utils.score_prediction import (
    actual_score_for_match,
    actual_score_from_history,
    sporttery_actual_score,
)


def test_regulation_score_when_extra_time():
    assert sporttery_actual_score(
        result_a=3, result_b=1,
        regulation_a=1, regulation_b=1,
        extra_time=True,
    ) == "1:1"


def test_full_time_when_no_regulation_fields():
    assert sporttery_actual_score(
        result_a=2, result_b=0,
        extra_time=False,
    ) == "2:0"


def test_history_argentina_switzerland_regulation():
    hist = {
        "team_a": "阿根廷", "team_b": "瑞士",
        "result_a": 3, "result_b": 1,
        "regulation_a": 1, "regulation_b": 1,
        "extra_time": True,
    }
    assert actual_score_from_history(hist) == "1:1"


def test_actual_score_for_match_prefers_history_regulation():
    hist = {
        "team_a": "挪威", "team_b": "英格兰",
        "result_a": 1, "result_b": 2,
        "regulation_a": 1, "regulation_b": 1,
        "extra_time": True,
    }
    actual = actual_score_for_match(
        result_a=1, result_b=2,
        team_a="挪威", team_b="英格兰",
        hist=hist,
    )
    assert actual == "1:1"
