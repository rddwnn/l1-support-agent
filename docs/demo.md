# Demo guide

## Prerequisites

| Requirement | Check |
|---|---|
| Python 3.13+ and `uv` | `uv --version` |
| Ollama for the built-in harness | `ollama --version` |
| Public MockAPI reachable | inspect the read-only dataset |
| Telegram/GitHub credentials | not required for the default safe demo |

## Prepare a disposable runtime

```bash
uv sync
cp .env.example .env
# Edit .env without committing it.
set -a
source .env
set +a
export SUPPORT_DB_PATH=/tmp/l1-support-agent-demo.db
export SUPPORT_SIDE_EFFECT_MODE=mock
```

`mock` is the safe default. It exercises real LLM routing, MCP calls, built-in authorization, result validation, and Case transitions, but the final Telegram/GitHub adapters are deterministic and network-free. The application reads exported environment variables; it does not parse `.env`.

Start Ollama in another terminal and ensure the configured model exists:

```bash
ollama serve
ollama pull "${LLM_MODEL:-qwen3.5:4b}"
```

## Seed the synthetic KB

```bash
uv run python -m l1_support_agent.demo_kb
```

Run this seed before Scenario A. It idempotently writes one synthetic bilingual POST/beep hardware article through `KnowledgeRepository`, including its FTS5 row. Retrieval is lexical SQLite FTS5, not semantic or vector search, so the fixture contains natural English terms (`computer`, `beeps`, `startup`, `boot`, `POST`, `RAM`) and the matching Russian ticket vocabulary.

## Scenario matrix

| Scenario | Input | Business capability calls | Final state | Visible evidence |
|---|---|---|---|---|
| A — known KB issue | hardware POST/beep ticket | `get_ticket`, `search_kb` | `RESOLVED` | answer grounded in seeded article |
| B — infrastructure | real outage with no adequate article | `get_ticket`, `search_kb`, `escalate_l2` | `ESCALATED_L2` | deterministic mock `message_id` |
| C — software defect | real defect with no adequate article | `get_ticket`, `search_kb`, `create_github_issue` | `ESCALATED_DEVELOPMENT` | URL under `mock.invalid` |
| Learning | escalated Case + verified resolution | no MCP calls | Case unchanged | learning status + article ID |

## Inspect source tickets

The dataset can change. Read it through the capability plane or inspect the public read-only endpoint; never mutate it.

```bash
curl -fsS https://6a7ad74c8c69b3eb4a179621.mockapi.io/tickets/tickets
```

At the time of writing, local smoke work used ticket `1` for the POST/beep scenario. Verify its current fields. Skip any scenario without a defensible source ticket.

## Scenario A — known solution

```bash
uv run l1-support-agent process 1
```

Expected JSON:

- populated `category` and `priority`;
- `final_state` equal to `resolved`;
- `outcome_message` grounded in the seeded article.

Run the same command again. The deterministic Case ID and state must match, and the persisted terminal Case must bypass another agent run.

## Scenario B — L2 escalation

In default mock mode this is safe and requires no Telegram credentials.

```bash
uv run l1-support-agent process INFRASTRUCTURE_TICKET_ID
```

Expected evidence:

- the LLM selects `escalate_l2` from the ticket and empty/inadequate KB result;
- MCP returns a deterministic positive mock `message_id` without network access;
- the Case reaches `ESCALATED_L2` only after an integer `message_id` is returned;
- rerunning the terminal Case performs no second escalation.

## Scenario C — development escalation

In default mock mode this is safe and requires no GitHub credentials.

```bash
uv run l1-support-agent process SOFTWARE_TICKET_ID
```

Expected evidence:

- the LLM selects `create_github_issue` from an actual software defect;
- MCP returns a deterministic URL under `https://mock.invalid/` without network access;
- the Case reaches `ESCALATED_DEVELOPMENT` only after a non-empty issue URL is returned;
- rerunning the terminal Case performs no second escalation.

## Optional real integrations

Only opt in when actual external writes are intended:

```bash
export SUPPORT_SIDE_EFFECT_MODE=real
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
export GITHUB_TOKEN=...
export GITHUB_REPOSITORY=owner/repository
```

Real mode preserves the production adapters and does not fall back to mock. Missing credentials fail clearly. Re-run only the scenario whose external destination you have verified.

## Explicit self-learning

Use a resolution verified outside L1:

```bash
uv run l1-support-agent learn CASE_UUID \
  --resolution "Verified factual resolution supplied by L2 or development"
```

| Status | Meaning |
|---|---|
| `created` | stable learned article written to KB and FTS5 |
| `already_exists` | this Case was learned before; no LLM call |
| `covered_by_existing` | a retrieved article already covers the resolution; no write |

Ordinary `RESOLVED` and non-terminal Cases are not eligible.

## REST transport

```bash
uv run uvicorn l1_support_agent.api:app --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/health
curl -fsS -X POST http://127.0.0.1:8000/tickets/1/process
curl -fsS -X POST http://127.0.0.1:8000/cases/CASE_UUID/learn \
  -H 'Content-Type: application/json' \
  -d '{"verified_resolution":"Verified factual resolution"}'
```

CLI and REST use the same composition functions in `interfaces.py`.

## No-side-effect MCP interoperability smoke

This starts the real stdio server as a child, initializes a disposable DB, and only discovers tools. It does not call MockAPI, Telegram, or GitHub.

```bash
SUPPORT_DB_PATH=/tmp/l1-support-agent-mcp-smoke.db uv run python - <<'PY'
import asyncio
from l1_support_agent.interfaces import RuntimeConfig, build_mcp_server_parameters
from l1_support_agent.mcp.client import connect_stdio_mcp

async def main() -> None:
    config = RuntimeConfig.from_env()
    async with connect_stdio_mcp(build_mcp_server_parameters(config)) as client:
        names = sorted(tool.name for tool in await client.list_tools())
        print(", ".join(names))

asyncio.run(main())
PY
```

The discovered set must contain exactly these names; ordering is not part of the MCP contract:

```text
create_github_issue, escalate_l2, get_ticket, list_tickets, search_kb
```

After seeding the DB, a harness may also call `search_kb`; that operation is read-only. Do not call escalation tools during an interoperability smoke.

## Safe local reset

Only remove the exact disposable paths selected above:

```bash
rm -f /tmp/l1-support-agent-demo.db \
      /tmp/l1-support-agent-demo.db-shm \
      /tmp/l1-support-agent-demo.db-wal \
      /tmp/l1-support-agent-mcp-smoke.db
```

Deleting SQLite files cannot undo Telegram messages or GitHub issues.
