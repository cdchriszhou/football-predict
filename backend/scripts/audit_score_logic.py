# -*- coding: utf-8 -*-
"""Scan all predicted matches for score-pipeline logic errors (Tunisia-Netherlands class)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
os.chdir(_BACKEND)

from sqlalchemy import select

from db import async_session
from db.models import Match, Prediction, Odds, Team
from service.prediction_service import prepare_fused_odds, team_to_dict
from service.score_pick import (
    run_full_score_pipeline,
    pick_crs_anchored_scores,
    align_score_picks_to_wdl,
    _score_outcome,
    _parse_handicap_line,
    _rank_crs,
)
from service.match_context import build_group_context
from service.prediction_service import infer_matchday
from service.calibration_service import CalibratedRuleEngine
from data.worldcup_group_standings import load_group_standings
from service.score_context import apply_contextual_score_adjustments


def _parse_stored(best_score: str | None) -> list[str]:
    if not best_score:
        return []
    try:
        payload = json.loads(best_score)
    except json.JSONDecodeError:
        return []
    scores = list(payload.get("scores") or [])
    if payload.get("upset"):
        scores.append(payload["upset"])
    return [s for s in scores if s and s != "?"]


def _crs_fav_outcome(crs: dict[str, float]) -> str | None:
    ranked = _rank_crs(crs, set())
    if not ranked:
        return None
    return _score_outcome(ranked[0][0])


def _outcome_label(out: str | None) -> str:
    return {"win": "主胜", "draw": "平", "lose": "客胜"}.get(out or "", "?")


def _flag_issues(
    *,
    team_a: str,
    team_b: str,
    rank_a: int,
    rank_b: int,
    wdl: tuple[float, float, float],
    stored: list[str],
    replay: list[str],
    crs: dict[str, float],
    fused: dict,
    ctx: dict,
    odds_row,
    rule_wdl: tuple[float, float, float] | None,
) -> list[str]:
    issues: list[str] = []
    wr, dr, lr = wdl
    gap = abs(rank_a - rank_b)
    hcp = _parse_handicap_line((odds_row.handicap if odds_row else None) or fused.get("handicap"))
    crs_fav = _crs_fav_outcome(crs)
    wdl_dom = max(("win", wr), ("draw", dr), ("lose", lr), key=lambda x: x[1])[0]
    has_1x2 = bool(odds_row and odds_row.win_win and odds_row.draw and odds_row.win_lose)

    stored_pri = _score_outcome(stored[0]) if stored else None
    replay_pri = _score_outcome(replay[0]) if replay else None

    # 1) 无欧赔但 WDL 把大弱队当热门
    if not has_1x2 and gap >= 25:
        if rank_b + 25 <= rank_a and wr > lr + 5:
            issues.append("无1X2但WDL主胜偏高(客队强很多)")
        if rank_a + 25 <= rank_b and lr > wr + 5:
            issues.append("无1X2但WDL客胜偏高(主队强很多)")

    # 2) CRS 与 WDL 方向冲突
    if crs_fav and crs_fav != wdl_dom and gap >= 20:
        if not (wdl_dom == "draw" and max(wr, lr) - dr < 8):
            issues.append(
                f"CRS首推{_outcome_label(crs_fav)} vs WDL倾向{_outcome_label(wdl_dom)}"
            )

    # 3) 深让球但存盘主胜
    if hcp >= 1.5 and rank_b + 20 <= rank_a and stored_pri == "win":
        issues.append("深让+2类但存盘主推主胜")

    # 4) MD3 已出线 vs 必须抢分 却推弱队主胜
    if ctx.get("matchday") == 3:
        if ctx.get("qualified_b") and ctx.get("must_win_a") and stored_pri == "win":
            issues.append("MD3已出线客队vs必赢主队却存盘主胜")
        if ctx.get("qualified_a") and ctx.get("must_win_b") and stored_pri == "lose":
            issues.append("MD3已出线主队vs必赢客队却存盘客胜")

    # 5) 存盘与修复后回放方向不一致且回放贴近CRS
    if stored_pri and replay_pri and stored_pri != replay_pri:
        if replay_pri == crs_fav or _score_outcome(replay[1] if len(replay) > 1 else "") == crs_fav:
            issues.append(f"存盘{_outcome_label(stored_pri)}→回放{_outcome_label(replay_pri)}(贴近CRS)")

    # 6) align 会把 contextual 改错（突尼斯类）
    if crs and ctx.get("matchday") == 3:
        anchored = pick_crs_anchored_scores(
            crs, win_rate=wr, lose_rate=lr, draw_rate=dr,
            rank_a=rank_a, rank_b=rank_b,
        )
        contextual = apply_contextual_score_adjustments(
            anchored, crs, group_context=ctx, odds_dict=fused,
            win_rate=wr, lose_rate=lr, draw_rate=dr,
            rank_a=rank_a, rank_b=rank_b,
        )
        aligned = align_score_picks_to_wdl(
            contextual, crs, win_rate=wr, draw_rate=dr, lose_rate=lr,
            group_context=ctx,
        )
        ctx_pri = _score_outcome(contextual[0]) if contextual else None
        aln_pri = _score_outcome(aligned[0]) if aligned else None
        if ctx_pri and aln_pri and ctx_pri != aln_pri:
            issues.append(f"align误改: contextual {_outcome_label(ctx_pri)}→{_outcome_label(aln_pri)}")

    # 7) 规则引擎 WDL 极端偏主队
    if rule_wdl:
        rw, rd, rl = rule_wdl
        if rank_b + 30 <= rank_a and rw > rl + 10:
            issues.append(f"规则引擎主胜{rw:.0f}%过高(客强{rank_a}vs{rank_b})")

    return issues


async def main() -> None:
    engine = CalibratedRuleEngine()
    rows: list[dict] = []
    async with async_session() as db:
        matches = (
            await db.execute(
                select(Match)
                .where(Match.competition_slug == "worldcup-2026")
                .order_by(Match.match_time)
            )
        ).scalars().all()

        for m in matches:
            pred = (
                await db.execute(
                    select(Prediction)
                    .where(Prediction.match_id == m.id)
                    .order_by(Prediction.create_time.desc())
                )
            ).scalars().first()
            if not pred:
                continue
            odds = (
                await db.execute(
                    select(Odds).where(Odds.match_id == m.id).order_by(Odds.id.desc())
                )
            ).scalars().first()
            ta = (
                await db.execute(
                    select(Team).where(
                        Team.competition_slug == m.competition_slug, Team.name == m.team_a
                    )
                )
            ).scalar_one_or_none()
            tb = (
                await db.execute(
                    select(Team).where(
                        Team.competition_slug == m.competition_slug, Team.name == m.team_b
                    )
                )
            ).scalar_one_or_none()
            rank_a = ta.rank if ta else 50
            rank_b = tb.rank if tb else 50
            fused = prepare_fused_odds(odds, m.team_a, m.team_b) if odds else {}
            crs = {
                k: v
                for k, v in (fused.get("score_odds") or {}).items()
                if not str(k).startswith("_")
            }
            if not crs:
                continue

            md = await infer_matchday(m, db)
            standings = None
            if m.group_name:
                standings = await load_group_standings(
                    db, m.competition_slug, m.group_name, m.match_time
                )
            ctx = build_group_context(
                m.stage, m.group_name or "", md, m.team_a, m.team_b,
                rank_a, rank_b, location=m.location or "", standings=standings,
            )
            team_a_d = team_to_dict(ta) if ta else {"name": m.team_a, "rank": rank_a}
            team_b_d = team_to_dict(tb) if tb else {"name": m.team_b, "rank": rank_b}
            rule = engine.evaluate(team_a_d, team_b_d, group_context=ctx, odds=fused)
            rule_wdl = (rule.win_rate, rule.draw_rate, rule.lose_rate)

            wdl = (pred.win_rate, pred.draw_rate or 0, pred.lose_rate or 0)
            stored = _parse_stored(pred.best_score)
            best, upset, allp, _ = run_full_score_pipeline(
                crs,
                win_rate=wdl[0], draw_rate=wdl[1], lose_rate=wdl[2],
                sp_win=odds.win_win if odds else None,
                sp_draw=odds.draw if odds else None,
                sp_lose=odds.win_lose if odds else None,
                handicap=odds.handicap if odds else None,
                rank_a=rank_a, rank_b=rank_b,
                odds_dict=fused, stage=m.stage, group_context=ctx,
                team_a=team_a_d, team_b=team_b_d, rule_result=rule,
                skip_wdl_resilience=True,
            )
            replay = best + ([upset] if upset else [])

            issues = _flag_issues(
                team_a=m.team_a, team_b=m.team_b,
                rank_a=rank_a, rank_b=rank_b,
                wdl=wdl, stored=stored, replay=replay,
                crs=crs, fused=fused, ctx=ctx, odds_row=odds,
                rule_wdl=rule_wdl,
            )
            if not issues:
                continue
            rows.append({
                "match": f"{m.team_a} vs {m.team_b}",
                "time": m.match_time.isoformat() if m.match_time else None,
                "matchday": md,
                "ranks": [rank_a, rank_b],
                "handicap": odds.handicap if odds else None,
                "has_1x2": bool(odds and odds.win_win),
                "stored": stored[:3],
                "replay": replay[:3],
                "wdl": [round(x, 1) for x in wdl],
                "rule_wdl": [round(x, 1) for x in rule_wdl],
                "crs_top": _rank_crs(crs, set())[:3],
                "ctx": {k: ctx.get(k) for k in (
                    "must_win_a", "must_win_b", "qualified_a", "qualified_b",
                    "both_need_draw", "both_must_win", "draw_suits_a", "draw_suits_b",
                )},
                "issues": issues,
            })

    out = Path(__file__).resolve().parent / "_score_logic_audit.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Scanned predictions, flagged {len(rows)} matches with logic issues\n")
    for r in rows:
        print("=" * 64)
        print(r["match"], f"MD{r['matchday']}", r["time"])
        print("  ranks", r["ranks"], "hcp", r["handicap"], "1X2", r["has_1x2"])
        print("  stored", r["stored"], "→ replay", r["replay"])
        print("  wdl", r["wdl"], "rule", r["rule_wdl"])
        print("  crs_top", r["crs_top"])
        print("  ctx", r["ctx"])
        for iss in r["issues"]:
            print("  ⚠", iss)
    print(f"\nFull report: {out}")


if __name__ == "__main__":
    asyncio.run(main())
