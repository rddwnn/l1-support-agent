# Design decisions

| Decision | Why chosen | Alternative rejected | Consequence |
|---|---|---|---|
| Bounded single-agent runtime | One model can triage and route the three required outcomes; a step limit prevents loops | Multi-agent framework | Less orchestration code; no specialist-agent handoffs |
| MCP for operational capabilities | Gives provider-neutral tool metadata and a single stdio boundary | Direct ad hoc calls from the agent loop | MCP server owns transport adapters; runtime still owns authorization |
| Deterministic Python validation around LLM output | Tool calls, article IDs, structured fields, and side-effect results require explicit checks | Trust model output because it matches a schema | Malformed or invented outcomes fail before state transition |
| State machine separate from tool policy | Lifecycle legality and capability permission answer different questions | Put tool names in transition table | Domain remains stable as MCP capabilities evolve |
| SQLite + FTS5 | Small local deployment, transactional repositories, built-in full-text retrieval | Vector database | Simple setup; lexical search only |
| Explicit learning from verified resolution | Telegram/GitHub do not provide solved-case callbacks; caller supplies trusted facts | Automatic learning after escalation | No speculative KB writes; an external/human step is required |
| Skills as packaged Markdown instructions | Behavior is reviewable and reusable without executable plugins | Prompt prose scattered through Python or framework plugin system | Skills guide the LLM but cannot grant tools or mutate state |
| Structured post-KB routing with `tools=[]` | Separates outcome selection from side-effect execution | Let the model directly call escalation tools | Python supplies trusted ticket fields and rechecks permission before MCP execution |
| Deterministic Case and learned-article IDs | Makes repeated ticket processing and learning idempotent | Random UUID on every invocation | Terminal reruns do not duplicate side effects or KB rows |
