"""football-data score parsing (regulation vs penalties)."""
from crawler.football_data_client import extract_match_score, extract_match_scores


def test_extract_regulation_and_penalties():
    score = {
        "fullTime": {"home": 1, "away": 1},
        "penalties": {"home": 4, "away": 5},
    }
    parsed = extract_match_scores(score)
    assert parsed == {"reg_a": 1, "reg_b": 1, "pen_a": 4, "pen_b": 5}
    assert extract_match_score(score) == (1, 1)


def test_extract_live_half_time():
    score = {"halfTime": {"home": 0, "away": 1}}
    parsed = extract_match_scores(score)
    assert parsed["reg_a"] == 0
    assert parsed["reg_b"] == 1
    assert parsed["pen_a"] is None
