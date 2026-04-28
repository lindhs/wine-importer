# API Key Setup

AI features are optional. The normal deterministic pipeline works without a key.

## .env

```bash
cp .env.example .env
```

Edit `.env`:

```text
OPENAI_API_KEY=sk-proj-your-key
```

Verify:

```bash
python3 setup_api_key.py
```

Run with AI:

```bash
wine-importer run data/raw/wine_raw_test1.csv \
  --canonical data/canonical/wine_canonical_clean.csv \
  --out-dir runs/example \
  --use-ai
```

## Shell

```bash
export OPENAI_API_KEY="sk-proj-your-key"
wine-importer run data.csv --canonical canonical.csv --out-dir runs/example --use-ai
```

`.env` is ignored by git. Do not commit real API keys.
