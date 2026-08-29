# Vera AI Bot

## Approach

4-context deterministic message composer powered by Google Gemini.

### Architecture
- **FastAPI** HTTP server with 5 endpoints matching the judge contract
- **In-memory context store** with version-aware idempotent upserts
- **Gemini 2.5 Flash** LLM for message composition (temperature=0 for determinism)
- **Structured prompts** encoding the scoring rubric, hard rules, and gold-standard examples

### How It Works

1. **Context Ingestion** (`POST /v1/context`): The judge pushes category, merchant, customer, and trigger contexts. We store them in a versioned in-memory dictionary with idempotency checking.

2. **Proactive Composition** (`POST /v1/tick`): For each available trigger, we:
   - Look up the trigger → find the target merchant → find their category
   - Check suppression keys to avoid duplicates
   - Feed all 4 context layers into a structured Gemini prompt
   - The prompt encodes the 5 scoring dimensions + hard rules + examples
   - Parse the JSON output into a TickAction

3. **Reactive Replies** (`POST /v1/reply`): When a merchant/customer replies:
   - Fast pattern matching catches auto-replies → `wait` (4h)
   - Fast pattern matching catches opt-outs → `end`
   - All other replies go through Gemini for contextual response

### Key Design Decisions

- **Temperature=0**: Deterministic output for reproducible scoring
- **JSON response mode**: Force Gemini to output valid JSON (no parsing errors)
- **URL stripping**: Auto-remove URLs from output to avoid -3 penalty
- **Suppression tracking**: In-memory set prevents duplicate messages
- **Safe fallbacks**: If LLM fails, return a generic but valid response

### Model Choice
Gemini 2.5 Flash — fast enough to stay under 30s timeout, cheap enough for iteration, quality sufficient for 40+ scores with good prompts.

## Setup

```bash
pip install -r requirements.txt
# Set GEMINI_API_KEY in .env
python main.py
```

## Tradeoffs
- In-memory store means state is lost on restart (acceptable for the 60-min test window)
- Single LLM call per message (no retrieval/re-ranking pipeline) to stay under timeout
- Could improve with few-shot examples per trigger kind, but current system prompt covers the key patterns
