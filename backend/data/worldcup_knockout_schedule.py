"""FIFA 2026 World Cup knockout fixtures (Beijing wall-clock, UTC+8).

Round of 32 = 1/16决赛 (16 matches). Times derived from FIFA published GMT kickoffs.
"""
from __future__ import annotations

from datetime import datetime

# fmt: off
KNOCKOUT_FIXTURES: list[dict] = [
    # ── 1/16决赛 (Round of 32) ──
    {"stage": "1/16决赛", "match_no": 73, "team_a": "南非", "team_b": "加拿大",
     "match_time": datetime(2026, 6, 29, 3, 0), "location": "洛杉矶", "stadium": "索菲体育场"},
    {"stage": "1/16决赛", "match_no": 76, "team_a": "巴西", "team_b": "日本",
     "match_time": datetime(2026, 6, 30, 1, 0), "location": "休斯顿", "stadium": "NRG体育场"},
    {"stage": "1/16决赛", "match_no": 74, "team_a": "德国", "team_b": "巴拉圭",
     "match_time": datetime(2026, 6, 30, 4, 30), "location": "波士顿", "stadium": "吉列体育场"},
    {"stage": "1/16决赛", "match_no": 75, "team_a": "荷兰", "team_b": "摩洛哥",
     "match_time": datetime(2026, 6, 30, 9, 0), "location": "蒙特雷", "stadium": "BBVA体育场"},
    {"stage": "1/16决赛", "match_no": 78, "team_a": "科特迪瓦", "team_b": "挪威",
     "match_time": datetime(2026, 7, 1, 1, 0), "location": "达拉斯", "stadium": "AT&T体育场"},
    {"stage": "1/16决赛", "match_no": 77, "team_a": "法国", "team_b": "瑞典",
     "match_time": datetime(2026, 7, 1, 6, 0), "location": "纽约/新泽西", "stadium": "大都会人寿体育场"},
    {"stage": "1/16决赛", "match_no": 79, "team_a": "墨西哥", "team_b": "厄瓜多尔",
     "match_time": datetime(2026, 7, 1, 10, 0), "location": "墨西哥城", "stadium": "阿兹特克体育场"},
    {"stage": "1/16决赛", "match_no": 80, "team_a": "英格兰", "team_b": "刚果(金)",
     "match_time": datetime(2026, 7, 2, 0, 0), "location": "亚特兰大", "stadium": "梅赛德斯-奔驰体育场"},
    {"stage": "1/16决赛", "match_no": 82, "team_a": "比利时", "team_b": "塞内加尔",
     "match_time": datetime(2026, 7, 2, 4, 0), "location": "西雅图", "stadium": "流明体育场"},
    {"stage": "1/16决赛", "match_no": 81, "team_a": "美国", "team_b": "波黑",
     "match_time": datetime(2026, 7, 2, 9, 0), "location": "旧金山", "stadium": "李维斯体育场"},
    {"stage": "1/16决赛", "match_no": 84, "team_a": "西班牙", "team_b": "奥地利",
     "match_time": datetime(2026, 7, 3, 3, 0), "location": "洛杉矶", "stadium": "索菲体育场"},
    {"stage": "1/16决赛", "match_no": 83, "team_a": "葡萄牙", "team_b": "克罗地亚",
     "match_time": datetime(2026, 7, 3, 7, 0), "location": "多伦多", "stadium": "BMO体育场"},
    {"stage": "1/16决赛", "match_no": 85, "team_a": "瑞士", "team_b": "阿尔及利亚",
     "match_time": datetime(2026, 7, 3, 11, 0), "location": "温哥华", "stadium": "卑诗体育馆"},
    {"stage": "1/16决赛", "match_no": 88, "team_a": "澳大利亚", "team_b": "埃及",
     "match_time": datetime(2026, 7, 4, 2, 0), "location": "达拉斯", "stadium": "AT&T体育场"},
    {"stage": "1/16决赛", "match_no": 86, "team_a": "阿根廷", "team_b": "佛得角",
     "match_time": datetime(2026, 7, 4, 6, 0), "location": "迈阿密", "stadium": "硬石体育场"},
    {"stage": "1/16决赛", "match_no": 87, "team_a": "哥伦比亚", "team_b": "加纳",
     "match_time": datetime(2026, 7, 4, 9, 30), "location": "堪萨斯城", "stadium": "箭头体育场"},

    # ── 1/8决赛 (Round of 16) ──
    {"stage": "1/8决赛", "match_no": 89, "team_a": "第74场胜者", "team_b": "第77场胜者",
     "match_time": datetime(2026, 7, 5, 5, 0), "location": "费城", "stadium": "林肯金融球场"},
    {"stage": "1/8决赛", "match_no": 90, "team_a": "加拿大", "team_b": "第75场胜者",
     "match_time": datetime(2026, 7, 5, 0, 0), "location": "休斯顿", "stadium": "NRG体育场"},
    {"stage": "1/8决赛", "match_no": 91, "team_a": "第76场胜者", "team_b": "第78场胜者",
     "match_time": datetime(2026, 7, 6, 4, 0), "location": "纽约/新泽西", "stadium": "大都会人寿体育场"},
    {"stage": "1/8决赛", "match_no": 92, "team_a": "第79场胜者", "team_b": "第80场胜者",
     "match_time": datetime(2026, 7, 6, 8, 0), "location": "墨西哥城", "stadium": "阿兹特克体育场"},
    {"stage": "1/8决赛", "match_no": 93, "team_a": "第83场胜者", "team_b": "第84场胜者",
     "match_time": datetime(2026, 7, 7, 2, 0), "location": "达拉斯", "stadium": "AT&T体育场"},
    {"stage": "1/8决赛", "match_no": 94, "team_a": "第81场胜者", "team_b": "第82场胜者",
     "match_time": datetime(2026, 7, 7, 5, 0), "location": "西雅图", "stadium": "流明体育场"},
    {"stage": "1/8决赛", "match_no": 95, "team_a": "第86场胜者", "team_b": "第88场胜者",
     "match_time": datetime(2026, 7, 8, 0, 0), "location": "亚特兰大", "stadium": "梅赛德斯-奔驰体育场"},
    {"stage": "1/8决赛", "match_no": 96, "team_a": "第85场胜者", "team_b": "第87场胜者",
     "match_time": datetime(2026, 7, 8, 1, 0), "location": "温哥华", "stadium": "卑诗体育馆"},

    # ── 1/4决赛 ──
    {"stage": "1/4决赛", "match_no": 97, "team_a": "第89场胜者", "team_b": "第90场胜者",
     "match_time": datetime(2026, 7, 10, 4, 0), "location": "波士顿", "stadium": "吉列体育场"},
    {"stage": "1/4决赛", "match_no": 98, "team_a": "第93场胜者", "team_b": "第94场胜者",
     "match_time": datetime(2026, 7, 11, 0, 0), "location": "洛杉矶", "stadium": "索菲体育场"},
    {"stage": "1/4决赛", "match_no": 99, "team_a": "第91场胜者", "team_b": "第92场胜者",
     "match_time": datetime(2026, 7, 12, 5, 0), "location": "迈阿密", "stadium": "硬石体育场"},
    {"stage": "1/4决赛", "match_no": 100, "team_a": "第95场胜者", "team_b": "第96场胜者",
     "match_time": datetime(2026, 7, 12, 8, 0), "location": "堪萨斯城", "stadium": "箭头体育场"},

    # ── 半决赛 ──
    {"stage": "半决赛", "match_no": 101, "team_a": "第97场胜者", "team_b": "第98场胜者",
     "match_time": datetime(2026, 7, 15, 2, 0), "location": "达拉斯", "stadium": "AT&T体育场"},
    {"stage": "半决赛", "match_no": 102, "team_a": "第99场胜者", "team_b": "第100场胜者",
     "match_time": datetime(2026, 7, 16, 3, 0), "location": "亚特兰大", "stadium": "梅赛德斯-奔驰体育场"},

    # ── 季军赛 / 决赛 ──
    {"stage": "季军赛", "match_no": 103, "team_a": "第101场负者", "team_b": "第102场负者",
     "match_time": datetime(2026, 7, 19, 5, 0), "location": "迈阿密", "stadium": "硬石体育场"},
    {"stage": "决赛", "match_no": 104, "team_a": "第101场胜者", "team_b": "第102场胜者",
     "match_time": datetime(2026, 7, 20, 3, 0), "location": "纽约/新泽西", "stadium": "大都会人寿体育场"},
]
# fmt: on


def build_knockout_matches() -> list[dict]:
    """Normalize knockout fixtures for schedule sync (group_name empty)."""
    out = []
    for fx in KNOCKOUT_FIXTURES:
        out.append({
            "stage": fx["stage"],
            "group_name": "",
            "team_a": fx["team_a"],
            "team_b": fx["team_b"],
            "match_time": fx["match_time"],
            "location": fx["location"],
            "stadium": fx["stadium"],
            "match_no": fx.get("match_no"),
        })
    return out


def knockout_kickoff_by_teams() -> dict[tuple[str, str], datetime]:
    from data.worldcup_venues import canonical_team_order

    mapping: dict[tuple[str, str], datetime] = {}
    for fx in KNOCKOUT_FIXTURES:
        if fx["team_a"].startswith("第") or fx["team_b"].startswith("第"):
            continue
        ta, tb = canonical_team_order(fx["team_a"], fx["team_b"])
        mapping[(ta, tb)] = fx["match_time"]
    return mapping
