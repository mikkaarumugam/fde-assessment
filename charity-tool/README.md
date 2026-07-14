# Charity Growth Lookup

The full project documentation — features, how to run it, and the decisions
made — lives in the [top-level README](../README.md).

Quick start:

```bash
cp .env.example .env          # add your Charity Commission API key
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload  # then open http://localhost:8000
```
