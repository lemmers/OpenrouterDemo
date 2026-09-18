#!/usr/bin/env python3
"""
or_latency_bench.py

Interleaved latency benchmark: OpenRouter (default routing) vs OpenRouter
(pinned to a single provider) vs the provider's direct API.

Built for the Kestrel AI retention case study. The point of this script is not
to "win" the benchmark. It is to produce a defensible measurement that a
skeptical lead engineer would accept, and to expose the things a laptop
benchmark usually gets wrong:

  1. Unpinned routing can land on a different provider than the direct arm,
     so you end up comparing two different fleets. This script records the
     provider that actually served every single request.
  2. Sequential arms measure time of day. This script interleaves arms
     round robin so both see the same conditions.
  3. Means hide the tail. This script reports p50, p90, p95 and p99.
  4. Prompt caching skews time to first token far more than a network hop.
     This script injects a unique nonce per request by default so neither arm
     gets a free cache hit. Use --allow-cache to measure the cached case.
  5. Cold edge caches inflate the first calls. Use --warmup to discard them.
  6. Single threaded runs never see queueing. Use --concurrency.

Measured per request:
  ttfb_ms     time to the first byte of the stream (transport + routing)
  ttft_ms     time to the first actual text token (what a user feels)
  total_ms    time to the last token
  decode_tps  output tokens per second after the first token (provider fleet)

Requires: pip install requests

Usage:
  export OPENROUTER_API_KEY=sk-or-...
  export ANTHROPIC_API_KEY=sk-ant-...        # optional, enables the direct arm
  python or_latency_bench.py --n 60 --concurrency 4 --warmup 3 --lookup-stats

Cost: roughly (arms x n) requests. At the defaults that is about 180 requests
of ~300 input and ~256 output tokens. Check the printed estimate before you
confirm.
"""

import argparse
import csv
import json
import os
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    sys.exit("Missing dependency. Run: pip install requests")

OR_URL = "https://openrouter.ai/api/v1/chat/completions"
OR_GEN_URL = "https://openrouter.ai/api/v1/generation"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# Verify both slugs before you run. OpenRouter model pages show the exact slug,
# and the Anthropic docs show the direct model id. They are not the same string.
DEFAULT_OR_MODEL = "anthropic/claude-sonnet-4.5"
DEFAULT_DIRECT_MODEL = "claude-sonnet-4-5"

# Provider slug to pin to. Copy the exact slug from the model page on
# OpenRouter. Base slugs match every region and variant for that provider.
DEFAULT_PIN = "anthropic"

# Prompts sized like a real agent assist call: a system style preamble plus a
# short user turn. Keep them stable across arms or the comparison is worthless.
PROMPTS = [
    "You are a support agent assistant. A customer writes: 'My invoice shows "
    "two charges for the same subscription this month.' Draft a reply in three "
    "sentences, apologize once, and state the next step.",
    "You are a support agent assistant. A customer writes: 'The export button "
    "does nothing in Safari.' Draft a reply in three sentences, ask one "
    "clarifying question, and give one workaround.",
    "You are a support agent assistant. A customer writes: 'We need to add nine "
    "seats before Friday.' Draft a reply in three sentences confirming the "
    "change and the billing impact.",
    "You are a support agent assistant. A customer writes: 'Our API key stopped "
    "working after the rotation.' Draft a reply in three sentences with the "
    "most likely cause and the next step.",
]

_print_lock = threading.Lock()
_local = threading.local()


def session() -> requests.Session:
    """One connection pool per worker thread, so arms do not share sockets."""
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        _local.s = s
    return s


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def pct(values, p):
    if not values:
        return None
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def sse_lines(resp):
    """Yield complete SSE lines as they arrive, without waiting on a buffer."""
    buf = b""
    for chunk in resp.iter_content(chunk_size=None):
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield line.rstrip(b"\r")


def blank_record(arm, model):
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arm": arm,
        "model": model,
        "ok": False,
        "http_status": None,
        "error": "",
        "provider_reported": "",
        "ttfb_ms": None,
        "ttft_ms": None,
        "total_ms": None,
        "output_tokens": None,
        "decode_tps": None,
        "gen_id": "",
        "gen_provider_name": "",
        "gen_latency_ms": None,
        "gen_generation_time_ms": None,
        "is_byok": "",
        "total_cost": None,
    }


