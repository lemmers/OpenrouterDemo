#!/usr/bin/env python3
"""
make_sample_data.py

Generates SYNTHETIC benchmark data in exactly the same shape as
or_latency_bench.py produces, so you can build slides and the demo page
before (or instead of) running the live test.

THIS IS MODELED DATA, NOT MEASUREMENT.

Every row carries synthetic=True and every summary carries "synthetic": true,
so the files label themselves. Use them to build. If you present a number that
came from here, say it is modeled. Do not describe it as something you ran.

The distributions are built from published gateway overhead reports (roughly
25 to 250 ms of routing overhead depending on model, region and provider) and
from ordinary streaming behavior for a Claude Sonnet class model at a few
hundred output tokens. They are plausible. They are not Kestrel's traffic and
they are not anyone's traffic.

Usage:
  python3 make_sample_data.py                 # all scenarios
  python3 make_sample_data.py --scenario loaded
  python3 make_sample_data.py --seed 7        # different but reproducible draw
"""

import argparse
import csv
import json
import random
import statistics
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Model of the world
# ---------------------------------------------------------------------------
# Each provider fleet has its own time to first token profile and its own
# decode speed. This is the single most important thing the data has to show:
# a gateway does not change decode speed, because decode happens on the
# provider's hardware either way. What changes is which fleet you land on.

PROVIDERS = {
    "Anthropic": {"ttft_med": 372, "ttft_sigma": 0.30, "tps_mean": 66, "tps_sd": 6},
    "Amazon Bedrock": {"ttft_med": 448, "ttft_sigma": 0.36, "tps_mean": 61, "tps_sd": 8},
    "Google Vertex": {"ttft_med": 421, "ttft_sigma": 0.33, "tps_mean": 64, "tps_sd": 7},
}

# Where unpinned routing lands. Default behavior load balances across top
# providers weighted toward lower price, so it does not sit on one fleet.
DEFAULT_ROUTING_MIX = [("Anthropic", 0.42), ("Amazon Bedrock", 0.34), ("Google Vertex", 0.24)]

# Client side overhead added by the gateway hop, in milliseconds.
GATEWAY_HOP_MED = 31
GATEWAY_HOP_SIGMA = 0.45

SCENARIOS = {
    "morning": {
        "label": "Weekday morning, light load",
        "n": 60, "concurrency": 4, "hour": 9,
        "load": 1.00, "cached": False,
        "err": {"direct": 0.008, "or_pinned": 0.008, "or_default": 0.002},
    },
    "midday": {
        "label": "Weekday midday, moderate load",
        "n": 60, "concurrency": 4, "hour": 13,
        "load": 1.12, "cached": False,
        "err": {"direct": 0.015, "or_pinned": 0.013, "or_default": 0.003},
    },
    "evening": {
        "label": "Weekday evening, light load",
        "n": 60, "concurrency": 4, "hour": 19,
        "load": 0.96, "cached": False,
        "err": {"direct": 0.007, "or_pinned": 0.007, "or_default": 0.002},
    },
    "loaded": {
        "label": "Peak concurrency, 8 in flight",
        "n": 200, "concurrency": 8, "hour": 11,
        "load": 1.35, "cached": False,
        "err": {"direct": 0.028, "or_pinned": 0.021, "or_default": 0.003},
    },
    "cached": {
        "label": "Prompt caching enabled, warm prefix",
        "n": 60, "concurrency": 4, "hour": 10,
        "load": 1.00, "cached": True,
        "err": {"direct": 0.008, "or_pinned": 0.008, "or_default": 0.002},
    },
    "incident_modeled": {
        "label": "MODELED provider capacity event, 40 percent through the run",
        "n": 200, "concurrency": 8, "hour": 15,
        "load": 1.25, "cached": False, "incident": True,
        "err": {"direct": 0.115, "or_pinned": 0.098, "or_default": 0.006},
    },
}

ARMS = ["or_default", "or_pinned", "direct"]

FIELDS = [
    "ts", "arm", "model", "ok", "http_status", "error", "provider_reported",
    "ttfb_ms", "ttft_ms", "total_ms", "output_tokens", "decode_tps",
    "gen_id", "gen_provider_name", "gen_latency_ms", "gen_generation_time_ms",
    "is_byok", "total_cost", "warmup", "synthetic",
]

OR_MODEL = "anthropic/claude-sonnet-4.5"
DIRECT_MODEL = "claude-sonnet-4-5"


def pct(values, p):
    if not values:
        return None
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def pick_provider(rng):
    r = rng.random()
    acc = 0.0
    for name, w in DEFAULT_ROUTING_MIX:
        acc += w
        if r <= acc:
            return name
    return DEFAULT_ROUTING_MIX[-1][0]


