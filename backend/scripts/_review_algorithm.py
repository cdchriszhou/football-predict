"""One-off algorithm review from backtest rows."""
import asyncio
from collections import Counter, defaultdict

from db import async_session
from service.score_backtest import compute_score_backtest


async def main():
    async with async_session() as db:
        bt = await compute_score_backtest(db)
        n = bt["matches_evaluated"]
        print("=== OVERALL ===")
        print(
            f"evaluated={n} primary={bt['primary_hit_rate']}% "
            f"triple={bt['triple_hit_rate']}%"
        )

        rows = [m for g in bt["groups"] for m in g["matches"]]

        by_source = Counter(r.get("pick_source", "?") for r in rows)
        print("by pick_source:", dict(by_source))

        misses = [r for r in rows if not r["primary_hit"]]
        print(f"misses={len(misses)} hits={n - len(misses)}")

        print("top actual on primary miss:", Counter(r["actual_score"] for r in misses).most_common(8))
        print("top wrong primary:", Counter(r["primary_pick"] for r in misses).most_common(10))

        stage_stats = defaultdict(lambda: [0, 0, 0])
        for r in rows:
            st = r.get("stage") or "小组赛"
            stage_stats[st][0] += 1
            stage_stats[st][1] += int(r["primary_hit"])
            stage_stats[st][2] += int(r["triple_hit"])
        print("=== BY STAGE ===")
        for st, (t, p, tr) in sorted(stage_stats.items()):
            print(f"  {st}: n={t} primary={p/t*100:.1f}% triple={tr/t*100:.1f}%")

        pub = [r for r in rows if str(r.get("pick_source", "")).startswith("published")]
        rep = [r for r in rows if "replay" in str(r.get("pick_source", ""))]
        if pub:
            print(
                f"published: n={len(pub)} "
                f"primary={sum(r['primary_hit'] for r in pub)/len(pub)*100:.1f}% "
                f"triple={sum(r['triple_hit'] for r in pub)/len(pub)*100:.1f}%"
            )
        if rep:
            print(
                f"replay: n={len(rep)} "
                f"primary={sum(r['primary_hit'] for r in rep)/len(rep)*100:.1f}% "
                f"triple={sum(r['triple_hit'] for r in rep)/len(rep)*100:.1f}%"
            )

        triple_miss = [r for r in rows if not r["triple_hit"]]
        print(f"triple_miss={len(triple_miss)}")
        print("=== TRIPLE MISSES (sample) ===")
        for r in triple_miss[:20]:
            print(
                f"  {r['team_a']} vs {r['team_b']} actual={r['actual_score']} "
                f"picks={r['primary_pick']}/{r['secondary_pick']}/{r.get('upset_pick')} "
                f"stage={r.get('stage')} src={r.get('pick_source')}"
            )


if __name__ == "__main__":
    asyncio.run(main())
