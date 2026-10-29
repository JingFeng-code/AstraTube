# Agent development rules

- Keep React + FastAPI as the existing architecture for Phase 0. No Vue/.NET rewrite unless explicitly requested.
- Code comments and end-user documentation should be clear Traditional Chinese (Taiwan conventions).
- Preserve the root MIT LICENSE, source attribution and third-party notices.
- Do not commit API keys, .env, settings.json, credentials, subtitles from private videos, or generated artifacts.
- Do not auto-run shell commands derived from video/transcript text; require explicit user approval.
- Use official YouTube embed/player interfaces. Respect media rights and platform terms.
- Prioritize minimum incremental changes with tests. Keep backend and frontend CI green.
- New features (Ollama, real-time bilingual subtitles, VideoToNo) are planned, not yet implemented. Never describe them as available prematurely.
