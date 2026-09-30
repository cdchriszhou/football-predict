# -*- coding: utf-8 -*-
"""Audit recent SSQ repeat rates vs hot-number predictive power."""
from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

import httpx

OUT = Path(__file__).with_name("_ssq_recent_repeat_audit.json")


def fetch_draws(n: int = 40) -> list[dict]:
    urls = (
        "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice",
        "https://www.cwl.gov.cn/cwl_admin/kjxx/findDrawNotice",
    )
    params = {
        "name": "ssq",
        "issueCount": str(n),
        "pageNo": "1",
        "pageSize": str(n),
        "systemType": "PC",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.cwl.gov.cn/kjxx/ssq/",
        "Accept": "application/json",
    }
    draws: list[dict] = []
    with httpx.Client(timeout=25, follow_redirects=True) as client:
        for url in urls:
            try:
                resp = client.get(url, params=params, headers=headers)
                rows = (resp.json() or {}).get("result") or []
                for row in rows:
                    red = [
                        int(x)
                        for x in str(row.get("red", "")).replace(" ", ",").split(",")
                        if x.strip().isdigit()
                    ]
                    blue_raw = str(row.get("blue", "0")).lstrip("0") or "0"
                    blue = int(blue_raw)
                    if len(red) == 6 and 1 <= blue <= 16:
                        draws.append(
                            {
                                "issue": str(row.get("code")),
                                "red": sorted(red),
                                "blue": blue,
                            }
                        )
                if draws:
                    break
            except Exception as exc:  # noqa: BLE001
                print("fetch err", url, exc)
    return draws


def main() -> None:
    draws = fetch_draws(40)
    if not draws:
        raise SystemExit("no draws")

    overlaps = []
    for i in range(min(30, len(draws) - 1)):
        overlaps.append(len(set(draws[i]["red"]) & set(draws[i + 1]["red"])))

    freq_blocks = {}
    for w in (10, 20):
        cnt: Counter[int] = Counter()
        for d in draws[:w]:
            cnt.update(d["red"])
        freq_blocks[f"last_{w}"] = {
            "top10": cnt.most_common(10),
            "uniform_expected_count": round(w * 6 / 33, 3),
        }

    blue20 = Counter(d["blue"] for d in draws[:20]).most_common()

    # Walk-forward: hot-6 from previous 10 vs random-6
    rng = random.Random(0)
    hits_hot: list[int] = []
    hits_rand: list[int] = []
    for i in range(25):
        hist = draws[i + 1 : i + 11]
        if len(hist) < 10:
            break
        cnt = Counter()
        for d in hist:
            cnt.update(d["red"])
        hot = [n for n, _ in cnt.most_common(6)]
        actual = set(draws[i]["red"])
        hits_hot.append(len(actual & set(hot)))
        hits_rand.append(len(actual & set(rng.sample(range(1, 34), 6))))

    # Adjacent-period "重号" rate
    overlap_dist = dict(Counter(overlaps))

    payload = {
        "newest": draws[0],
        "recent_12": [
            {
                "issue": d["issue"],
                "result": " ".join(f"{x:02d}" for x in d["red"]) + f" + {d['blue']:02d}",
            }
            for d in draws[:12]
        ],
        "consecutive_overlap": {
            "mean": round(sum(overlaps) / len(overlaps), 4),
            "theory_mean": round(36 / 33, 4),
            "dist": {str(k): v for k, v in sorted(overlap_dist.items())},
            "note": "相邻两期红球交集大小；公平开奖期望约 1.09",
        },
        "frequency": freq_blocks,
        "blue_last20": blue20,
        "hot6_walkforward": {
            "n": len(hits_hot),
            "hot6_avg_hits": round(sum(hits_hot) / len(hits_hot), 4) if hits_hot else None,
            "random6_avg_hits": round(sum(hits_rand) / len(hits_rand), 4) if hits_rand else None,
            "theory_single6": round(36 / 33, 4),
            "hot_dist": dict(Counter(hits_hot)),
            "verdict": None,
        },
    }
    h = payload["hot6_walkforward"]["hot6_avg_hits"]
    r = payload["hot6_walkforward"]["random6_avg_hits"]
    if h is not None and r is not None:
        payload["hot6_walkforward"]["verdict"] = (
            "no_edge" if abs(h - r) < 0.15 and abs(h - 36 / 33) < 0.25 else "weak_signal_check"
        )

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
