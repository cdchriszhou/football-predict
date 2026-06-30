"""
ContextAdjustmentScorer — TERTIARY scorer (default weight 0.15).

Handles situational factors: group standings, matchday-3 motivation,
knockout path pressure, market+handicap alignment.
"""
from __future__ import annotations

from typing import Optional

from .base import BaseScorer, ScorerInput, ScorerResult


class ContextAdjustmentScorer(BaseScorer):
    """TERTIARY scorer for group-stage situational factors."""

    label = "context"

    def score(self, inp: ScorerInput) -> ScorerResult:
        ctx = inp.group_context or {}
        md = int(ctx.get("matchday") or 0)
        if md < 2 or ctx.get("stage") != "小组赛":
            return ScorerResult(scores={}, confidence=1.0, rationale="no context needed", source=self.label)

        from service.score_context import market_score_profile, detect_resilience_signals
        market = market_score_profile(inp.odds_dict)

        adjustments: dict[str, float] = {}

        # ── Market + handicap alignment ──
        adjustments = self._apply_market_alignment(adjustments, inp, market)
        # ── Group standings motivation ──
        adjustments = self._apply_standings_motivation(adjustments, inp, ctx)
        # ── MD3 must-win / collusion ──
        adjustments = self._apply_md3_rules(adjustments, inp, ctx, market)
        # ── Knockout path pressure ──
        adjustments = self._apply_knockout_pressure(adjustments, inp, ctx)
        # ── Hot attacking form ──
        adjustments = self._apply_attacking_form(adjustments, inp, ctx)

        return ScorerResult(
            scores=adjustments,
            confidence=0.7,
            rationale=self._build_rationale(ctx),
            source=self.label,
        )

    # ── Market Alignment ─────────────────────────────────────────────────

    def _apply_market_alignment(
        self, adj: dict[str, float], inp: ScorerInput, market: dict,
    ) -> dict[str, float]:
        result = dict(adj)
        hcp = market.get("handicap", 0.0)

        if market.get("deep_fav") and market.get("fav_a") and market.get("cover_a"):
            for s in ("3:0", "2:0", "3:1", "2:1"):
                if s in inp.score_odds and hcp <= -1.0:
                    result[s] = result.get(s, 0) + 0.12
        elif market.get("deep_fav") and not market.get("fav_a") and market.get("cover_b"):
            for s in ("0:3", "0:2", "1:3", "1:2"):
                if s in inp.score_odds and hcp >= 1.0:
                    result[s] = result.get(s, 0) + 0.12

        if market.get("drawish") and inp.draw_rate >= 28 and market.get("low_total"):
            ctx = inp.group_context or {}
            if not (ctx.get("must_win_a") or ctx.get("must_win_b") or ctx.get("both_must_win")):
                for s in ("1:1", "0:0"):
                    if s in inp.score_odds:
                        result[s] = result.get(s, 0) + 0.15

        if market.get("high_total") and (inp.expected_a + inp.expected_b) >= 2.6:
            for s in ("2:1", "1:2", "2:2", "3:1", "1:3"):
                if s in inp.score_odds:
                    result[s] = result.get(s, 0) + 0.08

        if not market.get("deep_fav") and market.get("fav_clear"):
            if market.get("fav_a") and hcp <= -0.5:
                result["1:0"] = result.get("1:0", 0) + 0.10
            elif not market.get("fav_a") and hcp >= 0.5:
                for s in ("0:1", "1:2"):
                    if s in inp.score_odds:
                        result[s] = result.get(s, 0) + 0.10
                        break

        return result

    # ── Standings Motivation ─────────────────────────────────────────────

    def _apply_standings_motivation(
        self, adj: dict[str, float], inp: ScorerInput, ctx: dict,
    ) -> dict[str, float]:
        result = dict(adj)
        md = int(ctx.get("matchday") or 0)

        # Collusion draw (both accept draw)
        if ctx.get("both_need_draw") and inp.draw_rate >= 22 and not (
            ctx.get("must_win_a") or ctx.get("must_win_b") or ctx.get("both_must_win")
        ):
            for s in ("1:1", "0:0"):
                if s in inp.score_odds:
                    result[s] = result.get(s, 0) + 0.20

        for side, is_a in (("a", True), ("b", False)):
            qualified = ctx.get(f"qualified_{side}")
            must_win = ctx.get(f"must_win_{side}")
            need_goals = ctx.get(f"need_goals_{side}")

            if qualified and md == 3 and not must_win:
                for s in ("1:0", "0:1", "0:0", "1:1"):
                    if s in inp.score_odds:
                        result[s] = result.get(s, 0) + 0.08

            if must_win and need_goals:
                if is_a and inp.win_rate >= inp.lose_rate:
                    for s in ("2:1", "3:1", "3:0"):
                        if s in inp.score_odds:
                            result[s] = result.get(s, 0) + 0.15
                            break
                elif not is_a and inp.lose_rate >= inp.win_rate:
                    for s in ("1:2", "1:3", "0:3"):
                        if s in inp.score_odds:
                            result[s] = result.get(s, 0) + 0.15
                            break

        return result

    # ── MD3 Rules ────────────────────────────────────────────────────────

    def _apply_md3_rules(
        self, adj: dict[str, float], inp: ScorerInput, ctx: dict, market: dict,
    ) -> dict[str, float]:
        result = dict(adj)
        if ctx.get("matchday") != 3 or ctx.get("stage") != "小组赛":
            return result

        # Both must win → open, multi-goal
        if ctx.get("both_must_win"):
            for s in ("3:1", "2:1", "3:2", "3:0", "2:0"):
                if s in inp.score_odds:
                    result[s] = result.get(s, 0) + 0.25
                    break

        # Leader accepts draw, trailer must win (Switzerland 2:1 Canada)
        if ctx.get("must_win_a") and ctx.get("draw_suits_b"):
            for s in ("2:1", "3:1", "2:0", "1:0"):
                if s in inp.score_odds and self._score_outcome(s) == "win":
                    result[s] = result.get(s, 0) + 0.22
                    break

        if ctx.get("must_win_b") and ctx.get("draw_suits_a"):
            for s in ("1:2", "0:2", "0:1"):
                if s in inp.score_odds and self._score_outcome(s) == "lose":
                    result[s] = result.get(s, 0) + 0.22
                    break

        # Qualified favourite vs desperate opponent
        if ctx.get("qualified_b") and ctx.get("must_win_a") and inp.lose_rate >= 35:
            for s in ("0:3", "1:3", "0:2", "1:2"):
                if s in inp.score_odds and self._score_outcome(s) == "lose":
                    result[s] = result.get(s, 0) + 0.35
                    break

        if ctx.get("qualified_a") and ctx.get("must_win_b") and inp.win_rate >= 38:
            for s in ("3:0", "3:1", "2:0", "2:1"):
                if s in inp.score_odds and self._score_outcome(s) == "win":
                    result[s] = result.get(s, 0) + 0.30
                    break

        return result

    # ── Knockout Pressure ────────────────────────────────────────────────

    def _apply_knockout_pressure(
        self, adj: dict[str, float], inp: ScorerInput, ctx: dict,
    ) -> dict[str, float]:
        result = dict(adj)
        md = int(ctx.get("matchday") or 0)
        if md != 3:
            return result

        for side, is_a in (("a", True), ("b", False)):
            pressure = float(ctx.get(f"path_pressure_{side}") or 0)
            band = ctx.get(f"finish_band_{side}", "")
            if pressure >= 0.45:
                if is_a and inp.win_rate >= inp.lose_rate:
                    for s in ("2:1", "2:0", "1:0"):
                        if s in inp.score_odds:
                            result[s] = result.get(s, 0) + 0.12
                            break
                elif not is_a and inp.lose_rate >= inp.win_rate:
                    for s in ("1:2", "0:2", "0:1"):
                        if s in inp.score_odds:
                            result[s] = result.get(s, 0) + 0.12
                            break

        return result

    # ── Attacking Form ───────────────────────────────────────────────────

    def _apply_attacking_form(
        self, adj: dict[str, float], inp: ScorerInput, ctx: dict,
    ) -> dict[str, float]:
        result = dict(adj)
        sa = ctx.get("standing_a") or {}
        sb = ctx.get("standing_b") or {}
        avg_gf = float(ctx.get("group_avg_gf") or 1.35)
        if sa.get("played") and sb.get("played"):
            hot_a = sa["goals_for"] / sa["played"] >= avg_gf + 0.35
            hot_b = sb["goals_for"] / sb["played"] >= avg_gf + 0.35
            if hot_a and hot_b:
                for s in ("2:1", "1:2", "2:2"):
                    if s in inp.score_odds:
                        result[s] = result.get(s, 0) + 0.12

        return result

    # ── Helpers ─────────────────────────────────────────────────────────

    def _build_rationale(self, ctx: dict) -> str:
        parts = []
        md = ctx.get("matchday", 0)
        if ctx.get("both_must_win"):
            parts.append("双方必须取胜")
        elif ctx.get("both_need_draw"):
            parts.append("双方可接受平局")
        if ctx.get("must_win_a"):
            parts.append("A队必须取胜")
        if ctx.get("must_win_b"):
            parts.append("B队必须取胜")
        return f"MD{md}: " + ", ".join(parts) if parts else f"MD{md}"
