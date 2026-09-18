# OpenRouter CSM Case Study

Working materials for a technical case study interview: a 20 minute retention presentation plus 5 to 10 minutes of Q and A, delivered to a hiring manager playing a CTO and a team member playing a developer.

**The brief.** You are the CSM. Ninety days from renewal on a large account, a lead developer emails claiming OpenRouter adds unnecessary latency versus going direct to Anthropic, and the CTO is copied. Address the developer's concern technically while making the business case to the CTO.

## What is in here

| Path | What it is |
| --- | --- |
| `docs/01-plain-english-explainer.md` | The problem and the proposed solution in ordinary language. Start here. |
| `docs/02-prep-pack.pdf` | Strategy, time budget, account profile, latency coaching, Q and A prep, traps. |
| `benchmark/or_latency_bench.py` | Real benchmark. Compares routed, pinned, and direct. See `benchmark/README.md`. |
| `benchmark/make_sample_data.py` | Generates modeled data in the same format, for building slides before running the real test. |
| `data/sample/` | Six modeled scenarios, CSV plus summary JSON. |

## The argument in one paragraph

The developer's benchmark almost certainly compared different providers rather than measuring the gateway. OpenRouter load balances across Anthropic, Amazon Bedrock and Google Vertex by default, so an unpinned test is a provider mix versus one specific provider. Pinning to a single provider removes most of the measured gap. The real gateway cost is roughly 30 ms on a 3.9 second response. Meanwhile prompt caching is worth about 235 ms and is sitting unused. The tradeoff that actually matters is tail reliability: spreading across providers costs about 78 ms at p50 and prevents roughly forty times as many failed requests.

## Data honesty

Everything in `data/sample/` is **modeled, not measured**. Every row carries `synthetic=True` and every summary JSON opens with a disclaimer. Do not present any of it as a test that was run. Use it to build, then replace it with output from `or_latency_bench.py` against a real account.

## Where a collaborator can help

1. Run `or_latency_bench.py` against a real OpenRouter account and replace the sample data with real output
2. Build the slide deck against whichever dataset is current
3. Build the interactive demo page (three states: unpinned, pinned, modeled provider failure) driven by a summary JSON
4. Verify current OpenRouter pricing, BYOK allowances, and provider routing field names against the live docs, since these changed more than once in 2026
5. Rehearse the pitch to 15 minutes with a timer, leaving 5 for interruptions

## Never commit

API keys, `.env` files, or anything containing `sk-or-` or `sk-ant-`. The `.gitignore` covers the common cases but check your diff before pushing.
