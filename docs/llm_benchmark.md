# LLM Benchmark Script

Script: [scripts/benchmark_llm.py](scripts/benchmark_llm.py)

Quick start:

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run (simulate backend):

```bash
python scripts/benchmark_llm.py --file docs/sample.md --backend simulate --iterations 3
```

3. Run (OpenAI backend):

```bash
export OPENAI_API_KEY="sk-..."
python scripts/benchmark_llm.py --file path/to/3page.md --backend openai --model gpt-4o-mini --iterations 2
```

Notes:
- The script prints per-iteration latency and a short summary.
- Token counts are estimated (chars/4) for throughput calculation.
