"""
Schedule crawler — real 2026 FIFA World Cup match schedule.

All 72 group-stage matches with exact Beijing times (UTC+8).
Data source: FIFA official match schedule, confirmed May 2026.
Times verified against multiple sources (FIFA.com, Olympics.com, Sky Sports).
"""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sqldelete
from db.models import Match, Odds, Prediction
from data.status_constants import MATCH_FINISHED, MATCH_UPCOMING
from data.worldcup_venues import venue_for_match, canonical_team_order
from data.worldcup_knockout_schedule import build_knockout_matches
from .base_crawler import _log_crawler, _safe_crawler_fail, crawler_lock
from utils.logger import logger


# Real 2026 World Cup groups (48 teams, 12 groups)
WORLDCUP_GROUPS = {
    "A": ["墨西哥", "南非", "韩国", "捷克"],
    "B": ["加拿大", "波黑", "卡塔尔", "瑞士"],
    "C": ["巴西", "摩洛哥", "海地", "苏格兰"],
    "D": ["美国", "巴拉圭", "澳大利亚", "土耳其"],
    "E": ["德国", "库拉索", "科特迪瓦", "厄瓜多尔"],
    "F": ["荷兰", "日本", "瑞典", "突尼斯"],
    "G": ["比利时", "埃及", "伊朗", "新西兰"],
    "H": ["西班牙", "佛得角", "沙特阿拉伯", "乌拉圭"],
    "I": ["法国", "塞内加尔", "伊拉克", "挪威"],
    "J": ["阿根廷", "阿尔及利亚", "奥地利", "约旦"],
    "K": ["葡萄牙", "刚果(金)", "乌兹别克斯坦", "哥伦比亚"],
    "L": ["英格兰", "克罗地亚", "加纳", "巴拿马"],
}


def _real_time_slots():
    """Build 72 exact Beijing-time slots for group stage matches.

    Slots are ordered by matchday (1→2→3), then group (A→L),
    matching the iteration order in run_schedule_crawler().

    Matchday 3: both matches in each group kick off simultaneously
    (per FIFA rules), so consecutive slots share the same datetime.
    """
    slots = []

    # Matchday 1 — June 12 to June 18 (Beijing time)
    md1 = [
        datetime(2026, 6, 12, 3, 0), datetime(2026, 6, 12, 10, 0),
        datetime(2026, 6, 13, 3, 0), datetime(2026, 6, 14, 3, 0),
        datetime(2026, 6, 14, 6, 0), datetime(2026, 6, 14, 9, 0),
        datetime(2026, 6, 13, 9, 0), datetime(2026, 6, 14, 12, 0),
        datetime(2026, 6, 15, 1, 0), datetime(2026, 6, 15, 7, 0),
        datetime(2026, 6, 15, 4, 0), datetime(2026, 6, 15, 10, 0),
        datetime(2026, 6, 16, 3, 0), datetime(2026, 6, 16, 9, 0),
        datetime(2026, 6, 16, 0, 0), datetime(2026, 6, 16, 6, 0),
        datetime(2026, 6, 17, 3, 0), datetime(2026, 6, 17, 6, 0),
        datetime(2026, 6, 17, 9, 0), datetime(2026, 6, 17, 12, 0),
        datetime(2026, 6, 18, 1, 0), datetime(2026, 6, 18, 10, 0),
        datetime(2026, 6, 18, 4, 0), datetime(2026, 6, 18, 7, 0),
    ]

    # Matchday 2 — June 19 to June 24 (Beijing time)
    md2 = [
        datetime(2026, 6, 19, 0, 0), datetime(2026, 6, 19, 9, 0),
        datetime(2026, 6, 19, 3, 0), datetime(2026, 6, 19, 6, 0),
        datetime(2026, 6, 20, 6, 0), datetime(2026, 6, 20, 9, 0),
        datetime(2026, 6, 19, 12, 0), datetime(2026, 6, 20, 3, 0),
        datetime(2026, 6, 21, 4, 0), datetime(2026, 6, 21, 8, 0),
        datetime(2026, 6, 21, 1, 0), datetime(2026, 6, 21, 12, 0),
        datetime(2026, 6, 22, 3, 0), datetime(2026, 6, 22, 9, 0),
        datetime(2026, 6, 22, 0, 0), datetime(2026, 6, 22, 6, 0),
        datetime(2026, 6, 23, 5, 0), datetime(2026, 6, 23, 8, 0),
        datetime(2026, 6, 23, 1, 0), datetime(2026, 6, 23, 11, 0),
        datetime(2026, 6, 24, 1, 0), datetime(2026, 6, 24, 10, 0),
        datetime(2026, 6, 24, 4, 0), datetime(2026, 6, 24, 7, 0),
    ]

    # Matchday 3 — June 25 to June 28 (Beijing time)
    md3 = [
        datetime(2026, 6, 25, 9, 0), datetime(2026, 6, 25, 9, 0),
        datetime(2026, 6, 25, 3, 0), datetime(2026, 6, 25, 3, 0),
        datetime(2026, 6, 25, 6, 0), datetime(2026, 6, 25, 6, 0),
        datetime(2026, 6, 26, 10, 0), datetime(2026, 6, 26, 10, 0),
        datetime(2026, 6, 26, 4, 0), datetime(2026, 6, 26, 4, 0),
        datetime(2026, 6, 26, 7, 0), datetime(2026, 6, 26, 7, 0),
        datetime(2026, 6, 27, 11, 0), datetime(2026, 6, 27, 11, 0),
        datetime(2026, 6, 27, 8, 0), datetime(2026, 6, 27, 8, 0),
        datetime(2026, 6, 27, 3, 0), datetime(2026, 6, 27, 3, 0),
        datetime(2026, 6, 28, 10, 0), datetime(2026, 6, 28, 10, 0),
        datetime(2026, 6, 28, 7, 30), datetime(2026, 6, 28, 7, 30),
        datetime(2026, 6, 28, 5, 0), datetime(2026, 6, 28, 5, 0),
    ]

    return md1 + md2 + md3


