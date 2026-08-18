from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PredictionInput:
    match_id: int
    team_a: dict
    team_b: dict
    players_a: list = field(default_factory=list)
    players_b: list = field(default_factory=list)
    odds: dict = field(default_factory=dict)
    h2h: list = field(default_factory=list)
    score_odds: dict = field(default_factory=dict)
    half_full_odds: dict = field(default_factory=dict)
    group_context: dict = field(default_factory=dict)


def _is_league_prompt_stage(stage: str | None) -> bool:
    """Score prompts default to Big Five league unless the stage is a true tournament round."""
    s = (stage or "").strip()
    if s == "小组赛":
        return False
    from service.score_pick import is_knockout_stage
    return not is_knockout_stage(s)


@dataclass
class PredictionOutput:
    win_rate: float
    draw_rate: float
    lose_rate: float
    best_scores: list = field(default_factory=list)  # top 3 most likely scores
    handicap_result: str = ""
    total_goals: str = ""
    reason: str = ""
    model_used: str = ""
    confidence: float = 0.8


class BaseLLMClient(ABC):

    @abstractmethod
    async def predict(self, input: PredictionInput) -> Optional[PredictionOutput]:
        ...

    @abstractmethod
    def model_name(self) -> str:
        ...

    @staticmethod
    def _calc_implied_probs(odds: dict) -> dict:
        """Calculate overround-adjusted implied probabilities from 1X2 odds.

        Bookmakers build a margin (overround) into their odds. This method
        strips the margin to reveal the market's true probability estimate.

        Returns dict with imp_win, imp_draw, imp_lose (percentages 0-100).
        """
        result = {}
        win_w = odds.get("win_win")
        draw_o = odds.get("draw")
        lose = odds.get("win_lose")
        if win_w and draw_o and lose and win_w > 0 and draw_o > 0 and lose > 0:
            overround = 1 / win_w + 1 / draw_o + 1 / lose
            result["imp_win"] = round((1 / win_w) / overround * 100, 1)
            result["imp_draw"] = round((1 / draw_o) / overround * 100, 1)
            result["imp_lose"] = round((1 / lose) / overround * 100, 1)
            result["overround"] = round((overround - 1) * 100, 1)
        return result

    @staticmethod
    def _build_odds_section(input) -> str:
        """Build a comprehensive odds analysis section for the LLM prompt.

        Goes beyond raw numbers — explains what each market signal MEANS
        so the LLM can reason like a professional analyst.
        """
        odds = input.odds
        if not odds:
            return "【博彩市场数据】无（本场比赛暂无盘口数据）\n"

        lines = ["【博彩市场数据 — DraftKings 真实赔率及隐含信号】"]

        # ── 1. 1X2 odds with implied probability ──
        if odds.get("win_win"):
            implied = BaseLLMClient._calc_implied_probs(odds)
            lines.append("")
            lines.append("■ 欧赔（胜平负 1X2）：")
            lines.append(f"  主胜赔率: {odds['win_win']:.2f}  |  平局赔率: {odds['draw']:.2f}  |  客胜赔率: {odds['win_lose']:.2f}")

            if implied:
                lines.append(f"  市场隐含概率（去水分后）: 主胜 {implied['imp_win']}% / 平局 {implied['imp_draw']}% / 客胜 {implied['imp_lose']}%")
                lines.append(f"  博彩公司利润率: {implied['overround']}%")

                # Interpret the signal
                if implied["imp_win"] >= 55:
                    lines.append("  → 信号：市场强烈看好主队取胜，隐含概率超过55%")
                elif implied["imp_win"] >= 45:
                    lines.append("  → 信号：市场偏向主队但优势有限")
                elif implied["imp_lose"] >= 55:
                    lines.append("  → 信号：市场强烈看好客队取胜")
                elif implied["imp_draw"] >= 30:
                    lines.append(f"  → 信号：平局隐含概率{implied['imp_draw']}%，市场认为平局可能性较高")

                # Draw odds signal (key insight)
                if odds["draw"] < 3.5:
                    lines.append(f"  ⚠ 关键信号：平赔仅{odds['draw']:.2f}（低于3.5），博彩公司正在压低平赔防范平局打出，应显著提高平局概率")

        # ── 2. Asian handicap ──
        if odds.get("handicap"):
            lines.append("")
            lines.append("■ 亚盘（让球盘）：")
            lines.append(f"  盘口: {odds['handicap']}")
            lines.append(f"  让球主胜赔: {odds.get('handicap_win', '?')} | 让球平赔: {odds.get('handicap_draw', '?')} | 让球客胜赔: {odds.get('handicap_lose', '?')}")

            # Interpret handicap depth
            try:
                hcap = float(odds["handicap"])
                if abs(hcap) >= 1.5:
                    lines.append(f"  → 信号：深盘（{odds['handicap']}），市场预期实力差距大，强队大概率净胜2球以上")
                elif abs(hcap) >= 0.75:
                    lines.append(f"  → 信号：中深盘（{odds['handicap']}），市场预期强队净胜1-2球")
                elif abs(hcap) >= 0.25:
                    lines.append(f"  → 信号：浅盘（{odds['handicap']}），市场认为双方实力接近")
                else:
                    lines.append("  → 信号：平手盘，市场认为双方势均力敌")
            except ValueError:
                pass

        # ── 3. Over/Under ──
        if odds.get("over_under"):
            lines.append("")
            lines.append("■ 大小球：")
            lines.append(f"  盘口: {odds['over_under']}球")
            lines.append(f"  大球赔: {odds.get('over_odds', '?')} | 小球赔: {odds.get('under_odds', '?')}")

            try:
                ou = float(odds["over_under"])
                if ou >= 3.0:
                    lines.append(f"  → 信号：大小球盘口偏高（{odds['over_under']}），市场预期进球数较多，双方进攻火力足")
                elif ou <= 2.0:
                    lines.append(f"  → 信号：大小球盘口偏低（{odds['over_under']}），市场预期进球数偏少，可能是防守大战")
                else:
                    lines.append(f"  → 信号：大小球盘口标准（{odds['over_under']}），预期进球适中")
            except ValueError:
                pass

        # ── 4. Score odds (top 5 most likely) ──
        if input.score_odds:
            sorted_scores = sorted(input.score_odds.items(), key=lambda x: x[1])[:5]
            score_str = "  ".join(f"{s}={o:.2f}" for s, o in sorted_scores)
            lines.append("")
            lines.append("■ 比分赔率（赔率最低=市场认为最可能打出的比分 Top 5）：")
            lines.append(f"  {score_str}")
            lines.append("  → 信号：最低赔比分是市场认为最可能的结果，应与你的预期进球模型交叉验证")

        # ── 5. Half/Full odds ──
        if input.half_full_odds:
            sorted_hf = sorted(input.half_full_odds.items(), key=lambda x: x[1])[:3]
            hf_str = "  ".join(f"{k}={v:.2f}" for k, v in sorted_hf)
            lines.append("")
            lines.append("■ 半全场赔率（赔率最低 Top 3）：")
            lines.append(f"  {hf_str}")
            lines.append("  → 信号：反映市场对比赛进程的预期（如'胜胜'=主队半场领先且全场获胜）")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _format_match_context_section(input: PredictionInput) -> str:
        """League home advantage / knockout notes for the LLM (beyond WC group tables)."""
        ctx = input.group_context or {}
        stage = (ctx.get("stage") or "").strip()
        a = (input.team_a or {}).get("name", "主队")
        b = (input.team_b or {}).get("name", "客队")
        lines: list[str] = []

        is_league = _is_league_prompt_stage(stage)
        if is_league:
            lines.append(f"【赛事】俱乐部联赛 · {stage or '联赛轮次'}（主客场双循环，非淘汰赛）")
            lines.append("【排名说明】下列“排名”为联赛实力档/积分档参考，不是 FIFA 国家队排名。")
            if ctx.get("home_side") == "a":
                lines.append(
                    f"【主场】{a} 主场作战 vs 客队 {b}。"
                    "联赛主场优势明确：主胜概率通常 +4~+8%，主队预期进球可略上调；"
                    "比分应优先考虑主队不败或小胜（如 1:0/2:0/2:1），除非实力差距极大。"
                )
            elif ctx.get("home_side") == "b":
                lines.append(
                    f"【主场】{b} 主场作战（对阵列表中 {b} 为客队位，请按主客场解读盘口）。"
                )
            else:
                lines.append("【主场】本场主客场信息未标明，勿过度假设主场加成。")
            lines.append(
                "【联赛比分习惯】强弱分明时常见 2:0/3:0/2:1；势均力敌时 1:1/1:0/2:1 更常见；"
                "避免无依据的 4:3 类极端比分。"
            )
        elif stage and stage not in ("小组赛",):
            lines.append(f"【赛事阶段】{stage}")

        if not lines:
            return ""
        return "\n".join(lines) + "\n\n"

    def build_prompt(self, input: PredictionInput) -> str:
        a = input.team_a
        b = input.team_b

        players_a_str = ", ".join(
            f"{p['name']}({p['position']}/能力{p.get('ability','?')}/{p.get('status','?')})"
            for p in input.players_a[:7]
        )
        players_b_str = ", ".join(
            f"{p['name']}({p['position']}/能力{p.get('ability','?')}/{p.get('status','?')})"
            for p in input.players_b[:7]
        )

        # Build comprehensive market analysis section
        odds_section = self._build_odds_section(input)

        group_section = ""
        stage = ((input.group_context or {}).get("stage") or "").strip()
        is_league = _is_league_prompt_stage(stage)

        match_ctx_section = self._format_match_context_section(input)
        role = "五大联赛"
        rank_label = "实力档"
        knockout_section = (
            "8. 【联赛】本场是俱乐部联赛，只预测90分钟常规时间，不考虑加时和点球；"
            "不要套用世界杯淘汰赛的保守小球/拖平逻辑。\n"
        )

        return f"""你是专业{role}足球预测分析师。请综合以下多维数据，结合博彩市场信号与规则模型提示，进行科学严谨的比赛预测，并给出相对合理的常规时间比分。

{match_ctx_section}【对阵】{a['name']} vs {b['name']}

【{a['name']}】{rank_label}{a.get('rank','?')}
  进攻{a.get('attack','?')}(射门/射正能力) | 防守{a.get('defend','?')}(拦截/解围) | 中场{a.get('midfield','?')}(传球组织)
  速度{a.get('speed','?')}(反击效率) | 身体{a.get('physical','?')}(对抗/争顶) | 战术{a.get('tactic','?')}(阵型纪律)
  核心球员: {players_a_str}

【{b['name']}】{rank_label}{b.get('rank','?')}
  进攻{b.get('attack','?')}(射门/射正能力) | 防守{b.get('defend','?')}(拦截/解围) | 中场{b.get('midfield','?')}(传球组织)
  速度{b.get('speed','?')}(反击效率) | 身体{b.get('physical','?')}(对抗/争顶) | 战术{b.get('tactic','?')}(阵型纪律)
  核心球员: {players_b_str}

{group_section}{odds_section}
【历史交锋】{input.h2h if input.h2h else '无'}

预测要求（五维分析法 + 博彩市场信号 + 比分合理性）：
1. 分析维度：排名/实力差距→攻防实力对比→中场控制力→速度/身体对抗→战术风格克制→核心球员状态→主场因素→博彩市场信号验证
2. 博彩市场权重（有盘口时 30-35%）：赔率汇集了全球资金和信息——
   a) 欧赔隐含概率是最直接的胜负预测，应作为基准参考
   b) 平赔<3.5时博彩公司在防范平局，应显著提高平局概率（+5~+12%）
   c) 亚盘深度反映市场对净胜球的预期，深盘(≥1.5)意味着强队大概率大胜
   d) 大小球盘口偏高(≥3.0)→进球大战；偏低(≤2.0)→防守为主低比分
   e) 比分赔率最低的选项是市场共识结果，你的比分预测应与此交叉验证
   f) 若暂无盘口，则更依赖实力差、主场与预期进球，confidence 应略降
3. win_rate+draw_rate+lose_rate 必须精确等于100
4. best_scores 是长度为3的数组，按概率从高到低排列，列出最可能打出的3个比分——
   a) 全部为常规时间（90分钟）比分，不含加时赛及点球大战进球
   b) 参考市场比分赔率（若有）、预期进球模型、亚盘盘口深度与主场因素
   c) 每个比分必须真实可行，单场最大分差不超过5球；强弱分明时主推 2:0/3:0/2:1，接近时主推 1:1/1:0/2:1
   d) 如果市场数据指向小球（大小球≤2），不要预测大比分
   e) 如果市场数据指向大球（大小球≥3），不要只预测小球
   f) 三个比分应覆盖主结果方向，避免三个比分胜平负互相矛盾
5. handicap_result 根据让球盘口和目标分差给出"胜/平/负"（让球后的结果；无盘口时可按净胜球直觉给出）
6. total_goals 参考大小球盘口给出"大/小"（无盘口时按预期总进球≈2.5 判断）
7. confidence 反映预测把握度(0.45-0.85)：深盘一边倒、模型与市场一致时可到 0.75+；胶着战、冷门风险、无盘口时应明显降低
{knockout_section}9. reason 用中文写150字内，按【实力/主场→战术→球员→盘口或模型交叉验证】结构撰写，必须点名 3 个预测比分

严格按JSON格式输出，不要任何多余文字：
{{"win_rate": 数字, "draw_rate": 数字, "lose_rate": 数字, "best_scores": ["X:Y", "X:Y", "X:Y"], "handicap_result": "胜/平/负", "total_goals": "大/小", "reason": "分析理由150字内", "confidence": 0.45-0.85}}
"""
