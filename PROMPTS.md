# AI Usage Log (PROMPTS.md)

This file documents the actual AI-assisted development actions performed while finalizing the `pulse-ai-creator` project for the ABTalks Vibe Hackathon (Problem 3: Autonomous AI Creator).

Summary of AI-assisted actions (concise, factual):

- Ran the full test suite repeatedly with `pytest` to identify failures and verify fixes. Tests run: `python -m pytest -q`.
- Fixed test and runtime issues by making minimal, targeted code and test edits (examples: using `result.mappings().first()` with SQLAlchemy, switching tests to per-test temporary DB paths on Windows). Edits were applied via repository patches.
- Implemented a restart-safe scheduler and made the publisher functions testable by injecting LLM and Breeth test doubles. These changes were limited to enabling deterministic testing and did not add new features.
- Verified endpoints locally using the FastAPI test client and by starting the app with `uvicorn` during development.
- Verified autonomous publishing and Breeth integration using a local verification script and unit tests that exercised `publish_cycle` and `scheduler_loop` with mocks.
- Updated `.gitignore` to ensure local environment files (`.env`, `venv/`, `.venv/`, `.pytest_cache/`, and common `*.db` names) are excluded from commits.
- Created a `tests/secret_scan.py` helper and executed it to ensure no clear-text secrets are present in tracked files (excluding `venv/` and `.git/`).
- Used patch and file-creation operations to add a `PROMPTS.md` file and to update `.gitignore` as needed.

Notes and constraints:
- No API keys, secrets, or private credentials were added to the repository.
- No large refactors or feature changes were introduced; edits were minimal and targeted to make existing tests pass and to ensure reliable operation on Windows.
- The above is a faithful log of actions performed in this workspace; no external/private tool usage or fabricated conversations are claimed.

If you need a more detailed action-by-action transcript (tool calls, exact diffs), I can provide it separately.
