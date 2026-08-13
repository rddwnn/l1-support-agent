# Design decisions

| Decision | Why chosen | Alternative rejected | Consequence |
|---|---|---|---|
| Bounded single-agent runtime | One model can triage and route the three required outcomes; a step limit prevents loops | Multi-agent framework | Less orchestration code; no specialist-agent handoffs |
| MCP as the company capability plane | The built-in harness or any stdio MCP-compatible harness can reuse the same ticket, KB, Telegram, and GitHub capabilities | Keep MCP as an internal agent-loop adapter or call integrations ad hoc | Capability schemas and execution are portable; consumers choose their orchestration |
| Built-in policy outside MCP | Capability discovery and Case-aware authorization are different concerns | Enforce the built-in Case lifecycle inside the reusable server | Our harness applies deterministic sequencing; external harnesses must own an equivalent policy |
| Deterministic Python validation around LLM output | Tool calls, article IDs, structured fields, and side-effect results require explicit checks | Trust model output because it matches a schema | Malformed or invented outcomes fail before state transition |
| State machine separate from tool policy | Lifecycle legality and capability permission answer different questions | Put tool names in transition table | Domain remains stable as MCP capabilities evolve |
| SQLite + FTS5 | Small local deployment, transactional repositories, built-in full-text retrieval | Vector database | Simple setup; lexical search only |
| Explicit learning from verified resolution | Telegram/GitHub do not provide solved-case callbacks; caller supplies trusted facts | Automatic learning after escalation | No speculative KB writes; an external/human step is required |
| Skills as packaged Markdown instructions | Behavior is reviewable and reusable without executable plugins | Prompt prose scattered through Python or framework plugin system | Skills guide the LLM but cannot grant tools or mutate state |
| Structured post-KB routing with `tools=[]` | Separates outcome selection from side-effect execution | Let the model directly call escalation tools | Python supplies trusted ticket fields and rechecks permission before MCP execution |
| Deterministic Case and learned-article IDs | Makes repeated ticket processing and learning idempotent | Random UUID on every invocation | Terminal reruns do not duplicate side effects or KB rows |
