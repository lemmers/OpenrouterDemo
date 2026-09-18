# Benchmark

Two scripts. One measures, one models.

## or_latency_bench.py

Runs three arms round robin against the same prompts:

- `or_default` OpenRouter with no provider specified, load balanced across providers
- `or_pinned` OpenRouter pinned to a single provider, fallbacks disabled
- `direct` straight to the Anthropic API

Records the provider that actually served each request, separates time to first byte from time to first token, and reports p50 through p99 plus error rate rather than an average.

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export OPENROUTER_API_KEY="sk-or-v1-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

Before the first real run:

1. Verify the OpenRouter model slug on the model page, and the Anthropic direct model id in the Anthropic docs. They are different strings.
2. Copy the exact provider slug from the model page and pass it with `--pin`.
3. Keep a healthy credit balance. A low balance causes more aggressive edge cache expiry, which inflates latency and will poison your numbers.

### Running

```bash
# smoke test, about 12 calls
python3 or_latency_bench.py --n 2 --warmup 1 --lookup-stats --yes

# full run
python3 or_latency_bench.py --n 60 --warmup 3 --concurrency 4 --lookup-stats --out morning
```

Always use `--lookup-stats`. It pulls the generation record for each OpenRouter call and returns the provider name, OpenRouter's own measured latency, generation time, BYOK status and cost. That is the receipt when someone disputes a number.

### Useful runs

| Command | What it shows |
| --- | --- |
| Three runs at different hours | Time of day variance |
| `--concurrency 8` | Behavior under load, where error rates diverge |
| `--allow-cache` | What prompt caching does to time to first token |
| `--skip-chain` | Cost of a routing decision when the first choice provider cannot serve the model |

`--skip-chain` measures a provider skip, not a mid stream failover. Label it accurately on any slide.

### Output

Two files per run: `PREFIX_raw.csv` with every request, and `PREFIX_summary.json` with the per arm percentile summary.

Key columns: `ttfb_ms` first byte of the stream, `ttft_ms` first actual text token, `total_ms` to the last token, `decode_tps` output tokens per second after the first, `gen_provider_name` the provider that really served it.

## make_sample_data.py

Generates modeled data in the identical format so slides and the demo page can be built before the real test runs.

```bash
python3 make_sample_data.py              # all six scenarios
python3 make_sample_data.py --seed 7     # different but reproducible
```

Output is **not measurement**. Every row carries `synthetic=True` and every summary JSON opens with a disclaimer field. Keep that visible on anything built from it.
