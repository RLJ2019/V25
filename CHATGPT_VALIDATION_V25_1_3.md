# ChatGPT local validation V25.1.3

Expected local validation commands:

```bash
python -m compileall football_agent -q
python smoke_test.py
python -m unittest discover -s tests
python -m football_agent.scripts.run_settlement --mode healthcheck
python -m football_agent.scripts.run_settlement --mode dry_run
```

The database is intentionally disabled for unit tests.