def draw_request(rng, arm, cfg, in_incident):
    """Produce one row. Returns a dict matching the real script's schema."""
    sc_load = cfg["load"]

    if arm == "direct":
        provider = "Anthropic"
        gateway_hop = 0.0
        model = DIRECT_MODEL
    elif arm == "or_pinned":
        provider = "Anthropic"
        gateway_hop = rng.lognormvariate(0, GATEWAY_HOP_SIGMA) * GATEWAY_HOP_MED
        model = OR_MODEL
    else:
        provider = pick_provider(rng)
        gateway_hop = rng.lognormvariate(0, GATEWAY_HOP_SIGMA) * GATEWAY_HOP_MED
        model = OR_MODEL

    prof = PROVIDERS[provider]

    # Error draw. During a modeled incident the Anthropic fleet degrades, so
    # arms locked to it take the hit and the load balanced arm routes around.
    err_rate = cfg["err"][arm]
    if in_incident:
        err_rate = err_rate * (3.2 if provider == "Anthropic" else 0.5)

    row = {f: "" for f in FIELDS}
    row["arm"] = arm
    row["model"] = model
    row["synthetic"] = True
    row["warmup"] = False
    row["is_byok"] = False
    row["provider_reported"] = "anthropic-direct" if arm == "direct" else provider
    row["gen_provider_name"] = "" if arm == "direct" else provider
    row["gen_id"] = "" if arm == "direct" else f"gen-SYNTH{rng.randrange(10**10, 10**11)}"

    if rng.random() < err_rate:
        row["ok"] = False
        row["http_status"] = 429 if rng.random() < 0.8 else 529
        row["error"] = "rate limit exceeded" if row["http_status"] == 429 else "provider overloaded"
        for k in ("ttfb_ms", "ttft_ms", "total_ms", "output_tokens", "decode_tps",
                  "gen_latency_ms", "gen_generation_time_ms", "total_cost"):
            row[k] = ""
        return row

    # Time to first token: provider prefill and queueing, scaled by load.
    ttft = prof["ttft_med"] * sc_load * rng.lognormvariate(0, prof["ttft_sigma"])

    # A warm prefix cache removes most of prefill. This is the point of the
    # cached scenario: caching moves this number far more than a hop does.
    if cfg["cached"]:
        ttft *= rng.uniform(0.30, 0.44)

    ttft += gateway_hop

    # The load balanced arm recovers from a bad first attempt by retrying
    # elsewhere. It stays up, but the retried request pays twice. This is the
    # honest trade: availability bought with tail latency.
    retried = False
    if arm == "or_default" and rng.random() < (0.055 if in_incident else 0.012):
        ttft += prof["ttft_med"] * rng.uniform(0.8, 1.6)
        retried = True

    # Occasional tail event on any arm.
    if rng.random() < 0.02:
        ttft *= rng.uniform(1.8, 3.4)

    tokens = rng.randint(214, 256)
    tps = max(18.0, rng.gauss(prof["tps_mean"], prof["tps_sd"]) / (1 + (sc_load - 1) * 0.35))
    decode_ms = (tokens - 1) / tps * 1000.0
    total = ttft + decode_ms

    row["ok"] = True
    row["http_status"] = 200
    # First byte arrives before the first text token. On the routed arms the
    # stream opens sooner because of keepalive traffic, which is exactly why
    # time to first byte alone is a misleading metric to argue from.
    ttfb_ratio = rng.uniform(0.62, 0.78) if arm != "direct" else rng.uniform(0.84, 0.93)
    row["ttfb_ms"] = round(ttft * ttfb_ratio, 1)
    row["ttft_ms"] = round(ttft, 1)
    row["total_ms"] = round(total, 1)
    row["output_tokens"] = tokens
    row["decode_tps"] = round(tps, 1)
    if arm != "direct":
        # OpenRouter's own measurement excludes the client to edge leg.
        row["gen_latency_ms"] = round(ttft * rng.uniform(0.90, 0.95))
        row["gen_generation_time_ms"] = round(decode_ms)
        row["total_cost"] = round(320 / 1e6 * 3 + tokens / 1e6 * 15, 6)
    else:
        row["gen_latency_ms"] = ""
        row["gen_generation_time_ms"] = ""
        row["total_cost"] = ""
    row["_retried"] = retried
    return row


def build_scenario(name, cfg, seed):
    rng = random.Random(f"{seed}:{name}")
    base = datetime.now(timezone.utc).replace(
        hour=cfg["hour"], minute=0, second=0, microsecond=0
    ) - timedelta(days=2)

    rows = []
    n = cfg["n"]
    incident_from, incident_to = int(n * 0.40), int(n * 0.62)
    for i in range(n):
        in_incident = cfg.get("incident") and incident_from <= i < incident_to
        stamp = (base + timedelta(seconds=i * 3.2)).isoformat(timespec="seconds")
        for arm in ARMS:
            row = draw_request(rng, arm, cfg, in_incident)
            row["ts"] = stamp
            rows.append(row)
    return rows


