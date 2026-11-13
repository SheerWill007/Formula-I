# Pitwall agent

Pitwall is an optional conversational F1 analyst exposed by the Flask API. It
combines language-model planning and writing with deterministic, read-only
tools for retrieving session facts and computing analysis.

## Request flow

1. The agent API authenticates the user with Clerk, applies usage limits, and
   loads conversation context.
2. The router classifies the request and extracts entities such as race,
   driver, lap, and session type.
3. A template or validated LLM planner selects registered tools and builds a
   dependency graph. The default is `AGENT_PLANNER_MODE=template`.
4. The executor runs typed tools. Tools query PostgreSQL with parameterized SQL
   and fetch permitted artifacts through the configured storage adapter.
5. Evidence is verified and composed into a response. The streaming endpoint
   sends progress and answer events to the client.

Relevant implementation: `apps/backend/src/backend/api/v1/agent.py` and
`apps/backend/src/backend/agent/`.

## Evidence and safety

- The model can choose among registered tools; it cannot write SQL, run shell
  commands, browse arbitrary URLs, or call unregistered tools.
- Tools are read-only and return typed inputs/outputs. SQL remains in Python
  and uses bound parameters.
- Numerical answers must be grounded in tool output. Missing data should be
  reported as missing; retrieved documents do not replace telemetry evidence.
- Vector search is limited to approved strategy documents. Session availability
  and numeric race data are queried from PostgreSQL or artifacts.
- Personal profile and chat-embedding memory are not retained. Conversation
  history and run/tool records are persisted for the chat and usage features;
  they are distinct from personal memory.

## LLM provider and keys

Language-model calls go through the OpenRouter-compatible adapter in
`agent/llm.py`. Configure `OPENROUTER_API_KEY` and, if needed,
`OPENROUTER_BASE_URL`, `OPENROUTER_ROUTING_MODEL`, `OPENROUTER_FINAL_MODEL`,
and `OPENROUTER_CAPABLE_MODEL`. The configured default model is
`openai/gpt-4o-mini`; billing and available model access are determined by the
OpenRouter account. Without the key, the agent's model-dependent requests fail
with a configuration error. The core analytics do not use this key.

Embeddings use `EMBEDDING_PROVIDER`, `EMBEDDING_API_KEY`,
`EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, and `EMBEDDING_DIMENSIONS`. The default
endpoint is OpenAI's embeddings API, so a valid key is needed for remote
embeddings. Development and tests can use the deterministic local hash
embedding fallback when no embedding key is configured. Production document
retrieval also needs Cloudflare account, Vectorize token, and index settings.

Never put provider keys in frontend variables or commit them. Configure them
as backend environment secrets. Check provider pricing and the deployment's
usage limits before enabling agent access for users.

## Main building blocks

- `types.py`: typed intent, tool, and evidence contracts.
- `tools.py`: deterministic session, telemetry, strategy, and source tools.
- `planner.py`, `agentic_loop.py`: plan validation and dependency execution.
- `orchestrator.py`: routing, tool execution, verification, and synthesis.
- `llm.py`: OpenRouter-compatible completion and streaming adapter.
- `semantic_cache.py`: in-process response cache; it is not persistent user
  memory.
- `strategy_documents.py`, `vector_store.py`: approved-source ingestion and
  retrieval adapters.
- `persistence.py`, `rate_limit.py`: conversations, run traces, feedback, and
  usage controls.
- `nodes/`: compute, critic, and synthesis steps used by the orchestrator.

## Configuration reference

| Setting | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Required for model calls |
| `AGENT_PLANNER_MODE` | `template` by default; `llm` enables LLM DAG planning |
| `AGENT_FREE_DAILY_LIMIT` | Per-user daily run limit |
| `AGENT_FREE_DAILY_COST_USD` | Per-user estimated daily model-cost limit |
| `EMBEDDING_API_KEY` | Optional remote embedding provider key |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_VECTORIZE_API_TOKEN`, `CLOUDFLARE_VECTORIZE_INDEX` | Production strategy-source search |
| `CLERK_ISSUER` | Clerk JWT issuer for protected agent routes |

Names above map to the settings fields in
`apps/backend/src/backend/config.py` (the environment loader accepts the
corresponding uppercase forms). Configure other service settings in the backend
environment as needed.

## Tests

Run focused agent tests from the repository root:

```bash
uv run --project apps/backend python -m pytest apps/backend/tests/agent
```

When testing API or persistence behavior, use local Postgres and configure any
provider calls through test doubles rather than live credentials.
