# Real Benchmark Findings

Live measurement against a real OpenRouter account, run 2026-09-21. This replaces
the modeled numbers in `data/sample/` with actual data for the two OpenRouter
arms. Raw CSVs and summary JSONs are in `data/real/`.

## Setup

- Script: `benchmark/or_latency_bench.py`
- Model: `anthropic/claude-sonnet-4.5`, pin: `anthropic`
- Only two arms ran: `or_default` (unpinned, load balanced) and `or_pinned`
  (locked to Anthropic, fallbacks disabled). **No `direct` arm** — no
  Anthropic API key was available for this session (a Claude Pro subscription
  does not include API access; that requires a separate console.anthropic.com
  account with billed credits).
- Three runs, all with `--lookup-stats` so every result is corroborated by
  OpenRouter's own generation record (provider, latency, cost):

  | Run | Command flags | n/arm | Total calls |
  | --- | --- | --- | --- |
  | Standard | `--n 60 --warmup 3 --concurrency 4` | 60 | 126 |
  | Loaded | `--n 200 --warmup 3 --concurrency 8` | 200 | 406 |
  | Cached | `--n 60 --warmup 3 --concurrency 4 --allow-cache` | 60 | 126 |

- Total real spend across all 658 billed calls: **$0.81** (well under the
  ~$3.00 pre-run estimate).

## Results

All times in milliseconds. `ttft` = time to first token (the user-felt
number); `total` = time to last token.

| Run | Arm | Provider served | ttft p50 | ttft p90 | ttft p95 | ttft p99 | total p50 | error % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Standard | or_default | Amazon Bedrock (100%) | 1991 | 3054 | 3814 | 9462 | 4051 | 0.0 |
| Standard | or_pinned | Anthropic (100%) | 1566 | 2596 | 3092 | 3687 | 3803 | 0.0 |
| Loaded (conc. 8) | or_default | Amazon Bedrock (100%) | 1949 | 3049 | 3395 | 7213 | 3939 | 0.0 |
| Loaded (conc. 8) | or_pinned | Anthropic (100%) | 1517 | 2377 | 2729 | 4083 | 3735 | 0.0 |
| Cached | or_default | Amazon Bedrock (100%) | 2181 | 3054 | 4049 | 5318 | 3934 | 0.0 |
| Cached | or_pinned | Anthropic (100%) | 1737 | 2563 | 3451 | 4082 | 3781 | 0.0 |

## Key findings

1. **The gap is real, and it is a provider-fleet gap, not a gateway tax.**
   In all three runs, unpinned (`or_default`) routing landed **100% of
   traffic on Amazon Bedrock**; the pinned arm stayed 100% on Anthropic.
   The ~400-450ms p50 gap between the arms tracks that specific fleet
   difference, on this day, not a fixed cost of the OpenRouter hop itself.
   A run on a different day could land the default arm on a different
   provider mix with a different gap, larger or smaller.

2. **The tail is where the real pain is.** p50 gaps are a few hundred
   milliseconds, but p99 on the unpinned arm hit 9.4s (standard run) and
   7.2s (loaded run) versus 3.7s and 4.1s pinned. This is the number to
   put in front of the developer: the typical case is close, the bad case
   is not.

3. **Decode speed (tokens/sec) doesn't materially differ by pin status**
   (~39-46 tok/s across all arms and runs) — consistent with the
   explainer's point that decode speed is set by provider hardware, not
   by the gateway, once you've isolated for which provider actually served
   the request.

4. **Zero errors occurred in any of the 646 live requests.** This is
   expected for a short test on a healthy day and it means **this data
   cannot support the reliability/failover argument**. The "spreading
   across providers prevents ~40x more failed requests" claim remains
   backed only by the modeled `incident_modeled` scenario in
   `data/sample/` — say so plainly if asked.

5. **The cached run does not demonstrate a caching benefit, and should
   not be presented as if it does.** `--allow-cache` only removes the
   anti-cache nonce; it does not add Anthropic's `cache_control` markers,
   and the test prompts (~60-90 tokens) are far under Anthropic's
   ~1024-token minimum cacheable prefix. The observed numbers (slightly
   higher, not lower, ttft) are noise, not a caching signal. The 235ms
   caching claim also remains a modeled number, not a measured one from
   this run.

## What this means for the pitch

- Lead with finding #1 and #2: real data, real account, and the honest
  admission that the gap exists — while reframing it as a provider
  difference recoverable by pinning, with the tail as the number that
  actually matters for an SLA-bound product.
- Do **not** claim real evidence for the caching benefit or the failure
  -avoidance benefit from this data set. Both stay clearly labeled as
  modeled, exactly as `data/sample/` already discloses.
- If asked "did you test failover," the honest answer is: not directly —
  no provider outage occurred during the live window — and the credible
  fallback is either historical incident data from the account, or a
  30-day joint monitoring window as proposed in the plain English
  explainer.
- If time allows before the call, getting a real `direct` (Anthropic API)
  data point would complete the three-arm comparison; it requires a
  separate console.anthropic.com account with billed credits, which a
  Claude Pro subscription does not provide.

## Where the data lives

- `data/real/real_standard_{raw.csv,summary.json}`
- `data/real/real_loaded_{raw.csv,summary.json}`
- `data/real/real_cached_{raw.csv,summary.json}`
- `data/real/README.md` — same caveats as above, machine-readable context
  for whoever builds the slides or demo page next.
