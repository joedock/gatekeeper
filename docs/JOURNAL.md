## Day 1 (2026-05-08)
- ClickHouse deployed to telemetry ns with 20Gi PVC
- process_telemetry table created from sql/001_process_telemetry.sql
- Cross-namespace DNS verified (gatekeeper → telemetry)
- Decision: dropped istio, no value for this project
- Decision: telemetry/gatekeeper namespace split for clean lifecycle separation


## Day 2 — Pipeline Live (with a known limitation)

Stack from kernel to OLAP is end-to-end working. Tetragon → Vector → ClickHouse 
ingesting at ~150 events/min during normal cluster activity, and the agent will be
able to query process_exec events for any pod with stable enrichment.

### Known limitation: short-lived host-namespace events

Tetragon 1.2 on Linux kernel 6.17 (Ubuntu OEM) can't reliably attach pod metadata
to processes that exec-and-exit faster than its asynchronous K8s pod-info cache
can warm up. Symptoms:
- Events fire correctly (verified via `tetra getevents`)
- Long-lived pods (clickhouse, vector, tetragon) enrich correctly
- Short-lived processes (busybox `id`, `whoami`) land with namespace="host"

The fix in 1.2 — `enable-cgidmap=true` — requires custom kprobe BPF programs that
fail to load on kernel 6.17 (`bpf_multi_kprobe_v61.o ... load program: invalid argument`).
A newer Tetragon (>=1.3) or kernel-matched build is the proper fix.

### Why we're moving on

For the gatekeeper agent's threat-hunting use case, the relevant pivots are
process_binary, process_arguments, and parent_process — all enriched correctly.
Namespace attribution can be reconstructed at query time via cgroup ID joins
in week 4 if needed. Documenting the limitation now rather than blocking week 1.

### Debugging story (for future-me / interview retell)

What looked like four different problems was actually a chain:
1. Default Helm install emits no exec events. (Need denylist override.)
2. Default denylist excludes host, cilium, kube-system. (Override that.)
3. Custom TracingPolicies fail to load on kernel 6.17. (Don't need them; base sensor is enough.)
4. Pod metadata enrichment races short-lived processes. (Documented limitation.)

Lesson: when telemetry looks broken, instrument from both ends —
`tetra getevents` (source-side) and `SELECT count()` (sink-side) — before
changing config. Saved hours once we did.

## Day 3 — Agent loop live

The gatekeeper agent is now end-to-end:
- Pluggable LLM backend (Ollama implemented, Anthropic stubbed)
- Multi-turn investigation loop with 3-query budget cap and loop detection
- Three ClickHouse tools: query_recent_executions, query_pod_activity, 
  query_binary_history
- Structured output via Pydantic models (Finding | CleanRun)

### What worked first try
- Tool schema fired correctly with gemma4:e4b
- ClickHouse queries via port-forward returned PrettyCompact tables
- Pydantic parsing of model output

### What needed iteration
gemma4:e4b at 8B doesn't naturally converge — it kept calling the same tool
with slightly different parameters indefinitely. Fixed with two prompt-engineering
patterns:
1. Explicit tool-call budget in the initial user message ("You have 3 calls")
2. Loop detection in the agent code — same-tool-twice triggers a forced-conclusion
   user message

### Open observations
- Initial cycle returned a CleanRun, which is correct (the cluster IS clean)
- Need a red-team workload (day 4) to validate the agent CAN detect actual badness
- Pod metadata enrichment limitation from day 2 still applies — agent sees
  namespace="host" for short-lived processes
