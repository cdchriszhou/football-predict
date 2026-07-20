from dataclasses import dataclass, field
import math


@dataclass
class RulePrediction:
    win_rate: float
    draw_rate: float
    lose_rate: float
    best_scores: list = field(default_factory=list)  # top 3 most likely scores
    upset_score: str = "?"  # most plausible upset scoreline
    handicap_result: str = "?"
    total_goals: str = "?"
    expected_a: float = 0.0
    expected_b: float = 0.0


class RuleEngine:
    """Statistical rule-based prediction engine for World Cup matches.

    Implements the professional three-layer methodology:
      Layer 1 — Fundamentals (rank, ability, tactics, motivation)
      Layer 2 — Data (expected goals, player quality, style analysis)
      Layer 3 — Odds market (implied probability, handicap, over/under,
                odds-fundamentals consistency check)

    Key insight from professional analysis:
      盘口是否与基本面一致 → the most important signal.
      When odds diverge from fundamentals, the market is sending a message.
    """

    WEIGHTS = {
        "rank": 0.12,
        "ability": 0.18,
        "tactic": 0.10,
        "h2h": 0.10,
        "odds": 0.35,
        "players": 0.15,
    }

    # Average goals per match in recent World Cups (2014/2018/2022)
    AVG_GOALS = 2.7
    # Knockout stage goals tend to be ~15% lower
    KNOCKOUT_GOAL_REDUCTION = 0.85

    # Reference values for normalization (typical World Cup team ~75)
    LEAGUE_AVG_ATK = 75.0
    LEAGUE_AVG_DEF = 75.0
    LEAGUE_AVG_MID = 75.0

    # Threshold for odds-fundamentals divergence (percentage points)
    ODDS_DIVERGENCE_THRESHOLD = 15.0

    # Draw odds threshold — below this, bookmakers are protecting the draw
    LOW_DRAW_ODDS = 3.5

    # Draw base rate for target_draw anchoring (overridable by CalibratedRuleEngine)
    # Note: 2026 WC group stage observed draw rate ~28%, higher than historical ~25%
    DRAW_BASE = 28.0

    # Dixon-Coles low-score correlation (typical football value ~ -0.10 to -0.15)
    DIXON_COLES_RHO = -0.12
    # Per-team expected-goals ceiling (raised from 3.2 — World Cup blowouts like
    # Germany 7:1 or Netherlands 5:1 need headroom above 4.0 xG for the favourite)
    MAX_XG_PER_TEAM = 5.5

    TACTIC_MAP = {
        "高位压迫":   ("pressing", 82),
        "高压快速":   ("pressing", 78),
        "高压逼抢":   ("pressing", 80),
        "技术传控":   ("possession", 85),
        "传控足球":   ("possession", 83),
        "传控":       ("possession", 84),
        "传控Tiki-Taka": ("possession", 88),
        "技术流":     ("possession", 82),
        "中场控制":   ("possession", 80),
        "攻势足球":   ("attacking", 80),
        "防守反击":   ("counter_attack", 78),
        "技术防反":   ("counter_attack", 80),
        "防反":       ("counter_attack", 79),
        "边路突击":   ("counter_attack", 74),
        "快速反击":   ("counter_attack", 76),
        "铁桶防守":   ("defensive", 72),
        "硬朗防守":   ("defensive", 74),
        "区域防守":   ("defensive", 70),
        "长传冲吊":   ("physical", 68),
        "身体对抗":   ("physical", 72),
        "身体流":     ("physical", 70),
        "全攻全守":   ("balanced", 78),
        "控球压迫":   ("possession", 80),
        "反击突击":   ("counter_attack", 73),
    }

    def evaluate(self, team_a: dict, team_b: dict, h2h: list = None,
                 odds: dict = None, players_a: list = None, players_b: list = None,
                 group_context: dict = None) -> RulePrediction:
        def _num(d, key, default=50):
            v = d.get(key, default)
            if v is None:
                return default
            return float(v) if isinstance(v, (int, float, str)) else default

        scores = {"a": 0.0, "b": 0.0, "draw": 0.0}
        active_weight = 0.0

        # ── 1. FIFA rank differential (Elo-like) ──
        rank_a = _num(team_a, "rank", 50)
        rank_b = _num(team_b, "rank", 50)
        if rank_a and rank_b:
            rank_diff = (rank_b - rank_a) * 8
            expected_a = 1.0 / (1.0 + math.pow(10, -rank_diff / 400))
            rank_score = expected_a * 100
            scores["a"] += self.WEIGHTS["rank"] * rank_score
            scores["b"] += self.WEIGHTS["rank"] * (100 - rank_score)
            active_weight += self.WEIGHTS["rank"]

        # ── 2. Team ability composite (all 6 dimensions) ──
        att_a, def_a, mid_a = _num(team_a, "attack"), _num(team_a, "defend"), _num(team_a, "midfield")
        spd_a, phy_a = _num(team_a, "speed"), _num(team_a, "physical")
        att_b, def_b, mid_b = _num(team_b, "attack"), _num(team_b, "defend"), _num(team_b, "midfield")
        spd_b, phy_b = _num(team_b, "speed"), _num(team_b, "physical")

        tac_label_a = team_a.get("tactic", "全攻全守")
        tac_label_b = team_b.get("tactic", "全攻全守")
        style_a, tac_score_a = self.TACTIC_MAP.get(tac_label_a, ("balanced", 70))
        style_b, tac_score_b = self.TACTIC_MAP.get(tac_label_b, ("balanced", 70))

        technical_a = att_a * 0.32 + mid_a * 0.38 + def_a * 0.30
        technical_b = att_b * 0.32 + mid_b * 0.38 + def_b * 0.30
        athletic_a = spd_a * 0.55 + phy_a * 0.45
        athletic_b = spd_b * 0.55 + phy_b * 0.45

        power_a = technical_a * 0.50 + athletic_a * 0.32 + tac_score_a * 0.18
        power_b = technical_b * 0.50 + athletic_b * 0.32 + tac_score_b * 0.18

        if power_a + power_b > 0:
            power_diff = power_a - power_b
            scaled_diff = power_diff / 15.0
            expected_a = 1.0 / (1.0 + math.exp(-scaled_diff))
            ratio = expected_a * 100
            scores["a"] += self.WEIGHTS["ability"] * ratio
            scores["b"] += self.WEIGHTS["ability"] * (100 - ratio)
            active_weight += self.WEIGHTS["ability"]

        # ── 3. Tactical compatibility ──
        if style_a == "balanced" and tac_label_a not in self.TACTIC_MAP:
            style_a = self._team_style(att_a, def_a, mid_a, spd_a, phy_a, tac_score_a)
        if style_b == "balanced" and tac_label_b not in self.TACTIC_MAP:
            style_b = self._team_style(att_b, def_b, mid_b, spd_b, phy_b, tac_score_b)
        compatibility = self._tactic_matchup(style_a, style_b, power_a, power_b)
        if compatibility > 0.5:
            scores["a"] += self.WEIGHTS["tactic"] * compatibility
        elif compatibility < -0.5:
            scores["b"] += self.WEIGHTS["tactic"] * abs(compatibility)
        active_weight += self.WEIGHTS["tactic"]

        # ── 4. Head-to-head history ──
        if h2h and len(h2h) > 0:
            total_weight = 0.0
            a_weighted = 0.0
            b_weighted = 0.0
            d_weighted = 0.0
            for i, h in enumerate(h2h):
                recency = 1.0 / (1.0 + 0.3 * (len(h2h) - 1 - i))
                total_weight += recency
                winner = h.get("winner")
                if winner == team_a.get("name"):
                    a_weighted += recency
                elif winner == team_b.get("name"):
                    b_weighted += recency
                else:
                    d_weighted += recency

            scores["a"] += self.WEIGHTS["h2h"] * (a_weighted / total_weight * 100 + d_weighted / total_weight * 35)
            scores["b"] += self.WEIGHTS["h2h"] * (b_weighted / total_weight * 100 + d_weighted / total_weight * 35)
            scores["draw"] += self.WEIGHTS["h2h"] * (d_weighted / total_weight * 100 * 0.8)
            active_weight += self.WEIGHTS["h2h"]

        # ── 5. Odds implied probability ──
        imp_win = imp_draw = imp_lose = None
        if odds:
            win_w = odds.get("win_win")
            draw_o = odds.get("draw")
            lose = odds.get("win_lose")
            if win_w and draw_o and lose and win_w > 0 and draw_o > 0 and lose > 0:
                overround = 1 / win_w + 1 / draw_o + 1 / lose
                imp_win = (1 / win_w) / overround * 100
                imp_draw = (1 / draw_o) / overround * 100
                imp_lose = (1 / lose) / overround * 100

                # Check odds-fundamentals consistency (Layer 3 core insight)
                fundamentals_win_pct = 0.0
                if active_weight > 0:
                    fundamentals_win_pct = scores["a"] / active_weight * 100
                odds_weight = self._odds_consistency_check(
                    imp_win, fundamentals_win_pct, draw_o
                )

                scores["a"] += odds_weight * imp_win
                scores["b"] += odds_weight * imp_lose
                scores["draw"] += odds_weight * imp_draw
                active_weight += odds_weight

        # ── 6. Key player ability ──
        if players_a and players_b:
            top_a = sorted([p.get("ability", 50) for p in players_a], reverse=True)[:7]
            top_b = sorted([p.get("ability", 50) for p in players_b], reverse=True)[:7]
            weights = [0.30, 0.22, 0.18, 0.13, 0.08, 0.05, 0.04]
            n_a = min(len(top_a), len(weights))
            n_b = min(len(top_b), len(weights))
            avg_a = sum(w * a for w, a in zip(weights[:n_a], top_a[:n_a])) / sum(weights[:n_a])
            avg_b = sum(w * a for w, a in zip(weights[:n_b], top_b[:n_b])) / sum(weights[:n_b])
            if avg_a + avg_b > 0:
                player_ratio = avg_a / (avg_a + avg_b) * 100
                scores["a"] += self.WEIGHTS["players"] * player_ratio
                scores["b"] += self.WEIGHTS["players"] * (100 - player_ratio)
                active_weight += self.WEIGHTS["players"]

        # ── 7. Motivation adjustment ──
        motivation_adj = self._motivation_adjustment(group_context, team_a.get("name"), team_b.get("name"))
        scores["a"] += motivation_adj
        scores["b"] -= motivation_adj

        # ── 7b. 2026 host home advantage ──
        if group_context:
            home_side = group_context.get("home_side")
            home_boost = float(group_context.get("home_win_boost") or 0)
            if home_side == "a" and home_boost:
                scores["a"] += home_boost
            elif home_side == "b" and home_boost:
                scores["b"] += home_boost

        # ── Normalize ──
        if active_weight > 0:
            scale = 1.0 / active_weight
            scores["a"] *= scale
            scores["b"] *= scale
            scores["draw"] *= scale

        # ── Context-aware draw rate ──
        strength_gap = abs(scores["a"] - scores["b"])
        # Milder strength-gap deduction: 2026 WC observed ~28% draw rate
        target_draw = max(12.0, self.DRAW_BASE - strength_gap * 0.18)
        if strength_gap >= 22:
            target_draw = max(12.0, target_draw - 3.0)
        if group_context and group_context.get("home_side") and strength_gap >= 15:
            target_draw = max(10.0, target_draw - 2.0)

        # Group stage must-win games → lower draw
        if group_context and (group_context.get("must_win_a") or group_context.get("must_win_b")):
            target_draw = max(8.0, target_draw - 4.0)

        # Knockout stage → higher draw probability (teams more cautious)
        stage = group_context.get("stage", "") if group_context else ""
        is_knockout = stage not in ("", "小组赛")
        if is_knockout:
            from service.score_pick_config import get_config
            cfg = get_config()
            ko_params = cfg.get("KO_ROUND_PARAMS", {}).get(stage, {})
            draw_boost = float(ko_params.get("draw_boost", 4.0))
            rank_gap = int(group_context.get("rank_gap") or 0)
            if rank_gap >= 30:
                draw_boost *= 0.30
            elif rank_gap >= 20:
                draw_boost *= 0.45
            elif rank_gap >= 12:
                draw_boost *= 0.60
            target_draw = min(32.0, target_draw + draw_boost)

        # 平赔最关键: low draw odds → bookmaker protecting draw → increase draw %
        if imp_draw is not None and draw_o and draw_o < self.LOW_DRAW_ODDS:
            draw_boost = (self.LOW_DRAW_ODDS - float(draw_o)) * 3.0
            target_draw = min(38.0, target_draw + draw_boost)

        scores["draw"] = scores["draw"] * 0.40 + target_draw * 0.60
        scores["draw"] = max(10.0, min(38.0, scores["draw"]))

        # Draw nudge: in close matches, draw should be competitive with win/loss.
        # The Poisson model structurally under-predicts draws because xG separation
        # makes symmetric outcomes (1:1, 0:0) mathematically less likely than they
        # are in reality. This nudge gives draws a fair chance when the match is
        # relatively balanced (max win/loss < 55%).
        max_wl = max(scores["a"], scores["b"])
        if scores["draw"] >= max_wl - 8.0 and max_wl < 55.0:
            scores["draw"] = max(scores["draw"], max_wl)
        # Also: when draw is close to being the top pick, give it a slight edge
        # reflecting the real-world tendency toward draws in tournament football
        elif scores["draw"] >= max_wl - 4.0 and max_wl < 50.0:
            scores["draw"] = max(scores["draw"], max_wl + 1.0)

        remaining = 100.0 - scores["draw"]
        if remaining < 10:
            scores["draw"] = 90.0
            remaining = 10.0

        wl_sum = scores["a"] + scores["b"]
        if wl_sum > 0:
            scores["a"] = remaining * scores["a"] / wl_sum
            scores["b"] = remaining * scores["b"] / wl_sum
        else:
            scores["a"] = remaining / 2
            scores["b"] = remaining / 2

        # ── Score prediction ──
        expected_a, expected_b = self._expected_goals(
            att_a, def_a, mid_a, spd_a, phy_a, tac_score_a,
            att_b, def_b, mid_b, spd_b, phy_b, tac_score_b,
            scores, style_a, style_b, is_knockout, stage
        )

        if group_context:
            home_xg = float(group_context.get("home_xg_boost") or 0)
            home_side = group_context.get("home_side")
            if home_xg and home_side == "a":
                expected_a += home_xg
                expected_b = max(0.15, expected_b - home_xg * 0.4)
            elif home_xg and home_side == "b":
                expected_b += home_xg
                expected_a = max(0.15, expected_a - home_xg * 0.4)

            form_a = float(group_context.get("form_xg_a") or 0)
            form_b = float(group_context.get("form_xg_b") or 0)
            leak_a = float(group_context.get("defense_leak_a") or 0)
            leak_b = float(group_context.get("defense_leak_b") or 0)
            expected_a = max(0.15, expected_a + form_a + leak_b)
            expected_b = max(0.15, expected_b + form_b + leak_a)

            if group_context.get("need_goals_a"):
                expected_a = min(3.5, expected_a + 0.12)
            if group_context.get("need_goals_b"):
                expected_b = min(3.5, expected_b + 0.12)

        handicap = 0.0
        if odds:
            try:
                handicap = float(str(odds.get("handicap") or 0).replace("+", ""))
            except (TypeError, ValueError):
                handicap = 0.0
        ou_raw = odds.get("over_under") if odds else None
        over_under_line = float(ou_raw if ou_raw is not None else 2.5)

        best_scores = self._top3_scores(
            expected_a, expected_b, handicap, scores["draw"], over_under_line,
            is_knockout=is_knockout,
            win_rate=scores["a"],
            lose_rate=scores["b"],
        )

        # ── Handicap prediction ──
        goal_diff = expected_a - expected_b
        handicap_result = self._predict_handicap(goal_diff, handicap)

        # ── Over/Under prediction (knockout conservatism already in xG model) ──
        total_expected = expected_a + expected_b
        total_goals = "大" if total_expected > over_under_line else "小"

        upset_score = self._predict_upset_score(
            expected_a, expected_b,
            round(scores["a"], 1), round(scores["draw"], 1), round(scores["b"], 1),
            best_scores, over_under_line, is_knockout,
        )

        return RulePrediction(
            win_rate=round(scores["a"], 1),
            draw_rate=round(scores["draw"], 1),
            lose_rate=round(scores["b"], 1),
            best_scores=best_scores,
            upset_score=upset_score,
            handicap_result=handicap_result,
            total_goals=total_goals,
            expected_a=expected_a,
            expected_b=expected_b,
        )

    # ═══════════════════════════════════════════════════════════════════
    # Odds-fundamentals consistency check (Layer 3 — 盘口与基本面关系)
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _odds_consistency_check(imp_win: float, fundamentals_win_pct: float,
                                 draw_odds: float) -> float:
        """Check whether the betting market agrees with fundamentals.

        Returns adjusted odds weight for the fusion calculation.

        Key insight from professional analysis:
        - 盘口偏浅 (odds too shallow vs fundamentals) → bookmaker doubts big win → potential trap
        - 逆势升盘 (odds strengthen despite public opinion) → bookmaker real support
        - 平赔下降 (draw odds falling) → bookmaker protecting draw
        """
        base_weight = 0.35  # default WEIGHTS["odds"]

        divergence = abs(imp_win - fundamentals_win_pct)

        if divergence > 25:
            # Large divergence: market strongly disagrees with fundamentals.
            # Reduce odds weight — trust fundamentals more, avoid traps.
            return base_weight * 0.55
        elif divergence > 15:
            # Moderate divergence: moderate skepticism toward market.
            return base_weight * 0.75
        elif divergence < 5:
            # Close alignment: market confirms fundamentals → high confidence.
            return base_weight * 1.05

        return base_weight

    # ═══════════════════════════════════════════════════════════════════
    # Expected goals model
    # ═══════════════════════════════════════════════════════════════════

    def _expected_goals(self, att_a, def_a, mid_a, spd_a, phy_a, tac_a,
                        att_b, def_b, mid_b, spd_b, phy_b, tac_b,
                        scores, style_a, style_b, is_knockout=False,
                        stage: str = "") -> tuple:
        """Poisson-rate model with total-goals normalization.

        Uses attack/defense ratios (not weakness amplification) so mismatches
        stay realistic, then normalizes to historical World Cup averages.
        """
        half_avg = self.AVG_GOALS / 2.0
        # Per-round knockout goal reduction (configurable)
        ko_reduction = self.KNOCKOUT_GOAL_REDUCTION
        if is_knockout and stage:
            from service.score_pick_config import get_config
            cfg = get_config()
            ko_params = cfg.get("KO_ROUND_PARAMS", {}).get(stage, {})
            ko_reduction = float(ko_params.get("goal_reduction", self.KNOCKOUT_GOAL_REDUCTION))
        target_total = self.AVG_GOALS * (
            ko_reduction if is_knockout else 1.0
        )

        # Ratio model: stronger attack vs weaker defense → more goals, but bounded
        ex_a = half_avg * (att_a / self.LEAGUE_AVG_ATK) * (
            self.LEAGUE_AVG_DEF / max(def_b, 45.0)
        )
        ex_b = half_avg * (att_b / self.LEAGUE_AVG_ATK) * (
            self.LEAGUE_AVG_DEF / max(def_a, 45.0)
        )

        def _dim_boost(own: float, opp: float, scale: float = 0.06) -> float:
            edge = min(max(own / max(opp, 1.0) - 1.0, -0.5), 0.5)
            return 1.0 + scale * edge

        ex_a *= _dim_boost(mid_a, mid_b, 0.12)
        ex_b *= _dim_boost(mid_b, mid_a, 0.12)
        ex_a *= _dim_boost(spd_a, spd_b, 0.10)
        ex_b *= _dim_boost(spd_b, spd_a, 0.10)
        ex_a *= _dim_boost(phy_a, phy_b, 0.08)
        ex_b *= _dim_boost(phy_b, phy_a, 0.08)

        tac_mul_a, tac_mul_b = self._tactical_goal_multipliers(style_a, style_b)
        ex_a *= tac_mul_a
        ex_b *= tac_mul_b

        # Soft-blend toward World Cup average (preserves attack/defense mismatch signal)
        total = ex_a + ex_b
        if total > 0 and abs(total - target_total) > 0.05:
            # Blend 50% raw model + 50% normalized to target — allows natural variation
            ex_a_normalized = ex_a / total * target_total
            ex_b_normalized = ex_b / total * target_total
            ex_a = ex_a * 0.50 + ex_a_normalized * 0.50
            ex_b = ex_b * 0.50 + ex_b_normalized * 0.50

        # Shift goals toward the favorite based on win probability
        # Stronger tilt to create realistic xG separation (0.35 vs old 0.12)
        win_edge = (scores["a"] - scores["b"]) / 100.0
        tilt = target_total * 0.35 * win_edge
        ex_a = max(0.3, ex_a + tilt)
        ex_b = max(0.3, ex_b - tilt)

        if is_knockout:
            avg = (ex_a + ex_b) / 2
            ex_a = avg + (ex_a - avg) * 0.82
            ex_b = avg + (ex_b - avg) * 0.82
            # Soft-blend toward knockout target
            total = ex_a + ex_b
            if total > 0 and abs(total - target_total) > 0.05:
                ex_a_normalized = ex_a / total * target_total
                ex_b_normalized = ex_b / total * target_total
                ex_a = ex_a * 0.50 + ex_a_normalized * 0.50
                ex_b = ex_b * 0.50 + ex_b_normalized * 0.50

        ex_a = max(0.2, min(self.MAX_XG_PER_TEAM, ex_a))
        ex_b = max(0.2, min(self.MAX_XG_PER_TEAM, ex_b))
        return ex_a, ex_b

    @staticmethod
    def _tactical_goal_multipliers(style_a: str, style_b: str) -> tuple[float, float]:
        """Symmetric tactical conversion multipliers for both teams."""
        TACTIC_GOAL_MAP = {
            ("counter_attack", "possession"): (1.08, 0.96),
            ("possession", "defensive"): (1.06, 0.97),
            ("counter_attack", "pressing"): (1.04, 1.01),
            ("pressing", "possession"): (1.05, 0.98),
            ("defensive", "attacking"): (0.97, 1.05),
            ("attacking", "defensive"): (1.05, 0.97),
            ("physical", "possession"): (1.03, 0.99),
        }
        pair = TACTIC_GOAL_MAP.get((style_a, style_b))
        if pair:
            return pair
        pair_rev = TACTIC_GOAL_MAP.get((style_b, style_a))
        if pair_rev:
            return pair_rev[1], pair_rev[0]
        return 1.0, 1.0

    # ═══════════════════════════════════════════════════════════════════
    # Team style classification
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _team_style(att, df, mid, spd, phy, tac) -> str:
        if mid >= 70 and tac >= 65:
            return "possession"
        if spd >= 70 and att >= 65:
            return "counter_attack"
        if df >= 70 and phy >= 65:
            return "defensive"
        if spd >= 65 and phy >= 65 and tac >= 60:
            return "pressing"
        if 45 <= mid <= 75 and 45 <= att <= 75 and 45 <= df <= 75:
            return "balanced"
        best = max(
            ("att", att), ("mid", mid), ("def", df),
            ("spd", spd), ("phy", phy), ("tac", tac)
        )
        style_map = {
            "att": "attacking",
            "mid": "possession",
            "def": "defensive",
            "spd": "counter_attack",
            "phy": "physical",
            "tac": "possession"
        }
        return style_map.get(best[0], "balanced")

    @staticmethod
    def _tactic_matchup(style_a: str, style_b: str, power_a: float, power_b: float) -> float:
        COUNTER_MAP = {
            "counter_attack": {"possession": 12, "pressing": 5, "attacking": 8},
            "possession":     {"defensive": 10, "physical": 7, "balanced": 5},
            "pressing":       {"possession": 10, "defensive": 7, "balanced": 6},
            "defensive":      {"attacking": 8, "counter_attack": -5, "physical": 0},
            "attacking":      {"defensive": -5, "balanced": 6, "physical": 5},
            "physical":       {"possession": -3, "counter_attack": -3, "attacking": 0},
        }

        base = COUNTER_MAP.get(style_a, {}).get(style_b, 0)
        power_ratio = power_a / max(1, power_b)
        return base * min(power_ratio, 1.5) / 10.0

    # ═══════════════════════════════════════════════════════════════════
    # Motivation adjustment
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _motivation_adjustment(group_context: dict, name_a: str, name_b: str) -> float:
        if not group_context:
            return 0.0

        adj = 0.0
        must_win_a = group_context.get("must_win_a", False)
        must_win_b = group_context.get("must_win_b", False)
        qualified_a = group_context.get("qualified_a", False)
        qualified_b = group_context.get("qualified_b", False)

        if must_win_a and not must_win_b:
            adj += 3.0
        elif must_win_b and not must_win_a:
            adj -= 3.0

        if qualified_a and not qualified_b:
            adj -= 1.5
        elif qualified_b and not qualified_a:
            adj += 1.5

        return adj

    # ═══════════════════════════════════════════════════════════════════
    # Top-3 score prediction (Poisson-based with handicap constraint)
    # ═══════════════════════════════════════════════════════════════════

    @classmethod
    def _dixon_coles_tau(cls, goals_a: int, goals_b: int,
                         lambda_a: float, lambda_b: float) -> float:
        """Low-score correlation adjustment (Dixon-Coles 1997)."""
        rho = cls.DIXON_COLES_RHO
        if goals_a == 0 and goals_b == 0:
            return 1.0 - lambda_a * lambda_b * rho
        if goals_a == 0 and goals_b == 1:
            return 1.0 + lambda_a * rho
        if goals_a == 1 and goals_b == 0:
            return 1.0 + lambda_b * rho
        if goals_a == 1 and goals_b == 1:
            return 1.0 - rho
        return 1.0

    @classmethod
    def _score_probabilities(
        cls,
        ex_a: float,
        ex_b: float,
        handicap: float = 0.0,
        draw_rate: float = 25.0,
        over_under_line: float = 2.5,
    ) -> list[tuple[str, float]]:
        """All scorelines with Dixon-Coles Poisson probability (descending)."""
        max_goals = 8

        def poisson_pmf(lmbda: float) -> dict:
            if lmbda <= 0:
                return {0: 1.0}
            probs = {}
            for k in range(max_goals + 1):
                probs[k] = (lmbda ** k) * math.exp(-lmbda) / math.factorial(k)
            tail = max(0.0, 1.0 - sum(probs.values()))
            probs[max_goals] += tail
            return probs

        pa = poisson_pmf(ex_a)
        pb = poisson_pmf(ex_b)
        draw_boost = 1.0 + (draw_rate / 100.0) * 0.45

        scores = []
        for ga in range(max_goals + 1):
            for gb in range(max_goals + 1):
                prob = pa.get(ga, 0) * pb.get(gb, 0)
                prob *= cls._dixon_coles_tau(ga, gb, ex_a, ex_b)

                if ga == gb:
                    prob *= draw_boost

                if handicap != 0.0:
                    margin = ga - gb
                    target_margin = handicap if handicap > 0 else -abs(handicap)
                    margin_diff = abs(margin - target_margin)
                    if margin_diff < 0.5:
                        prob *= 1.15
                    elif margin_diff < 1.0:
                        prob *= 1.08

                total = ga + gb
                if total > 7:
                    prob *= 0.65
                elif total > 5:
                    prob *= 0.80

                if abs(margin := ga - gb) >= 5:
                    prob *= 0.65

                if over_under_line <= 2.5 and total >= 4:
                    prob *= 0.7
                elif over_under_line >= 3.0 and total <= 2:
                    prob *= 0.75

                scores.append((f"{ga}:{gb}", prob))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    @staticmethod
    def pick_likely_scores(
        items,
        *,
        max_count: int = 3,
        min_relative: float = 0.38,
    ) -> list[str]:
        """Return 1..max_count scorelines sorted by likelihood; drop weak tails."""
        if not items:
            return []
        if isinstance(items, dict):
            pairs = sorted(items.items(), key=lambda x: x[1], reverse=True)
        elif items and isinstance(items[0], tuple):
            pairs = list(items)
        else:
            clean = [s for s in items if s and s != "?"]
            return clean[:max_count] if clean else []

        pairs = [(s, float(w)) for s, w in pairs if s and s != "?" and w > 0]
        if not pairs:
            return []
        min_w = pairs[0][1] * min_relative
        picked: list[str] = []
        for s, w in pairs:
            if len(picked) >= max_count:
                break
            if not picked or w >= min_w:
                picked.append(s)
            else:
                break
        return picked

    @classmethod
    def _top3_scores(cls, ex_a: float, ex_b: float, handicap: float = 0.0,
                     draw_rate: float = 25.0, over_under_line: float = 2.5,
                     *, is_knockout: bool = False,
                     win_rate: float = 50.0, lose_rate: float = 50.0) -> list:
        """Return 1-3 most likely scorelines via Dixon-Coles Poisson."""
        scores = cls._score_probabilities(
            ex_a, ex_b, handicap, draw_rate, over_under_line
        )
        expected_margin = ex_a - ex_b
        if scores:
            best_margin = int(round(expected_margin))
            best_margin = max(-3, min(3, best_margin))
            preferred = None
            for s, _ in scores:
                ga, gb = map(int, s.split(":"))
                if ga - gb == best_margin:
                    preferred = s
                    break
            if preferred and preferred != scores[0][0]:
                scores = [(preferred, scores[0][1] * 1.02)] + [
                    (s, p) for s, p in scores if s != preferred
                ]
                scores.sort(key=lambda x: x[1], reverse=True)

        margin = ex_a - ex_b
        margin_threshold = 0.35 if is_knockout else 0.85
        if margin >= margin_threshold:
            adjusted: list[tuple[str, float]] = []
            for s, p in scores:
                ga, gb = map(int, s.split(":"))
                if ga > gb and gb == 0:
                    p *= 1.35
                elif ga == gb:
                    p *= 0.55 if is_knockout else 0.72
                elif is_knockout and ga > gb and ga + gb >= 3:
                    p *= 1.12
                adjusted.append((s, p))
            scores = sorted(adjusted, key=lambda x: x[1], reverse=True)
        elif margin <= -margin_threshold:
            adjusted = []
            for s, p in scores:
                ga, gb = map(int, s.split(":"))
                if gb > ga and ga == 0:
                    p *= 1.35
                elif ga == gb:
                    p *= 0.55 if is_knockout else 0.72
                elif is_knockout and gb > ga and ga + gb >= 3:
                    p *= 1.12
                adjusted.append((s, p))
            scores = sorted(adjusted, key=lambda x: x[1], reverse=True)

        # Knockout: if favourite clear but draw still tops, promote a win scoreline
        if is_knockout and scores and win_rate >= lose_rate + 5.0:
            top = scores[0][0]
            ga, gb = map(int, top.split(":"))
            if ga <= gb:
                for s, p in scores:
                    sga, sgb = map(int, s.split(":"))
                    if sga > sgb:
                        scores = [(s, p * 1.08)] + [(x, y) for x, y in scores if x != s]
                        scores.sort(key=lambda x: x[1], reverse=True)
                        break
        elif is_knockout and scores and lose_rate >= win_rate + 5.0:
            top = scores[0][0]
            ga, gb = map(int, top.split(":"))
            if gb <= ga:
                for s, p in scores:
                    sga, sgb = map(int, s.split(":"))
                    if sgb > sga:
                        scores = [(s, p * 1.08)] + [(x, y) for x, y in scores if x != s]
                        scores.sort(key=lambda x: x[1], reverse=True)
                        break

        deduped: list[tuple[str, float]] = []
        seen: set[str] = set()
        for s, p in scores:
            if s not in seen:
                seen.add(s)
                deduped.append((s, p))
        return cls.pick_likely_scores(deduped)

    def _predict_upset_score(
        self,
        ex_a: float,
        ex_b: float,
        win_rate: float,
        draw_rate: float,
        lose_rate: float,
        best_scores: list,
        over_under_line: float = 2.5,
        is_knockout: bool = False,
        context_analysis=None,
    ) -> str:
        """Pick the most plausible upset scoreline (underdog win or surprise draw)."""
        exclude = {s for s in (best_scores or []) if s and s != "?"}
        upset_risk = getattr(context_analysis, "upset_risk", 0.0) or 0.0
        underdog_side = getattr(context_analysis, "underdog_side", "") or ""

        if win_rate >= lose_rate and win_rate >= draw_rate:
            fav_side = "a"
        elif lose_rate >= win_rate and lose_rate >= draw_rate:
            fav_side = "b"
        else:
            fav_side = "draw"

        if not underdog_side and fav_side != "draw":
            underdog_side = "b" if fav_side == "a" else "a"

        def is_upset(ga: int, gb: int) -> bool:
            if fav_side == "a":
                return gb > ga or (ga == gb and draw_rate < 28)
            if fav_side == "b":
                return ga > gb or (ga == gb and draw_rate < 28)
            margin = abs(ga - gb)
            return margin == 1 and (ga + gb) <= 4

        win_candidates = []
        draw_candidates = []
        for score, prob in self._score_probabilities(
            ex_a, ex_b, 0.0, draw_rate, over_under_line
        ):
            if score in exclude:
                continue
            ga, gb = map(int, score.split(":"))
            if not is_upset(ga, gb):
                continue
            weight = prob
            is_draw = ga == gb
            if underdog_side == "a" and ga > gb:
                weight *= 1.0 + upset_risk * 2.5
            elif underdog_side == "b" and gb > ga:
                weight *= 1.0 + upset_risk * 2.5
            elif is_draw and fav_side != "draw":
                weight *= 1.0 + upset_risk * 1.2
            if is_knockout and abs(ga - gb) == 1 and (ga + gb) <= 3:
                weight *= 1.08
            (draw_candidates if is_draw else win_candidates).append((score, weight))

        # 大热门时优先把「平局」纳入冷门候选（卡塔尔 1:1 瑞士）
        if lose_rate >= 55 and fav_side == "b" and "1:1" not in exclude:
            draw_candidates.append(("1:1", draw_rate * 0.08 + 2.0))
        if win_rate >= 58 and fav_side == "a" and "1:1" not in exclude:
            draw_candidates.append(("1:1", draw_rate * 0.08 + 2.0))

        pool = win_candidates if win_candidates else draw_candidates
        if pool:
            pool.sort(key=lambda x: x[1], reverse=True)
            return pool[0][0]

        # Fallback: simple underdog one-goal win
        if fav_side == "a":
            return "0:1" if "0:1" not in exclude else "1:2"
        if fav_side == "b":
            return "1:0" if "1:0" not in exclude else "2:1"
        return "1:0" if "1:0" not in exclude else "0:1"

    @staticmethod
    def _predict_handicap(goal_diff: float, handicap_line: float) -> str:
        adjusted = goal_diff - handicap_line
        if adjusted > 0.5:
            return "胜"
        elif adjusted < -0.5:
            return "负"
        else:
            return "平"
