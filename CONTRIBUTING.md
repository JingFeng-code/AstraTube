# Contributing

Thanks for taking a look. This is a small project — issues and PRs are both welcome.

## Getting set up

```bash
git clone https://github.com/<you>/youtube-card-reader.git
cd youtube-card-reader
./scripts/start.sh          # installs everything on first run, then starts both servers
```

Backend runs on `127.0.0.1:8420`, frontend on `127.0.0.1:15273`. Override with
`YCR_BACKEND_PORT` / `YCR_FRONTEND_PORT`.

To work on the two halves separately:

```bash
cd backend  && ./.venv/bin/python -m uvicorn app.main:app --reload --port 8420
cd frontend && npm run dev
```

## Running the tests

No test needs the network or an API key — everything external is injected.

```bash
cd backend
./.venv/bin/python tests/test_deepsrt.py
./.venv/bin/python tests/test_progress_stream.py
./.venv/bin/python tests/test_providers.py
```

They are also pytest-compatible (`pytest tests`) and run in CI on every push.

## Adding an AI engine

Most engines speak the OpenAI Chat Completions protocol, so adding one is a
table entry rather than a new file:

1. Add a `Vendor(...)` in `backend/app/llm/openai_compat.py` and register it in
   `VENDORS`.
2. Add the config key to `_FIELDS` in `backend/app/core/config.py` and to
   `_KEY_FIELDS` in `backend/app/api/settings.py`.
3. Add the field to `SettingsUpdate` in `backend/app/models/schemas.py`.
4. Add the provider to `PROVIDER_ORDER` in `frontend/src/hooks/useModels.js`,
   the `ENGINES` list in `SettingsModal.jsx`, and the two label/hint strings in
   `frontend/src/i18n/strings.js`.

An engine with its own SDK or wire format gets its own module instead — see
`backend/app/llm/anthropic_api.py` for the shape, then wire it into
`backend/app/llm/router.py`.

## Adding a UI language

Add one entry to `STRINGS` in `frontend/src/i18n/strings.js` and one to `LANGS`
at the top of that file. Any key you leave out falls back to English, so a
partial translation is still useful.

## Adding a card output language

Add a `Language(...)` row to `LANGUAGES` in `backend/app/core/languages.py`.
The prompt bodies stay in Traditional Chinese on purpose (they are calibrated
against real output and translating them changes quality); each language row
supplies a hard "write in this language" directive that is prepended to every
prompt. `tests/test_providers.py` checks that every language reaches all four
prompts.

## Style

- Python: standard library formatting, type hints on public functions, comments
  in the codebase's existing voice — explain *why*, not *what*.
- JavaScript: no formatter is enforced; match the surrounding file.
- Commit messages: plain imperative ("Add DeepSeek provider").