# Real venues used in the tournament
VENUES = [
    ("墨西哥城", "阿兹特克体育场"),
    ("萨波潘", "阿克伦体育场"),
    ("蒙特雷", "BBVA体育场"),
    ("多伦多", "BMO体育场"),
    ("温哥华", "卑诗体育馆"),
    ("洛杉矶", "索菲体育场"),
    ("旧金山", "李维斯体育场"),
    ("西雅图", "流明体育场"),
    ("纽约/新泽西", "大都会人寿体育场"),
    ("波士顿", "吉列体育场"),
    ("费城", "林肯金融体育场"),
    ("迈阿密", "硬石体育场"),
    ("亚特兰大", "梅赛德斯-奔驰体育场"),
    ("达拉斯", "AT&T体育场"),
    ("休斯顿", "NRG体育场"),
    ("堪萨斯城", "箭头体育场"),
]


MATCHDAY_PAIRINGS = [
    [(0, 1), (2, 3)],
    [(0, 2), (1, 3)],
    [(0, 3), (1, 2)],
]

# 2026 东道主主场：按轮次固定球场（避免轮询 VENUES 错配）
_HOST_VENUES: dict[str, dict[int, tuple[str, str]]] = {
    "墨西哥": {
        1: ("墨西哥城", "阿兹特克体育场"),
        2: ("瓜达拉哈拉", "瓜达拉哈拉体育场"),
        3: ("蒙特雷", "BBVA体育场"),
    },
    "加拿大": {
        1: ("多伦多", "BMO体育场"),
        2: ("温哥华", "卑诗体育馆"),
        3: ("温哥华", "卑诗体育馆"),
    },
    "美国": {
        1: ("洛杉矶", "索菲体育场"),
        2: ("西雅图", "流明体育场"),
        3: ("旧金山", "李维斯体育场"),
    },
}


def _venue_for_host(team_a: str, team_b: str, matchday: int) -> tuple[str, str] | None:
    for team in (team_a, team_b):
        rounds = _HOST_VENUES.get(team)
        if rounds and matchday in rounds:
            return rounds[matchday]
    return None


def _match_key(stage: str, group_name: str, team_a: str, team_b: str) -> tuple:
    return (stage, group_name or "", team_a, team_b)


def _build_expected_matches():
    """Build the canonical 72 group-stage matches from FIFA schedule data."""
    time_slots = _real_time_slots()
    expected = []
    idx = 0
    for md_i, pairings in enumerate(MATCHDAY_PAIRINGS):
        matchday = md_i + 1
        for group_name, teams in WORLDCUP_GROUPS.items():
            for i, j in pairings:
                team_a, team_b = canonical_team_order(teams[i], teams[j])
                venue = venue_for_match(team_a, team_b)
                if not venue:
                    venue = _venue_for_host(team_a, team_b, matchday) or VENUES[idx % len(VENUES)]
                expected.append({
                    "stage": "小组赛",
                    "group_name": group_name,
                    "team_a": team_a,
                    "team_b": team_b,
                    "match_time": time_slots[idx],
                    "location": venue[0],
                    "stadium": venue[1],
                })
                pair = (team_a, team_b)
                from data.worldcup_schedule_lookup import KICKOFF_OVERRIDES_BEIJING
                if pair in KICKOFF_OVERRIDES_BEIJING:
                    expected[-1]["match_time"] = KICKOFF_OVERRIDES_BEIJING[pair]
                idx += 1
    return expected


def _build_all_expected_matches():
    """Group stage (72) + knockout bracket (32)."""
    return _build_expected_matches() + build_knockout_matches()


