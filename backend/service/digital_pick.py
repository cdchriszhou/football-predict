"""数字彩选号多样性：按最新期号 + 换一批序号做稳定伪随机扰动。

纯频率 Top1 在大样本窗口下几乎不变，用户会看到「几天同一组号」。
期号变化或手动 rotate 后，在各位/各球 Top-K 候选内轮换，保证：
- 同期内同一 rotate 结果稳定（可复现）
- 新开奖期号后推荐会变化
- 「换一批」可立即换号
"""

from __future__ import annotations


def period_seed(issue: str | None, rotate: int = 0) -> int:
    text = f"{issue or '0'}:{int(rotate or 0)}"
    h = 2166136261
    for ch in text:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return int(h)


def rotate_ranked(ranked: list, seed: int, *, top_k: int = 4, salt: int = 0) -> list:
    """在排名列表的前 top_k 内按 seed 轮换，其余保持相对顺序。"""
    if not ranked:
        return []
    out = list(ranked)
    k = min(max(1, top_k), len(out))
    if k <= 1:
        return out
    head = out[:k]
    rest = out[k:]
    off = (seed + salt) % k
    return head[off:] + head[:off] + rest


def pick_from_pool(pool: list, seed: int, salt: int = 0):
    if not pool:
        return None
    return pool[(seed + salt) % len(pool)]
