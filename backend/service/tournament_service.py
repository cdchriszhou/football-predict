"""Tournament-level prediction: champion, runner-up, semifinalists."""
import json
import asyncio
import math
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Team, Player, Odds, Match
from data.status_constants import MATCH_LIVE, MATCH_UPCOMING, match_status_in_db_values
from db.redis_client import cache_get, cache_set
from llm.deepseek_client import create_llm_client, _call_api, _parse_response
from service.prediction_service import get_configured_models
from crawler.odds_scraper import DK_GROUP_ODDS, american_to_prob
from utils.logger import logger


@dataclass
class TournamentPrediction:
    champion: str
    runner_up: str
    semifinalists: list = field(default_factory=list)
    reason: str = ""
    model_used: str = ""
    confidence: float = 0.7

    def to_dict(self) -> dict:
        return {
            "champion": self.champion,
            "runner_up": self.runner_up,
            "semifinalists": self.semifinalists,
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


def _build_tournament_prompt(teams: list, match_odds_summary: str = "") -> str:
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

    return f"""你是专业世界杯足球预测分析师。请基于全部48支参赛球队的完整数据，结合博彩市场预测，进行科学的冠军/亚军/四强预测。

【博彩市场预测 — 小组头名赔率排名 Top 20】
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
   b) 博彩市场赔率（小组头名赔率和关键比赛盘口，反映市场共识预期，权重应占30-40%）
   c) 核心球员质量与战术风格
   d) 小组出线难度与淘汰赛路径
   e) 历史大赛表现与冠军底蕴
2. 市场赔率是重要参考信号：博彩市场汇集了全球大量信息和资金，赔率隐含的判断往往比纯数据模型更全面
3. champion 和 runner_up 必须是不同球队
4. semifinalists 必须包含 champion 和 runner_up（共4支不同球队）
5. reason 用中文写200字内，必须同时引用数据指标和市场赔率，说明冠军球队的核心优势
6. confidence 反映预测把握度(0.5-0.95)

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


def _fallback_prediction(teams: list) -> TournamentPrediction:
    """Fallback: market-implied strength weighted with FIFA ranking.

    Uses both DraftKings odds and FIFA ranking to produce a consensus fallback.
    Market weight = 0.5, ranking weight = 0.5.
    """
    def composite_score(team):
        rank_score = 1.0 / max((team.rank or 999) / 10, 1)
        market_score = _market_strength(team.name)
        return rank_score * 0.5 + market_score * 0.5

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

        # 2. Load match odds for additional market signal
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

        # 3. Determine models to call
        if model and model != "auto":
            models_to_call = [model]
        else:
            models_to_call = get_configured_models()

        # 4. Call LLMs in parallel
        prompt = _build_tournament_prompt(teams, match_odds_summary)
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

        # 5. Fuse results with market-weighted consensus
        if predictions:
            fused = _fuse_tournament_predictions(predictions)
        else:
            fused = _fallback_prediction(teams)

        result = fused.to_dict()
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