def summarize(rows, name, cfg):
    out = []
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        ok = [r for r in rs if r["ok"] is True]
        ttft = [r["ttft_ms"] for r in ok]
        ttfb = [r["ttfb_ms"] for r in ok]
        total = [r["total_ms"] for r in ok]
        tps = [r["decode_tps"] for r in ok]
        providers = {}
        for r in ok:
            key = r["gen_provider_name"] or r["provider_reported"]
            providers[key] = providers.get(key, 0) + 1
        out.append({
            "arm": arm,
            "n": len(rs),
            "errors": len(rs) - len(ok),
            "error_rate_pct": round(100.0 * (len(rs) - len(ok)) / max(len(rs), 1), 2),
            "ttfb_p50": round(pct(ttfb, 50), 1) if ttfb else None,
            "ttft_p50": round(pct(ttft, 50), 1) if ttft else None,
            "ttft_p90": round(pct(ttft, 90), 1) if ttft else None,
            "ttft_p95": round(pct(ttft, 95), 1) if ttft else None,
            "ttft_p99": round(pct(ttft, 99), 1) if ttft else None,
            "total_p50": round(pct(total, 50), 1) if total else None,
            "total_p95": round(pct(total, 95), 1) if total else None,
            "decode_tps_median": round(statistics.median(tps), 1) if tps else None,
            "providers": providers,
        })
    return out


def print_table(name, cfg, rows_summary):
    print("\n" + "=" * 98)
    print(f"{name}   [{cfg['label']}]   SYNTHETIC")
    print("=" * 98)
    hdr = ["arm", "n", "err%", "ttfb p50", "ttft p50", "ttft p90", "ttft p95",
           "ttft p99", "tot p50", "tok/s"]
    print(hdr[0].ljust(12) + "".join(h.rjust(10) for h in hdr[1:]))
    for row in rows_summary:
        line = row["arm"].ljust(12)
        for k in ["n", "error_rate_pct", "ttfb_p50", "ttft_p50", "ttft_p90",
                  "ttft_p95", "ttft_p99", "total_p50", "decode_tps_median"]:
            line += str(row[k] if row[k] is not None else "-").rjust(10)
        print(line)
    for row in rows_summary:
        parts = ", ".join(f"{k} x{v}" for k, v in sorted(row["providers"].items()))
        print(f"  {row['arm']:<12} served by: {parts}")
    direct = next((r for r in rows_summary if r["arm"] == "direct"), None)
    if direct and direct["ttft_p50"]:
        print("  overhead vs direct:")
        for row in rows_summary:
            if row["arm"] == "direct":
                continue
            d50 = row["ttft_p50"] - direct["ttft_p50"]
            d95 = row["ttft_p95"] - direct["ttft_p95"]
            share = abs(d50) / row["total_p50"] * 100
            print(f"    {row['arm']:<12} p50 {d50:+7.1f} ms   p95 {d95:+8.1f} ms   "
                  f"({share:.1f}% of a full response)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="all", choices=["all", *SCENARIOS.keys()])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--prefix", default="sample")
    args = ap.parse_args()

    names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    written = []

    for name in names:
        cfg = SCENARIOS[name]
        rows = build_scenario(name, cfg, args.seed)
        summary = summarize(rows, name, cfg)
        print_table(name, cfg, summary)

        csv_path = f"{args.prefix}_{name}_raw.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
            wr.writeheader()
            for r in rows:
                wr.writerow(r)

        json_path = f"{args.prefix}_{name}_summary.json"
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump({
                "synthetic": True,
                "disclaimer": "Modeled data generated by make_sample_data.py. "
                              "Not a measurement. Do not present as a test you ran.",
                "scenario": name,
                "scenario_label": cfg["label"],
                "seed": args.seed,
                "config": {
                    "or_model": OR_MODEL,
                    "direct_model": DIRECT_MODEL,
                    "pin": "anthropic",
                    "n_per_arm": cfg["n"],
                    "concurrency": cfg["concurrency"],
                    "cache_allowed": cfg["cached"],
                },
                "arms": summary,
            }, fh, indent=2)
        written += [csv_path, json_path]

    print("\n" + "-" * 98)
    print("Files written:")
    for f in written:
        print("  " + f)
    print("\nAll of it is modeled. Label it as such on any slide it reaches.")


if __name__ == "__main__":
    main()
