# AI Usage Log & Prompt History (PROMPTS.md)

This log documents the interactive prompt history and development workflow used to build and refine the PULSE Autonomous AI Tech Creator backend and frontend integration.

AI coding tools and LLMs were used at every stage of development to design, implement, debug, and document the system. Below is the historical sequence of development prompts.

---

## 1. Project Initialization Prompt
> "Initialize a new FastAPI application for a hackathon project named 'PULSE' (Autonomous AI Creator). Set up a clean directory structure with `app/` containing the source files and `tests/` for automated testing. Use `pyproject.toml` or `requirements.txt` for package management with Pydantic, SQLAlchemy, and HTTPX. Ensure database configuration supports SQLite."

## 2. Backend Architecture Prompt
> "Design the SQLAlchemy schema for the backend. We need:
> - An `agents` table storing agent UUID, persona name, persona domain, created timestamp, next publish scheduled time, last publish time, and total published count.
> - A `posts` table storing unique post UUID, agent ID, text content, editorial rationale, 'why now' description, sources (list of strings), and topic meta-data (source, URL, published timestamp).
> - A `rejection_records` table to log rejected topics and editorial rejection reasons for debugging and transparency.
> Ensure database helper functions initialize the tables and return async session contexts using `aiosqlite`."

## 3. Autonomous Scheduler Prompt
> "Create a robust, restart-safe background scheduler loop in `app/scheduler.py` that polls the database every 10 seconds.
> - It should find agents whose `next_publish_at` is in the past.
> - Use atomic updates or state locking (e.g. updating `last_cycle_started_at`) to claim agents safely and prevent duplicate parallel execution.
> - When an agent is claimed, call the publication cycle, catch any exceptions gracefully, and advance the agent's scheduled publication time by `publish_interval_minutes`."

## 4. Topic Discovery Prompt
> "Implement `app/topic_discovery.py`. Create a prompt for the LLM instructing it as the persona 'PULSE' to discover 5 timely, production-relevant developments in AI engineering (such as RAG, agents, optimizations, devtools). The LLM must output clean JSON with keys `title`, `summary`, `url`, `publishedAt`, and `source`."

## 5. Editorial Judgment Prompt
> "Write `app/editorial.py`. It should feed the discovered candidate topics to the LLM along with the agent's persona. The LLM must choose at most one publication-worthy topic and reject others, outputting JSON with `selected_index`, a `decision_reason`, and a list of rejection reasons. If a topic is redundant or low-signal, it should be rejected."

## 6. Memory/Breeth Integration Prompt
> "Create `app/breeth_client.py` to connect with the Breeth vector memory service.
> - Before choosing a topic for publication, perform a semantic search query in Breeth for the topic's title to ensure PULSE does not repeat itself.
> - Once a post is successfully generated, index it into Breeth as a new episode in the agent's memory group so that it is included in future semantic search checks."

## 7. Gemini Migration/Debugging Prompt
> "The hackathon sandbox is switching from OpenAI to Gemini. We need to update `app/llm_client.py` to route calls to the Generative Language API (`models/gemini-3.5-flash:generateContent`). Ensure query parameters (`?key=...`) and Bearer authentication are supported. Keep client signatures identical so that `discover_topics`, `judge_topics`, and `publish_cycle` continue to work without modification."

## 8. Gemini Response Parsing/Debugging Prompt
> "We are getting the error `LLMClientError: Unable to extract text from Gemini content`.
> - Inspect `LLMClient._extract_text()` and fix it so it parses the Gemini structure `candidates[0].content.parts[].text` successfully.
> - Ensure it ignores metadata keys like `thoughtSignature` but preserves fallback parsing for raw strings, flat dicts, nested contents, and lists.
> - Strip any markdown code blocks (e.g. ` ```json ... ``` `) from the final returned text so that subsequent `json.loads` calls in the application do not crash.
> - Set `"thinkingConfig": {"thinkingBudget": 0}` in the Gemini generation config and increase `maxOutputTokens` to `4096` to prevent the thinking process from consuming the token budget and truncating the output JSON."

## 9. Testing/E2E Verification Prompt
> "Write automated unit tests for `llm_client`, `publisher`, and API endpoints using `pytest` and `fastapi.testclient`.
> Create a comprehensive end-to-end verification script `temp_e2e.py` that starts the app, manually triggers agent initialization, runs the scheduler, checks that a post is generated, and queries the feed."

## 10. Frontend Integration Prompt
> "Verify that FastAPI CORS middleware is configured correctly. Import `CORSMiddleware` and configure it in `app/main.py` using `settings.frontend_origin`. Ensure local web applications (such as a Lovable UI on localhost) can query `POST /api/agent/init` and `GET /api/agent/feed` without cross-origin policy blocks."

## 11. Final Documentation/Submission Prompt
> "Write a clean, markdown-formatted `README.md` containing the project overview, architecture diagram, api contracts, local environment setup, and instructions for running backend and frontend tests."
