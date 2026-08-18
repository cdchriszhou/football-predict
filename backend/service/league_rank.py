"""League table rank helpers — 1–20 (or 18) scale, not FIFA 1–200.

Missing / FIFA-leftover ranks must not invent a fake gap of 50.
"""
from __future__ import annotations

# Meaningful gaps on a 18–20 team table
GAP_CLEAR = 8       # e.g. 3 vs 11
GAP_LARGE = 12      # e.g. 2 vs 14
GAP_MISMATCH = 15   # e.g. 1 vs 16
MINNOW_RANK = 16    # relegation zone on a 20-team table
MAX_CLUB_TABLE = 24  # refuse FIFA-scale leftovers (rank 50, 75, …)


def table_rank(rank) -> int | None:
    if rank is None:
        return None
    try:
        r = int(rank)
    except (TypeError, ValueError):
        return None
    if r <= 0 or r > MAX_CLUB_TABLE:
        return None
    return r


def rank_gap(rank_a, rank_b) -> int:
    ra, rb = table_rank(rank_a), table_rank(rank_b)
    if ra is None or rb is None:
        return 0
    return abs(ra - rb)


def is_minnow_rank(rank) -> bool:
    r = table_rank(rank)
    return r is not None and r >= MINNOW_RANK
