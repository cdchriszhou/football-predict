"""Tournament-level prediction: champion, runner-up, 3rd/4th, semifinalists."""
import json
import asyncio
import math
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Team, Player, Odds, Match
from data.status_constants import MATCH_LIVE, MATCH_UPCOMING, match_status_in_db_values
from data.knockout_advance import (
    _match_no_for_row,
    display_teams_for_match,
    load_knockout_slot_index_cached,
    match_loser,
    match_winner,
)
from llm.deepseek_client import create_llm_client, _call_api
from service.prediction_service import get_configured_models
from crawler.odds_scraper import DK_GROUP_ODDS, american_to_prob
from utils.logger import logger


@dataclass
class TournamentPrediction:
    champion: str
    runner_up: str
    semifinalists: list = field(default_factory=list)
    third_place: Optional[str] = None
    fourth_place: Optional[str] = None
    reason: str = ""
    model_used: str = ""
    confidence: float = 0.7

    def to_dict(self) -> dict:
        return {
            "champion": self.champion,
            "runner_up": self.runner_up,
            "semifinalists": self.semifinalists,
            "third_place": self.third_place,
            "fourth_place": self.fourth_place,
            "reason": self.reason,
            "model_used": self.model_used,
            "confidence": self.confidence,
        }


GROUPS = {
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


def _is_real_team_name(name: str | None) -> bool:
    if not name or not str(name).strip():
        return False
    s = str(name).strip()
    if s.startswith("第") or s in ("?", "待定", "TBD"):
        return False
    if "胜者" in s or "负者" in s or "待定" in s:
        return False
    return True


def _resolved_winner(m, by_no: dict | None) -> str | None:
    match_no = _match_no_for_row(m, by_no or {}) if by_no else None
    return match_winner(m, match_no=match_no, by_no=by_no)


def _resolved_loser(m, by_no: dict | None) -> str | None:
    match_no = _match_no_for_row(m, by_no or {}) if by_no else None
    return match_loser(m, match_no=match_no, by_no=by_no)


async def resolve_knockout_progress(
    db: AsyncSession,
    competition_slug: str = "worldcup-2026",
) -> dict:
    """Lock known semifinalists / finalists / 3rd-4th from scheduled knockout fixtures."""
    progress = {
        "semifinalists": [],
        "finalists": [],
        "champion": None,
        "runner_up": None,
        "third_place": None,
        "fourth_place": None,
        "notes": [],
    }
    try:
        by_no = await load_knockout_slot_index_cached(db, competition_slug)
    except Exception as e:
        logger.warning(f"Failed to load knockout index for tournament lock: {e}")
        by_no = None

    semis = (await db.execute(
        select(Match).where(
            Match.competition_slug == competition_slug,
            Match.stage == "半决赛",
        ).order_by(Match.match_time.asc())
    )).scalars().all()

    semi_teams: list[str] = []
    for m in semis:
        if by_no is not None:
            ta, tb = display_teams_for_match(m, by_no)
        else:
            ta, tb = m.team_a, m.team_b
        for t in (ta, tb):
            if _is_real_team_name(t) and t not in semi_teams:
                semi_teams.append(t)
    if len(semi_teams) >= 4:
        progress["semifinalists"] = semi_teams[:4]
        progress["notes"].append(f"四强已由半决赛对阵锁定：{'、'.join(semi_teams[:4])}")
    elif len(semi_teams) >= 2:
        progress["semifinalists"] = semi_teams
        progress["notes"].append(f"部分四强已确定：{'、'.join(semi_teams)}")

    finals = (await db.execute(
        select(Match).where(
            Match.competition_slug == competition_slug,
            Match.stage == "决赛",
        ).order_by(Match.match_time.asc())
    )).scalars().all()

    finalists: list[str] = []
    for m in finals:
        if by_no is not None:
            ta, tb = display_teams_for_match(m, by_no)
        else:
            ta, tb = m.team_a, m.team_b
        for t in (ta, tb):
            if _is_real_team_name(t) and t not in finalists:
                finalists.append(t)
        winner = _resolved_winner(m, by_no)
        if winner and _is_real_team_name(winner):
            progress["champion"] = winner
            loser = _resolved_loser(m, by_no)
            if not loser:
                loser = ta if winner == tb else tb if winner == ta else None
            if loser and _is_real_team_name(loser):
                progress["runner_up"] = loser
            progress["notes"].append(f"决赛已结束，冠军锁定：{winner}")
    if len(finalists) >= 2:
        progress["finalists"] = finalists[:2]
        if not progress["champion"]:
            progress["notes"].append(f"决赛对阵已确定：{' vs '.join(finalists[:2])}")
        # Finalists are also semifinalists
        for t in finalists[:2]:
            if t not in progress["semifinalists"]:
                progress["semifinalists"].append(t)

    # If both semis finished, winners are the finalists even if final row not filled
    if len(semis) >= 2 and not progress["finalists"]:
        winners = []
        for m in semis:
            w = _resolved_winner(m, by_no)
            if w and _is_real_team_name(w) and w not in winners:
                winners.append(w)
        if len(winners) >= 2:
            progress["finalists"] = winners[:2]
            progress["notes"].append(f"半决赛已结束，决赛对阵：{' vs '.join(winners[:2])}")

    thirds = (await db.execute(
        select(Match).where(
            Match.competition_slug == competition_slug,
            Match.stage == "季军赛",
        ).order_by(Match.match_time.asc())
    )).scalars().all()
    for m in thirds:
        winner = _resolved_winner(m, by_no)
        loser = _resolved_loser(m, by_no)
        if winner and _is_real_team_name(winner):
            progress["third_place"] = winner
            if loser and _is_real_team_name(loser):
                progress["fourth_place"] = loser
            progress["notes"].append(f"季军赛已结束，季军锁定：{winner}")
            for t in (winner, loser):
                if t and _is_real_team_name(t) and t not in progress["semifinalists"]:
                    progress["semifinalists"].append(t)

    return progress


def _pick_from_candidates(
    preferred: str,
    candidates: list[str],
    exclude: set[str] | None = None,
) -> str:
    exclude = exclude or set()
    pool = [c for c in candidates if c not in exclude]
    if not pool:
        return preferred if preferred not in exclude else (candidates[0] if candidates else preferred)
    if preferred in pool:
        return preferred
    return pool[0]


def _apply_knockout_constraints(
    pred: TournamentPrediction,
    progress: dict,
) -> TournamentPrediction:
    """Override AI fantasy picks with already-decided knockout outcomes."""
    semis = list(progress.get("semifinalists") or [])
    finals = list(progress.get("finalists") or [])
    locked_champ = progress.get("champion")
    locked_runner = progress.get("runner_up")
    locked_third = progress.get("third_place")
    locked_fourth = progress.get("fourth_place")
    notes = list(progress.get("notes") or [])

    if not semis and not finals and not locked_champ and not locked_third:
        return pred

    champion = pred.champion
    runner_up = pred.runner_up
    third_place = pred.third_place or locked_third
    fourth_place = pred.fourth_place or locked_fourth
    semifinalists = list(pred.semifinalists or [])

    if len(semis) >= 4:
        semifinalists = semis[:4]
    elif semis:
        # Keep known teams; fill remaining from AI pick if still eligible
        known = set(semis)
        filled = list(semis)
        for t in pred.semifinalists:
            if t not in known and len(filled) < 4:
                filled.append(t)
                known.add(t)
        semifinalists = filled[:4]

    if locked_champ and locked_runner:
        champion, runner_up = locked_champ, locked_runner
    elif len(finals) >= 2:
        champion = _pick_from_candidates(champion, finals)
        runner_up = _pick_from_candidates(runner_up, finals, exclude={champion})
    elif len(semifinalists) >= 4:
        champion = _pick_from_candidates(champion, semifinalists)
        runner_up = _pick_from_candidates(runner_up, semifinalists, exclude={champion})

    if locked_third:
        third_place = locked_third
    if locked_fourth:
        fourth_place = locked_fourth

    # Order final four as 1–4 when podium is known
    if locked_champ and locked_runner and locked_third and locked_fourth:
        semifinalists = [champion, runner_up, third_place, fourth_place]
    else:
        # Ensure champion/runner_up are inside semifinalists
        if champion not in semifinalists:
            semifinalists = ([champion] + [t for t in semifinalists if t != champion])[:4]
        if runner_up not in semifinalists:
            semifinalists = (
                [champion, runner_up]
                + [t for t in semifinalists if t not in (champion, runner_up)]
            )[:4]
        if third_place and third_place not in semifinalists:
            semifinalists = (semifinalists + [third_place])[:4]
        if fourth_place and fourth_place not in semifinalists:
            semifinalists = (semifinalists + [fourth_place])[:4]

    conf = pred.confidence
    reason = pred.reason or ""
    if notes:
        lock_note = "；".join(notes)
        reason = f"【赛程锁定】{lock_note}。{reason}".strip()
        if locked_champ and locked_third:
            conf = max(conf, 0.98)
        elif locked_champ:
            conf = max(conf, 0.95)
        elif len(finals) >= 2:
            conf = max(conf, 0.88)
        elif len(semis) >= 4:
            conf = max(conf, 0.80)

    return TournamentPrediction(
        champion=champion,
        runner_up=runner_up,
        semifinalists=semifinalists[:4],
        third_place=third_place,
        fourth_place=fourth_place,
        reason=reason,
        model_used=pred.model_used,
        confidence=round(min(0.98, conf), 2),
    )


def _market_strength(team_name: str) -> float:
    """Return market-implied strength (0-1) from DraftKings group winner odds.

    Converts American odds to implied probability, normalized so the strongest
    team in the tournament maps to ~1.0. Teams not in DK_GROUP_ODDS get a
    neutral 0.3 baseline.
    """
    american = DK_GROUP_ODDS.get(team_name)
    if american is None:
        return 0.3
    raw_prob = american_to_prob(american)
    # DK_GROUP_ODDS are group-winner odds, not tournament-winner, so the
    # strongest team (Brazil, -370) has raw_prob ~0.72 after margin.
    # Scale so the strongest team is ~1.0 for readability in the prompt.
    return round(raw_prob / 0.80, 3)


def _market_odds_str(team_name: str) -> str:
    """Return human-readable market odds string for a team."""
    american = DK_GROUP_ODDS.get(team_name)
    if american is None:
        return "无市场数据"
    if american > 0:
        return f"+{int(american)}"
    return str(int(american))


def _build_market_ranking() -> str:
    """Build a market-implied power ranking section for the prompt.

    Ranks all 48 teams by their DraftKings group winner implied probability
    and formats the top 20 as a concise reference table.
    """
    entries = []
    for name, american in DK_GROUP_ODDS.items():
        prob = american_to_prob(american)
        entries.append((name, american, prob))

    entries.sort(key=lambda x: x[2], reverse=True)

    lines = []
    for i, (name, american, prob) in enumerate(entries[:20], 1):
        odds_str = f"+{int(american)}" if american > 0 else str(int(american))
        lines.append(f"  {i:2d}. {name}  赔率:{odds_str}  隐含概率:{prob:.1%}")

    return "\n".join(lines)


def _team_summary(team) -> str:
    """Build a one-line summary of a team for the prompt."""
    players = getattr(team, '_players', [])
    top_players = ", ".join(
        f"{p.name}({p.position}/{p.ability})"
        for p in sorted(players, key=lambda x: x.ability or 0, reverse=True)[:3]
    ) if players else "无球员数据"

    market_str = _market_odds_str(team.name)
    mkt_strength = _market_strength(team.name)

    return (
        f"{team.name} | FIFA#{team.rank} | "
        f"攻{team.attack} 防{team.defend} 中{team.midfield} "
        f"速{team.speed} 体{team.physical} | "
        f"战术:{team.tactic or '未知'} | 身价:{team.price or '未知'} | "
        f"小组{team.group_name} | "
        f"市场赔率:{market_str} | "
        f"核心:{top_players}"
    )


def _build_tournament_prompt(
    teams: list,
    match_odds_summary: str = "",
    knockout_progress: dict | None = None,
) -> str:
    """Build the comprehensive tournament prediction prompt including market data."""
    team_lines = "\n".join(_team_summary(t) for t in teams)

    group_lines = "\n".join(
        f"{g}组: {', '.join(GROUPS[g])}" for g in sorted(GROUPS.keys())
    )

    market_ranking = _build_market_ranking()

    odds_section = ""
    if match_odds_summary:
        odds_section = f"""
【博彩市场数据 — 小组赛盘口赔率】
以下为各小组关键比赛的博彩赔率（DraftKings真实数据），赔率越低表示市场越看好该队取胜：
{match_odds_summary}
"""

    progress = knockout_progress or {}
    lock_section = ""
    if progress.get("notes") or progress.get("semifinalists") or progress.get("finalists"):
        semis = progress.get("semifinalists") or []
        finals = progress.get("finalists") or []
        lines = ["【淘汰赛已确定赛果 — 必须严格遵守，不得改写】"]
        if len(semis) >= 4:
            lines.append(f"- 四强已锁定（只能这4支）：{', '.join(semis[:4])}")
        elif semis:
            lines.append(f"- 已确定进入四强：{', '.join(semis)}")
        if len(finals) >= 2:
            lines.append(f"- 决赛对阵已确定，冠军/亚军只能从这两队中选：{' vs '.join(finals[:2])}")
        if progress.get("champion"):
            lines.append(f"- 冠军已产生：{progress['champion']}")
        if progress.get("runner_up"):
            lines.append(f"- 亚军已产生：{progress['runner_up']}")
        if progress.get("third_place"):
            lines.append(f"- 季军已产生：{progress['third_place']}")
        if progress.get("fourth_place"):
            lines.append(f"- 第四名已产生：{progress['fourth_place']}")
        for note in progress.get("notes") or []:
            lines.append(f"- {note}")
        lines.append("若与上方锁定冲突，以锁定赛果为准。已淘汰球队（如未进四强的巴西等）禁止出现在 semifinalists。")
        lock_section = "\n".join(lines) + "\n"

    return f"""你是专业世界杯足球预测分析师。请基于全部48支参赛球队的完整数据，结合博彩市场预测，进行科学的冠军/亚军/四强预测。

{lock_section}【博彩市场预测 — 小组头名赔率排名 Top 20】
赔率越低=市场越看好。隐含概率由美式赔率换算，反映了全球博彩市场的共识预期：
{market_ranking}
{odds_section}
【全部球队数据】（共{len(teams)}队，含市场赔率）
{team_lines}

【小组分组】
{group_lines}

【淘汰赛对阵规则】
- 1/8决赛: A1vsB2, C1vsD2, E1vsF2, G1vsH2, I1vsJ2, K1vsL2, A2vsC1, B2vsD1
- 1/4决赛: A1/B2胜者 vs C1/D2胜者, E1/F2胜者 vs G1/H2胜者, I1/J2胜者 vs K1/L2胜者, A2/C1胜者 vs B2/D1胜者
- 半决赛: 上半区两组胜者对决, 下半区两组胜者对决
- 决赛: 半决赛胜者对决

预测要求：
1. 综合五维分析：
   a) FIFA排名与攻防能力（球队数据中的量化指标）
   b) 博彩市场赔率（小组头名赔率和单场比赛盘口，反映市场共识预期，权重应占30-40%）
   c) 核心球员质量与战术风格
   d) 小组出线难度与淘汰赛路径
   e) 历史大赛表现与冠军底蕴
2. 市场赔率是重要参考信号：博彩市场汇集了全球大量信息和资金，赔率隐含的判断往往比纯数据模型更全面
3. champion 和 runner_up 必须是不同球队
4. semifinalists 必须包含 champion 和 runner_up（共4支不同球队）；若上方已锁定四强，必须原样使用锁定名单
5. 若决赛对阵已确定，champion/runner_up 只能从决赛两队中选择
6. reason 用中文写200字内，必须同时引用数据指标和市场赔率，说明冠军球队的核心优势；若有赛程锁定，先说明已确定事实再分析
7. confidence 反映预测把握度(0.5-0.95)；四强已定时 confidence 应不低于0.8

严格按JSON格式输出，不要任何多余文字：
{{"champion": "冠军队名", "runner_up": "亚军队名", "semifinalists": ["四强1", "四强2", "四强3", "四强4"], "reason": "分析理由200字内", "confidence": 0.5-0.95}}"""


def _parse_tournament_response(data: dict, model_name: str) -> Optional[TournamentPrediction]:
    """Parse LLM response into TournamentPrediction."""
    try:
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        result = json.loads(content)

        champion = result.get("champion", "")
        runner_up = result.get("runner_up", "")
        semifinalists = result.get("semifinalists", [])

        if not champion or not runner_up:
            return None

        if champion not in semifinalists:
            semifinalists.insert(0, champion)
        if runner_up not in semifinalists:
            semifinalists.insert(1, runner_up)
        semifinalists = semifinalists[:4]

        return TournamentPrediction(
            champion=champion,
            runner_up=runner_up,
            semifinalists=semifinalists,
            reason=result.get("reason", ""),
            model_used=model_name,
            confidence=float(result.get("confidence", 0.7)),
        )
    except (json.JSONDecodeError, KeyError, ValueError, IndexError) as e:
        logger.error(f"Failed to parse tournament prediction from {model_name}: {e}")
        return None


def _fallback_prediction(
    teams: list,
    knockout_progress: dict | None = None,
) -> TournamentPrediction:
    """Fallback: market-implied strength weighted with FIFA ranking.

    Uses both DraftKings odds and FIFA ranking to produce a consensus fallback.
    Market weight = 0.5, ranking weight = 0.5. Respects known knockout locks.
    """
    progress = knockout_progress or {}
    locked_semis = list(progress.get("semifinalists") or [])
    locked_finals = list(progress.get("finalists") or [])

    def composite_score(team):
        rank_score = 1.0 / max((team.rank or 999) / 10, 1)
        market_score = _market_strength(team.name)
        return rank_score * 0.5 + market_score * 0.5

    if len(locked_finals) >= 2:
        name_to_team = {t.name: t for t in teams}
        ranked = sorted(
            [name_to_team[n] for n in locked_finals if n in name_to_team],
            key=composite_score,
            reverse=True,
        )
        names = [t.name for t in ranked] or locked_finals[:2]
        champ, runner = names[0], names[1] if len(names) > 1 else names[0]
        semis = locked_semis[:4] if len(locked_semis) >= 4 else (locked_semis + [n for n in names if n not in locked_semis])[:4]
        return TournamentPrediction(
            champion=champ,
            runner_up=runner,
            semifinalists=semis or names[:4],
            reason="基于已确定决赛对阵与球队实力自动生成（AI模型暂不可用）",
            model_used="rule_engine",
            confidence=0.85,
        )

    if len(locked_semis) >= 4:
        name_to_team = {t.name: t for t in teams}
        ranked = sorted(
            [name_to_team[n] for n in locked_semis[:4] if n in name_to_team],
            key=composite_score,
            reverse=True,
        )
        top4 = [t.name for t in ranked] or locked_semis[:4]
        return TournamentPrediction(
            champion=top4[0],
            runner_up=top4[1] if len(top4) > 1 else top4[0],
            semifinalists=locked_semis[:4],
            reason="基于已锁定四强与球队实力自动生成（AI模型暂不可用）",
            model_used="rule_engine",
            confidence=0.8,
        )

    sorted_teams = sorted(teams, key=composite_score, reverse=True)
    top4 = [t.name for t in sorted_teams[:4]]
    return TournamentPrediction(
        champion=top4[0] if len(top4) > 0 else "?",
        runner_up=top4[1] if len(top4) > 1 else "?",
        semifinalists=top4[:4],
        reason="基于FIFA排名与博彩市场赔率综合自动生成（AI模型暂不可用）",
        model_used="rule_engine",
        confidence=0.45,
    )


class TournamentPredictionService:

    async def predict_tournament(self, db: AsyncSession, model: str = None) -> dict:
        """Predict champion, runner-up, and semifinalists.

        Incorporates: FIFA ranking, team attributes, player quality,
        DraftKings group winner odds, and match-level betting market data.
        """
        # 1. Load all teams with top 5 players
        teams = (await db.execute(
            select(Team).order_by(Team.rank)
        )).scalars().all()

        if not teams:
            return {
                "champion": "?", "runner_up": "?",
                "semifinalists": [], "reason": "暂无球队数据",
                "model_used": "none", "confidence": 0
            }

        for team in teams:
            players = (await db.execute(
                select(Player).where(Player.team_id == team.id).order_by(Player.ability.desc()).limit(5)
            )).scalars().all()
            team._players = players

        # 2. Lock known knockout outcomes from schedule (semis / final)
        knockout_progress = await resolve_knockout_progress(db)

        # 3. Load match odds for additional market signal
        match_odds_summary = ""
        try:
            matches = (await db.execute(
                select(Match).where(Match.status.in_(match_status_in_db_values(MATCH_UPCOMING, MATCH_LIVE))).order_by(Match.match_time.asc())
            )).scalars().all()

            odds_lines = []
            for match in matches[:36]:  # top 36 key matches
                odds = (await db.execute(
                    select(Odds).where(Odds.match_id == match.id).order_by(Odds.update_time.desc())
                )).scalar_one_or_none()
                if odds:
                    odds_lines.append(
                        f"  {match.team_a} vs {match.team_b} | "
                        f"主胜:{odds.win_win:.2f} 平:{odds.draw:.2f} 客胜:{odds.win_lose:.2f} | "
                        f"盘口:{odds.handicap or '-'}"
                    )
            if odds_lines:
                match_odds_summary = "\n".join(odds_lines)
        except Exception as e:
            logger.warning(f"Failed to load match odds for tournament prompt: {e}")

        # 4. Determine models to call
        if model and model != "auto":
            models_to_call = [model]
        else:
            models_to_call = get_configured_models()

        # 5. Call LLMs in parallel
        prompt = _build_tournament_prompt(teams, match_odds_summary, knockout_progress)
        predictions: list[TournamentPrediction] = []

        if models_to_call:
            async def call_one(m: str):
                client = create_llm_client(m)
                try:
                    data = await _call_api(
                        client.api_key, client.base_url, client.model_name(),
                        prompt, temperature=0.1, max_tokens=600,
                    )
                    if data:
                        return _parse_tournament_response(data, client.model_name())
                except Exception as e:
                    logger.error(f"Tournament prediction error for {m}: {e}")
                return None

            results = await asyncio.gather(*[call_one(m) for m in models_to_call], return_exceptions=True)
            predictions = [r for r in results if r is not None and not isinstance(r, Exception)]

        # 6. Fuse results, then hard-lock already decided knockout outcomes
        if predictions:
            fused = _fuse_tournament_predictions(predictions)
        else:
            fused = _fallback_prediction(teams, knockout_progress)

        fused = _apply_knockout_constraints(fused, knockout_progress)
        result = fused.to_dict()
        if knockout_progress.get("notes"):
            result["knockout_locked"] = True
            result["knockout_notes"] = knockout_progress["notes"]
        return result


def _fuse_tournament_predictions(predictions: list[TournamentPrediction]) -> TournamentPrediction:
    """Fuse multiple model predictions into one market-aware consensus.

    Model confidence is blended with market-implied probability to produce
    a final weighted vote. This ensures the consensus reflects both AI
    analysis and betting market sentiment.
    """
    if len(predictions) == 1:
        return predictions[0]

    def market_weight(team_name: str) -> float:
        """Market-derived bonus weight (0.8-1.2x multiplier)."""
        mkt = _market_strength(team_name)
        return 0.8 + mkt * 0.5  # ranges from ~0.95 to 1.3

    def weighted_vote(attr: str) -> str:
        votes = {}
        for p in predictions:
            v = getattr(p, attr, "?")
            mw = market_weight(v)
            votes[v] = votes.get(v, 0) + p.confidence * mw
        return max(votes, key=votes.get)

    champion = weighted_vote("champion")
    runner_up = weighted_vote("runner_up")

    if champion == runner_up:
        champ_votes = {}
        for p in predictions:
            mw = market_weight(p.champion)
            champ_votes[p.champion] = champ_votes.get(p.champion, 0) + p.confidence * mw
        sorted_champs = sorted(champ_votes, key=champ_votes.get, reverse=True)
        champion = sorted_champs[0]
        runner_up = sorted_champs[1] if len(sorted_champs) > 1 else runner_up

    semi_scores = {}
    for p in predictions:
        for team in p.semifinalists:
            mw = market_weight(team)
            semi_scores[team] = semi_scores.get(team, 0) + p.confidence * mw

    semi_scores[champion] = semi_scores.get(champion, 0) + 2.5
    semi_scores[runner_up] = semi_scores.get(runner_up, 0) + 2.5

    semifinalists = sorted(semi_scores, key=semi_scores.get, reverse=True)[:4]

    reasons = []
    seen = set()
    for p in predictions:
        if p.reason and p.reason not in seen:
            seen.add(p.reason)
            prefix = p.model_used.split("-")[0] if p.model_used else "Model"
            reasons.append(f"[{prefix}] {p.reason}")

    def short_name(full: str) -> str:
        if "deepseek" in full: return "DeepSeek"
        if "qwen" in full: return "Qwen"
        if "glm" in full or "GLM" in full: return "GLM"
        return full

    model_used = "+".join(short_name(p.model_used) for p in predictions)
    avg_confidence = round(sum(p.confidence for p in predictions) / len(predictions), 2)

    return TournamentPrediction(
        champion=champion,
        runner_up=runner_up,
        semifinalists=semifinalists,
        reason=" | ".join(reasons),
        model_used=model_used,
        confidence=avg_confidence,
    )
