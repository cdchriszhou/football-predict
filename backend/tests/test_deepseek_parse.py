from llm.deepseek_client import _parse_llm_json, _parse_response


def test_parse_trailing_comma():
    result = _parse_llm_json('{"win_rate": 50, "draw_rate": 30, "lose_rate": 20,}')
    assert result["win_rate"] == 50


def test_parse_code_fence():
    result = _parse_llm_json('```json\n{"win_rate": 40, "draw_rate": 30, "lose_rate": 30}\n```')
    assert result["win_rate"] == 40


def test_parse_response_full():
    data = {
        "choices": [{
            "message": {
                "content": (
                    '{"win_rate": 55, "draw_rate": 25, "lose_rate": 20, '
                    '"best_scores": ["2:1", "1:0", "1:1"], '
                    '"handicap_result": "胜", "total_goals": "大", '
                    '"reason": "测试", "confidence": 0.7}'
                )
            }
        }]
    }
    out = _parse_response(data, "deepseek-chat")
    assert out is not None
    assert out.win_rate == 55
    assert len(out.best_scores) == 3