def finish(rec, t0, t_first_byte, t_first_token, tokens):
    now = time.perf_counter()
    rec["total_ms"] = round((now - t0) * 1000, 1)
    if t_first_byte:
        rec["ttfb_ms"] = round((t_first_byte - t0) * 1000, 1)
    if t_first_token:
        rec["ttft_ms"] = round((t_first_token - t0) * 1000, 1)
        decode_s = now - t_first_token
        if tokens and tokens > 1 and decode_s > 0:
            rec["decode_tps"] = round((tokens - 1) / decode_s, 1)
    rec["output_tokens"] = tokens or None
    rec["ok"] = rec["ttft_ms"] is not None
    return rec


def call_openrouter(arm, provider_block, prompt, cfg):
    rec = blank_record(arm, cfg["or_model"])
    payload = {
        "model": cfg["or_model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": cfg["max_tokens"],
        "temperature": 0,
        "stream": True,
        "usage": {"include": True},
    }
    if provider_block:
        payload["provider"] = provider_block
    headers = {
        "Authorization": f"Bearer {cfg['or_key']}",
        "Content-Type": "application/json",
    }
    if cfg.get("referer"):
        headers["HTTP-Referer"] = cfg["referer"]
        headers["X-OpenRouter-Title"] = "latency-bench"

    t0 = time.perf_counter()
    t_fb = t_ft = None
    tokens = 0
    try:
        with session().post(
            OR_URL, headers=headers, json=payload, stream=True, timeout=(10, 180)
        ) as r:
            rec["http_status"] = r.status_code
            if r.status_code != 200:
                rec["error"] = r.text[:300]
                return rec
            for line in sse_lines(r):
                if t_fb is None:
                    t_fb = time.perf_counter()
                if not line or line.startswith(b":"):
                    # OpenRouter sends ": OPENROUTER PROCESSING" keepalives.
                    continue
                if not line.startswith(b"data: "):
                    continue
                data = line[6:]
                if data == b"[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if obj.get("provider") and not rec["provider_reported"]:
                    rec["provider_reported"] = obj["provider"]
                if obj.get("id") and not rec["gen_id"]:
                    rec["gen_id"] = obj["id"]
                usage = obj.get("usage")
                if usage and usage.get("completion_tokens"):
                    tokens = usage["completion_tokens"]
                for ch in obj.get("choices") or []:
                    piece = (ch.get("delta") or {}).get("content")
                    if piece:
                        if t_ft is None:
                            t_ft = time.perf_counter()
                        if not usage:
                            tokens += 1
    except Exception as exc:  # noqa: BLE001
        rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return rec
    return finish(rec, t0, t_fb, t_ft, tokens)


def call_anthropic_direct(prompt, cfg):
    rec = blank_record("direct", cfg["direct_model"])
    rec["provider_reported"] = "anthropic-direct"
    payload = {
        "model": cfg["direct_model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": cfg["max_tokens"],
        "temperature": 0,
        "stream": True,
    }
    headers = {
        "x-api-key": cfg["anthropic_key"],
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    t0 = time.perf_counter()
    t_fb = t_ft = None
    tokens = 0
    try:
        with session().post(
            ANTHROPIC_URL, headers=headers, json=payload, stream=True, timeout=(10, 180)
        ) as r:
            rec["http_status"] = r.status_code
            if r.status_code != 200:
                rec["error"] = r.text[:300]
                return rec
            for line in sse_lines(r):
                if t_fb is None:
                    t_fb = time.perf_counter()
                if not line.startswith(b"data: "):
                    continue
                try:
                    obj = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                etype = obj.get("type")
                if etype == "content_block_delta":
                    delta = obj.get("delta") or {}
                    if delta.get("text"):
                        if t_ft is None:
                            t_ft = time.perf_counter()
                        tokens += 1
                elif etype == "message_delta":
                    out = (obj.get("usage") or {}).get("output_tokens")
                    if out:
                        tokens = out
                elif etype == "message_stop":
                    break
    except Exception as exc:  # noqa: BLE001
        rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return rec
    return finish(rec, t0, t_fb, t_ft, tokens)


def lookup_generation(rec, cfg):
    """Ask OpenRouter what actually happened. This is the receipt."""
    if not rec.get("gen_id"):
        return
    headers = {"Authorization": f"Bearer {cfg['or_key']}"}
    for attempt in range(4):
        time.sleep(0.6 * (attempt + 1))
        try:
            r = session().get(
                OR_GEN_URL, headers=headers, params={"id": rec["gen_id"]}, timeout=20
            )
            if r.status_code != 200:
                continue
            d = (r.json() or {}).get("data") or {}
            rec["gen_provider_name"] = d.get("provider_name") or ""
            rec["gen_latency_ms"] = d.get("latency")
            rec["gen_generation_time_ms"] = d.get("generation_time")
            rec["is_byok"] = d.get("is_byok", "")
            rec["total_cost"] = d.get("total_cost")
            return
        except Exception:  # noqa: BLE001
            continue


def build_arms(cfg):
    arms = []
    arms.append(("or_default", None))
    arms.append(
        (
            "or_pinned",
            {"order": [cfg["pin"]], "allow_fallbacks": False},
        )
    )
    if cfg["skip_chain"]:
        # First choice cannot serve this model, so the router skips it. This
        # measures routing decision cost, NOT a mid stream failover. Label it
        # honestly on the slide.
        arms.append(
            (
                "or_skip_chain",
                {"order": ["openai", cfg["pin"]], "allow_fallbacks": True},
            )
        )
    if cfg.get("anthropic_key"):
        arms.append(("direct", "DIRECT"))
    return arms


def run_one(arm, provider_block, prompt, cfg):
    if provider_block == "DIRECT":
        rec = call_anthropic_direct(prompt, cfg)
    else:
        rec = call_openrouter(arm, provider_block, prompt, cfg)
        if cfg["lookup"]:
            lookup_generation(rec, cfg)
    status = "ok " if rec["ok"] else "ERR"
    log(
        f"  {status} {arm:<14} ttft={str(rec['ttft_ms']):>8} ms  "
        f"total={str(rec['total_ms']):>8} ms  "
        f"provider={rec['gen_provider_name'] or rec['provider_reported'] or '?'}"
        + (f"  {rec['error']}" if rec["error"] else "")
    )
    return rec


def summarize(records, cfg):
    arms = []
    for r in records:
        if r["arm"] not in arms:
            arms.append(r["arm"])

    rows = []
    for arm in arms:
        rs = [r for r in records if r["arm"] == arm]
        ok = [r for r in rs if r["ok"]]
        ttft = [r["ttft_ms"] for r in ok]
        ttfb = [r["ttfb_ms"] for r in ok if r["ttfb_ms"] is not None]
        total = [r["total_ms"] for r in ok]
        tps = [r["decode_tps"] for r in ok if r["decode_tps"]]
        providers = {}
        for r in ok:
            key = r["gen_provider_name"] or r["provider_reported"] or "unknown"
            providers[key] = providers.get(key, 0) + 1
        rows.append(
            {
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
            }
        )

    w = 16
    print("\n" + "=" * 96)
    print("RESULTS  (all times in milliseconds)")
    print("=" * 96)
    hdr = ["arm", "n", "err%", "ttfb p50", "ttft p50", "ttft p90", "ttft p95", "ttft p99", "tot p50", "tok/s"]
    print("".join(str(h).ljust(10) for h in hdr[:1]) + "".join(str(h).rjust(10) for h in hdr[1:]))
    for row in rows:
        line = row["arm"].ljust(10)
        for k in ["n", "error_rate_pct", "ttfb_p50", "ttft_p50", "ttft_p90",
                  "ttft_p95", "ttft_p99", "total_p50", "decode_tps_median"]:
            line += str(row[k] if row[k] is not None else "-").rjust(10)
        print(line)

    print("\nProvider that actually served each request:")
    for row in rows:
        parts = ", ".join(f"{k} x{v}" for k, v in sorted(row["providers"].items()))
        print(f"  {row['arm']:<14} {parts or 'none'}")

    direct = next((r for r in rows if r["arm"] == "direct"), None)
    if direct and direct["ttft_p50"]:
        print("\nGateway overhead versus direct, measured on this run:")
        for row in rows:
            if row["arm"] == "direct" or not row["ttft_p50"]:
                continue
            d50 = row["ttft_p50"] - direct["ttft_p50"]
            d95 = (row["ttft_p95"] or 0) - (direct["ttft_p95"] or 0)
            share = ""
            if row["total_p50"]:
                share = f"   ({abs(d50) / row['total_p50'] * 100:.1f}% of a full response)"
            print(
                f"  {row['arm']:<14} p50 {d50:+.1f} ms   p95 {d95:+.1f} ms{share}"
            )
        print(
            "\nRead the p95 column, not the p50 column. The p50 is the number the "
            "developer measured. The p95 is the number the end user feels."
        )
    print("=" * 96 + "\n")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=60, help="requests per arm (default 60)")
    ap.add_argument("--concurrency", type=int, default=1, help="parallel in flight requests")
    ap.add_argument("--warmup", type=int, default=2, help="discarded requests per arm, for cold edge caches")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--or-model", default=DEFAULT_OR_MODEL)
    ap.add_argument("--direct-model", default=DEFAULT_DIRECT_MODEL)
    ap.add_argument("--pin", default=DEFAULT_PIN, help="provider slug for the pinned arm")
    ap.add_argument("--allow-cache", action="store_true", help="do not add a per request nonce")
    ap.add_argument("--skip-chain", action="store_true", help="add an arm whose first provider cannot serve the model")
    ap.add_argument("--lookup-stats", action="store_true", help="fetch the generation record for every OpenRouter call")
    ap.add_argument("--no-direct", action="store_true", help="skip the direct Anthropic arm")
    ap.add_argument("--out", default="bench", help="output file prefix (default bench)")
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    args = ap.parse_args()

    or_key = os.environ.get("OPENROUTER_API_KEY")
    if not or_key:
        sys.exit("Set OPENROUTER_API_KEY first.")
    anthropic_key = None if args.no_direct else os.environ.get("ANTHROPIC_API_KEY")

    cfg = {
        "or_key": or_key,
        "anthropic_key": anthropic_key,
        "or_model": args.or_model,
        "direct_model": args.direct_model,
        "pin": args.pin,
        "max_tokens": args.max_tokens,
        "lookup": args.lookup_stats,
        "skip_chain": args.skip_chain,
        "referer": os.environ.get("BENCH_REFERER", ""),
    }

    arms = build_arms(cfg)
    total_calls = (args.n + args.warmup) * len(arms)
    print(f"\nArms: {', '.join(a for a, _ in arms)}")
    print(f"Model: {args.or_model}  (direct: {args.direct_model if anthropic_key else 'skipped'})")
    print(f"Requests: {args.n} per arm plus {args.warmup} warmup, concurrency {args.concurrency}")
    print(f"Total billable calls: {total_calls} at up to {args.max_tokens} output tokens each")
    if not anthropic_key and not args.no_direct:
        print("NOTE: ANTHROPIC_API_KEY is not set, so there is no direct arm to compare against.")
    if not args.yes:
        if input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            sys.exit("Cancelled.")

    tasks = []
    for i in range(args.warmup + args.n):
        for arm, block in arms:
            prompt = PROMPTS[i % len(PROMPTS)]
            if not args.allow_cache:
                prompt = f"[trace {uuid.uuid4().hex[:12]}]\n{prompt}"
            tasks.append((i, arm, block, prompt))

    print(f"\nRunning {len(tasks)} requests, interleaved...\n")
    started = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = [(i, pool.submit(run_one, arm, block, prompt, cfg))
                   for i, arm, block, prompt in tasks]
        for i, fut in futures:
            rec = fut.result()
            rec["warmup"] = i < args.warmup
            results.append(rec)

    kept = [r for r in results if not r["warmup"]]
    print(f"\nDone in {time.time() - started:.1f}s. "
          f"Kept {len(kept)} of {len(results)} (warmup discarded).")

    csv_path = f"{args.out}_raw.csv"
    fields = [k for k in blank_record("x", "y").keys()] + ["warmup"]
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    rows = summarize(kept, cfg)

    json_path = f"{args.out}_summary.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "config": {
                    "or_model": args.or_model,
                    "direct_model": args.direct_model if anthropic_key else None,
                    "pin": args.pin,
                    "n_per_arm": args.n,
                    "warmup": args.warmup,
                    "concurrency": args.concurrency,
                    "max_tokens": args.max_tokens,
                    "cache_allowed": args.allow_cache,
                },
                "arms": rows,
            },
            fh,
            indent=2,
        )

    print(f"Raw data:  {csv_path}")
    print(f"Summary:   {json_path}   (feed this into the demo page)")


if __name__ == "__main__":
    main()
