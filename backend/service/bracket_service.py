from typing import Optional


class BracketService:
    """Generate knockout bracket matchups based on group results"""

    KNOCKOUT_STAGES = ["1/8决赛", "1/4决赛", "半决赛", "季军赛", "决赛"]
    MATCHES_PER_STAGE = {"1/8决赛": 8, "1/4决赛": 4, "半决赛": 2, "季军赛": 1, "决赛": 1}

    # Group winner/runner-up mapping to R16 slots
    GROUP_PAIRINGS = [
        ("A", "B"), ("C", "D"), ("E", "F"), ("G", "H"),
        ("I", "J"), ("K", "L"),
        ("A", "C"), ("B", "D"),
    ]

    @staticmethod
    def generate_r16_matchups(group_standings: dict) -> list[dict]:
        """
        group_standings: {group_name: [{"team": "队名", "points": 9, "gd": 5}, ...]}
        Returns list of {team_a, team_b, description}
        """
        matchups = []
        for i in range(0, len(BracketService.GROUP_PAIRINGS), 2):
            if i + 1 >= len(BracketService.GROUP_PAIRINGS):
                break

        pair_sets = []
        for idx in range(0, 8):
            if idx < 4:
                # Groups A-B, C-D, E-F, G-H: 1st vs 2nd
                pass

        # Standard 48-team format: 12 groups, top 2 + 8 best 3rd place
        # Simplified: winner of group pairings play runners-up
        return BracketService._build_standard_bracket(group_standings)

    @staticmethod
    def _build_standard_bracket(group_standings: dict) -> list[dict]:
        """
        Standard FIFA 48-team bracket construction.
        Group winners play 3rd-place teams or runners-up depending on slot.
        """
        # For simplicity, pair group winners against group runners-up
        groups = sorted(group_standings.keys())
        winners = {}
        runners = {}

        for g in groups:
            standings = group_standings.get(g, [])
            if len(standings) >= 2:
                winners[g] = standings[0]["team"]
                runners[g] = standings[1]["team"]

        matchups = []
        pairings = [
            ("A", "B"), ("C", "D"), ("E", "F"), ("G", "H"),
            ("I", "J"), ("K", "L"),
            ("A", "C"), ("B", "D"),
        ]

        for i, (g1, g2) in enumerate(pairings[:8]):
            if g1 in winners and g2 in runners:
                matchups.append({
                    "match_number": i + 1,
                    "team_a": winners[g1],
                    "team_b": runners[g2],
                    "description": f"{g1}组第一 vs {g2}组第二"
                })

        return matchups

    @staticmethod
    def get_stage_matches(matches: list[dict], stage: str) -> list[dict]:
        return [m for m in matches if m.get("stage") == stage]

    @staticmethod
    def advance_winners(current_stage_matches: list[dict], results: dict) -> list[str]:
        """Return list of winning team names advancing to next stage"""
        winners = []
        for match in current_stage_matches:
            match_id = match.get("id")
            if match_id in results:
                r = results[match_id]
                if r["a"] > r["b"]:
                    winners.append(match["team_a"])
                elif r["b"] > r["a"]:
                    winners.append(match["team_b"])
                else:
                    winners.append(r.get("penalty_winner", match["team_a"]))
        return winners
