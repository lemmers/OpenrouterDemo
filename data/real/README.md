# Real benchmark data

Produced by `benchmark/or_latency_bench.py` against a live OpenRouter account
on 2026-09-21. This is **measured, not modeled** — the opposite of
`data/sample/`.

| File prefix | Command | n/arm | Notes |
| --- | --- | --- | --- |
| `real_standard` | `--n 60 --warmup 3 --concurrency 4 --lookup-stats` | 60 | Baseline comparison |
| `real_loaded` | `--n 200 --warmup 3 --concurrency 8 --lookup-stats` | 200 | Higher concurrency |
| `real_cached` | `--n 60 --warmup 3 --concurrency 4 --lookup-stats --allow-cache` | 60 | See caveat below |

## What this run showed

- No `direct` arm: no Anthropic API key was available, so only `or_default`
  (unpinned) and `or_pinned` (pinned to Anthropic) ran.
- In all three runs, `or_default` landed **100% of requests on Amazon
  Bedrock** and `or_pinned` stayed 100% on Anthropic. The p50 gap
  (roughly 400-450ms) and the much fatter p99 tail on `or_default` reflect
  that specific provider-fleet difference on this day, not a fixed
  "OpenRouter tax." A different day could land the default arm on a
  different mix of providers with a different gap.
- All three runs had **0% errors**, so none of them can support the
  reliability/failover argument — that still relies on the modeled
  `incident_modeled` scenario in `data/sample/`.
- The `real_cached` run does **not** demonstrate a prompt-caching benefit.
  `--allow-cache` only removes the anti-cache nonce; it does not add
  Anthropic's `cache_control` markers, and these prompts (~60-90 tokens)
  are well under Anthropic's ~1024-token minimum cacheable prefix. Do not
  present this run as evidence for the caching claim.
