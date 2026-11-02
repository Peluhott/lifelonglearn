---
name: check
description: Verify changes to the tutor backend/frontend offline (compile, import the graph and API, lint the frontend) without calling Gemini. Use after editing Python or frontend code.
---

Run from the repo root. Report each step's result; stop and report on the first failure.

1. Compile: `.venv/bin/python -m compileall -q main.py api tutor`
2. Build the graph (imports every node and loads every prompt, no API calls): `.venv/bin/python -c "import tutor.graph"`. A `LangSmithBetaWarning` about `wrap_gemini` is expected.
3. Import the API: `.venv/bin/python -c "import api.main"`
   - If this fails with `ModuleNotFoundError: fastapi` (or uvicorn), say the venv is out of date and suggest `.venv/bin/pip install -r requirements.txt` — don't count it as a code failure.
4. Tests (offline, Gemini is mocked): `.venv/bin/python -m pytest -q -p no:warnings`
5. If anything under `frontend/` changed: if `frontend/node_modules` exists, run `cd frontend && npm run lint`; otherwise note that `npm install` is needed to lint.
6. Live run — **only if the user explicitly approves**, since it spends Gemini credits:
   `printf '%s\n' "<short prompt>" | .venv/bin/python main.py`
   Offer this at the end; never run it on your own.