async def _repair_misaligned_fixtures(db: AsyncSession, expected: list[dict]) -> list[int]:
    """Fix DB rows where group+teams differ from canonical schedule (by pair, not time slot)."""
    by_pair: dict[tuple[str, str, str], dict] = {}
    for item in expected:
        if item.get("stage") != "小组赛":
            continue
        by_pair[(item["group_name"], item["team_a"], item["team_b"])] = item

    rows = (await db.execute(
        select(Match).where(
            Match.competition_slug == "worldcup-2026",
            Match.stage == "小组赛",
        )
    )).scalars().all()

    repaired_ids: list[int] = []
    for row in rows:
        if not row.group_name:
            continue
        canon = by_pair.get((row.group_name, row.team_a, row.team_b))
        if not canon:
            continue
        changed = False
        if row.location != canon["location"]:
            row.location = canon["location"]
            changed = True
        if row.stadium != canon["stadium"]:
            row.stadium = canon["stadium"]
            changed = True
        if row.status == MATCH_UPCOMING and row.match_time != canon["match_time"]:
            row.match_time = canon["match_time"]
            changed = True
        if changed:
            repaired_ids.append(row.id)
    if repaired_ids:
        await db.flush()
    return repaired_ids


async def _sync_schedule(db: AsyncSession) -> dict:
    """Upsert schedule rows instead of wiping the whole matches table."""
    from data.match_status import repair_canonical_team_order

    await repair_canonical_team_order(db, "worldcup-2026")
    expected = _build_all_expected_matches()
    repaired_ids = await _repair_misaligned_fixtures(db, expected)
    repaired = len(repaired_ids)
    expected_keys = {
        _match_key(m["stage"], m["group_name"], m["team_a"], m["team_b"])
        for m in expected
    }

    existing = (await db.execute(
        select(Match).where(Match.competition_slug == "worldcup-2026")
    )).scalars().all()
    by_key: dict[tuple, list[Match]] = {}
    for m in existing:
        key = _match_key(m.stage, m.group_name, m.team_a, m.team_b)
        by_key.setdefault(key, []).append(m)

    created = updated = removed = 0

    existing_map: dict[tuple, Match] = {}
    for key, items in by_key.items():
        if len(items) == 1:
            existing_map[key] = items[0]
            continue
        items.sort(
            key=lambda m: (
                1 if m.status == MATCH_FINISHED and m.result_a is not None else 0,
                -(m.id or 0),
            ),
            reverse=True,
        )
        existing_map[key] = items[0]
        for dup in items[1:]:
            await db.execute(sqldelete(Prediction).where(Prediction.match_id == dup.id))
            await db.execute(sqldelete(Odds).where(Odds.match_id == dup.id))
            await db.delete(dup)
            removed += 1

    for item in expected:
        key = _match_key(item["stage"], item["group_name"], item["team_a"], item["team_b"])
        current = existing_map.get(key)
        if current:
            current.location = item["location"]
            current.stadium = item["stadium"]
            if current.status == MATCH_UPCOMING:
                current.match_time = item["match_time"]
            updated += 1
            continue

        db.add(Match(
            competition_slug="worldcup-2026",
            stage=item["stage"],
            group_name=item["group_name"],
            team_a=item["team_a"],
            team_b=item["team_b"],
            match_time=item["match_time"],
            location=item["location"],
            stadium=item["stadium"],
            result_a=None,
            result_b=None,
            status=MATCH_UPCOMING,
        ))
        created += 1

    # Remove only obsolete upcoming group matches (preserve finished results & predictions history)
    for key, match in existing_map.items():
        if key in expected_keys:
            continue
        if match.stage != "小组赛" or match.status != MATCH_UPCOMING:
            continue
        await db.execute(sqldelete(Prediction).where(Prediction.match_id == match.id))
        await db.execute(sqldelete(Odds).where(Odds.match_id == match.id))
        await db.delete(match)
        removed += 1

    from db.sqlite_write import flush_session

    await flush_session(db)
    total = created + updated
    return {
        "status": "success",
        "records": total,
        "created": created,
        "updated": updated,
        "removed": removed,
        "repaired": repaired,
    }


async def run_schedule_crawler(db: AsyncSession):
    """Sync group stage match schedule from real FIFA data (upsert, no full wipe)."""
    from service.write_guard import is_heavy_job_running

    if is_heavy_job_running():
        logger.info("Schedule crawler skipped (batch predict / data refresh in progress)")
        return {"status": "skipped", "reason": "heavy_job_running"}

    async with crawler_lock:
        start_time = datetime.now()
        try:
            result = await _sync_schedule(db)
            await _log_crawler(
                db, "schedule", "success", result["records"], start=start_time
            )
            logger.info(
                "Schedule sync: %d created, %d updated, %d removed",
                result["created"], result["updated"], result["removed"],
            )
            return result
        except Exception as e:
            await _safe_crawler_fail(db, "schedule", e, start_time)
            return {"status": "failed", "error": str(e)}
