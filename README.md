# FieldForge

Capture a job (photos + voice) → a supervised small-model agent forges an itemized estimate. Build Small Hackathon entry. See `docs/superpowers/specs/` and `docs/adr/`.

## Run
```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m fieldforge.app
```

## Test
```
pytest -v
```

Models are stubbed in the core build; real Private/Best stacks wire in via `fieldforge/resolver.py`. Pricing is clearly-labeled sample data.
