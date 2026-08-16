
# Repository Instructions

每次提问后大模型的回答 -- 必须带有问候“主人”二字

window系统调用bash工具时--优先考虑git bash的终端 优先级：git bash > powershell > cmd 

## Layout And Entrypoints

- The active application is `python/` plus the optional `frontend/`; run Python commands from `python/` so imports resolve through `pytest.ini`/the package layout.
- The FastAPI entrypoint is `python/agent/app.py` (`agent.app:app`). Startup initializes `agent.runtime`, which owns the recommendation supervisor, repositories, tool registry, and main deep agent.
- `python/agent/recommend/` contains the v1 recommendation pipeline; `python/agent/main/` contains the v2 deepagents chat agent; `python/tools/` contains registered atomic tools; `python/skills/` contains `SKILL.md` documents loaded progressively by SkillsMiddleware.
- The root `CLAUDE.md` is the detailed architecture and historical decision reference; check it when changing orchestration, memory, tools, or skills.

## Setup And Commands

- Create the environment with `python -m venv .venv` and install backend dependencies with `python -m pip install -r python/requirements.txt`.
- Run the focused backend suite with `cd python; python -m pytest tests/test_file.py -v`; run the normal local suite with `python -m pytest tests/ -m "not slow" -v`.
- Coverage (`.coveragerc` present): `python -m pytest tests/ --cov --cov-report=term-missing`.
- `pytest.ini` enables strict markers and auto asyncio; use the declared markers `unit`, `integration`, `slow`, `agent`, and `api` rather than inventing new ones.
- Full or external-service tests may require LLM/database services; the `not slow` suite is the default verification target and mocks must avoid real LLM calls.
- Import course data from `python/` with `python scripts/ingest_course_dataset.py --limit 20` before a full `python scripts/ingest_course_dataset.py`; the CSV source is `course_dataset_tools/output/course.csv` (`public_elective_courses.csv` is its pre-rename name). Ingest strategy details for courses/handbook/transcript: `docs/v2.0.0/rag-ingest.md`.
- Offline evals: `python eval/runner.py --set <name>` (deterministic assertions; `--live` hits the running API, `--judge` adds LLM-as-judge); sets are `python/eval_sets/*.jsonl`, results land in `python/eval/reports/`.
- Build the frontend with `cd frontend; npm ci; npm run build`; there are no frontend lint or test scripts. Use a Node version allowed by `frontend/package.json` (engines: ^18.18 || ^20 || >=22). The dev server proxies `/api` to port 8000; override with `frontend/.env.local` `VITE_API_PROXY_TARGET`.

## Environment And Services

- Settings load the repository-root `.env` first and `python/.env` second, with the latter overriding the former; Docker injects only `python/.env`. Never commit credentials.
- Start dependencies and the API with `docker compose up -d`; after Python changes rebuild the API with `docker compose up -d --build python-api`.
- Docker maps MySQL host port `3307` to container port `3306`; application containers use service names and container ports. API is at `http://localhost:8000`, frontend dev server at `http://localhost:5173`.
- LLM and embedding configuration must be present for application startup: `app.py` refuses to boot without `LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`, and `EMBEDDING_PROVIDER` must be one of `local`/`openai`/`dashscope_multimodal` (local skips the embedding key check). If the provider has certificate/SAN problems, set `HTTPX_VERIFY_SSL=false` in the relevant env file and rebuild the container.

## Implementation Constraints

- Route all ChatOpenAI construction through `ai.llm_client.build_chat_openai`; do not instantiate `ChatOpenAI` directly. Preserve `LLMTaskName` run names where the caller uses them.
- `config.get_settings()` is `lru_cache`-backed. Tests should patch `config.get_settings` with a complete mock instead of changing environment variables after imports.
- Keep orchestration in `agent/`, atomic capabilities in `tools/`, and procedural skill instructions in `skills/`; tools are registered in `agent/runtime.py` before `build_main_agent()` runs.
- The main agent persists conversation checkpoints in SQLite and reads long-term memory from `python/memories/AGENTS.md`; do not confuse that runtime memory file with this repository instruction file.
- Redis caches candidate course IDs rather than full course objects; course facts still come from MySQL. Hard constraints are deterministic filtering before reranking, not a soft ranking preference.

## Frontend API Contract

- Any new or modified frontend-facing API must return a streaming response by default; use SSE or the repository's established streaming event protocol rather than adding a final synchronous JSON-only endpoint.
- The stream must expose meaningful progress/results events and always terminate with an explicit `done` event; failures must use a structured `error` event without silently ending the connection.
- Tests for frontend-facing APIs must consume the stream and assert event order, meaningful payloads, the terminal `done` event, and structured error behavior; a synchronous mock response alone is not sufficient validation.
- The frontend is Next.js (App Router) consuming the Python backend; `app/api/` is a reserved BFF proxy layer (future Java REST data service) — currently empty on purpose, frontend talks to Python via rewrites only, do not add real proxy logic there.

## Knowledge Base RAG

- The knowledge base is stored in Milvus `document_chunks` (schema with `user_id` partition key). Public knowledge (student handbook) uses `user_id=public`; personal data (transcript) uses per-user partitions and is only retrievable by the owner.
- Ingestion pipeline: parse (pypdf, pymupdf fallback for tables) → NFKC normalize → desensitize personal docs (name→`[姓名]`, student ID masked, class→grade, date→year; course names/credits/scores kept for owner queries) → recursive chunking (heading-aware + Chinese separators) → embed → upsert Milvus + MySQL metadata.
- Run `python scripts/ingest_student_handbook.py` from `python/` for the handbook (public); `python scripts/ingest_transcript_desensitized.py --user-id <id> --name <姓名>` for a personal transcript. `--embedding local` does a quota-free smoke test.
- Smoke-test KB answers end-to-end (needs a running API) with `python scripts/run_kb_test.py scripts/kb_test_transcript.json`; keyword hit/redact cases are in `kb_test_*.json`. The runtime upload path is `POST /api/v1/documents/upload` (multipart `file` + `dataset_name`, `chunk_strategy`), served by `agent/documents/service.py`.
- Re-ingestion is idempotent: `DocumentVectorRepository.delete_by_dataset` + `DocumentRepository.replace_chunks` replace the whole dataset, so old knowledge does not linger alongside new.
- Agents answer knowledge questions via the `query_knowledge` tool (retrieves `public + current user` partitions); answers must cite `source_doc_name`/`page_number` and must not fabricate when retrieval is empty.
- LangSmith RAG quality gates (context recall, faithfulness) are defined in `docs/v2.0.0/plan.md`; baselines require real end-to-end measurement before tuning top_k/chunking/rerank.

## User Context Injection

- The current request `user_id` is injected into the agent run via `agent.main.context.user_context()` (ContextVar) — `/api/v1/chat` and `/api/v1/chat/stream` wrap the agent call with it and also put `user_id` in `configurable`.
- Tools that need the current user MUST read it from `agent.main.context.get_current_user_id()`; never rely on the LLM guessing `user_id` from conversation, and never add `user_id` to a tool's `args_schema`.
- `query_knowledge` (personal transcript partition) and `recommend_courses` (personalized recommendation) already follow this pattern; any future personalization/authz tool must do the same.
- Direct endpoints like `/api/v1/recommend/stream` still accept structured `user_id` explicitly (bypass chat).
