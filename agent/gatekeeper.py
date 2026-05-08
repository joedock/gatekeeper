"""Gatekeeper — kernel telemetry threat-hunting agent.

Multi-turn investigation loop:
1. Fetch recent process activity from ClickHouse.
2. Identify anything anomalous; if nothing, emit CleanRun and exit.
3. Drill into specifics with follow-up tool calls.
4. After investigation, emit a structured Finding.

Run on host with kubectl port-forward active:
    kubectl -n telemetry port-forward svc/clickhouse-service 8123:8123 &
    LLM_BACKEND=ollama python -m agent.gatekeeper
"""

import json
import os
import sys
import time
from typing import Any

from .backends import get_backend
from .clickhouse_tools import TOOL_FUNCTIONS, TOOL_SCHEMA
from .findings import CleanRun, Finding

MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "10"))
LOOP_SLEEP_SECONDS = int(os.environ.get("AGENT_SLEEP_SECONDS", "60"))

SYSTEM_PROMPT = """You are Gatekeeper, an autonomous threat-hunting agent for a Kubernetes cluster.

You have read-only access to a ClickHouse database (`process_telemetry`) containing
process_exec events captured by Tetragon (eBPF). Each row is a single binary
execution: when, where (namespace + pod), what binary, what arguments, and what
parent process spawned it.

Your job each cycle:
1. Pull recent activity using `query_recent_executions`.
2. Look for anomalies: suspicious binaries (curl piped to sh, base64 decoders
   followed by exec, reverse shells, crypto miners, post-exploit tools like
   nsenter/socat in non-system pods), unexpected parent-child chains, or
   binaries appearing in pods where they don't belong.
3. If something stands out, drill in with `query_pod_activity` or
   `query_binary_history` — investigate before concluding.
4. After your investigation, output a SINGLE JSON object as your final response
   — nothing else, no markdown, no preamble.

Final output schema (when something is suspicious):
{
  "type": "finding",
  "severity": "info|low|medium|high|critical",
  "summary": "one-sentence headline",
  "affected_pod": "pod-name or null",
  "suspicious_binary": "/path/to/bin or null",
  "parent_chain": ["/usr/bin/parent", "/usr/bin/child"],
  "reasoning": "specific data points you saw",
  "suggested_action": "what an analyst should check next"
}

Final output schema (when everything looks clean):
{
  "type": "clean",
  "reasoning": "what you looked at and why it's normal",
  "queries_run": <number>
}

Rules:
- Be specific. Reference actual binaries and pod names you saw.
- Do not output text outside the final JSON. The orchestrator parses your output.
- If unsure, classify as 'low' or 'info' — don't cry wolf.
- Most cluster activity is legitimate (kubelet, containerd, system daemons).
  Don't flag normal Kubernetes operations.
"""


def _run_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Dispatch a tool call to the matching ClickHouse function."""
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return f"ERROR: unknown tool '{name}'"
    try:
        return fn(**arguments)
    except TypeError as e:
        return f"ERROR: bad arguments for {name}: {e}"
    except Exception as e:  # noqa: BLE001 - tool error must not crash agent
        return f"ERROR: tool {name} raised: {e}"


def _parse_final_output(text: str) -> Finding | CleanRun | None:
    """Extract the JSON object from the model's final response."""
    text = text.strip()
    # Some models wrap JSON in ```json fences despite instructions.
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if data.get("type") == "finding":
        data.pop("type", None)
        return Finding(**data)
    if data.get("type") == "clean":
        data.pop("type", None)
        return CleanRun(**data)
    return None

def run_investigation() -> Finding | CleanRun | None:
    """One end-to-end investigation cycle. Returns the structured finding."""
    backend = get_backend()
    print(f"[gatekeeper] backend={backend.name} max_turns={MAX_TURNS}")

    messages: list[dict] = [
        {
            "role": "user",
            "content": "Begin a threat-hunting cycle. Investigate recent activity "
            "and report your findings. You have a STRICT BUDGET of 3 tool calls "
            "before you must output your final JSON conclusion. Use them wisely.",
        }
    ]
    queries_run = 0
    last_tool_signature: str | None = None
    forced_conclusion_sent = False

    for turn in range(1, MAX_TURNS + 1):
        print(f"[gatekeeper] turn {turn}/{MAX_TURNS} (queries_run={queries_run})...")
        response = backend.chat(
            messages=messages,
            tools=TOOL_SCHEMA,
            system=SYSTEM_PROMPT,
            max_tokens=2048,
        )

        if response.tool_calls:
            # Loop detection: same tool with effectively the same intent twice
            # in a row is the model spinning, not investigating.
            tc = response.tool_calls[0]
            sig = tc.name
            if sig == last_tool_signature and queries_run >= 2:
                print(f"[gatekeeper] loop detected: {sig} called repeatedly. "
                      "Forcing conclusion.")
                messages.append({
                    "role": "user",
                    "content": "STOP investigating. You have enough data. "
                    "Output ONLY your final JSON object now, with no other text.",
                })
                forced_conclusion_sent = True
                continue
            last_tool_signature = sig

            # Hard budget cap: after 3 queries, force conclusion
            if queries_run >= 3 and not forced_conclusion_sent:
                print("[gatekeeper] budget exhausted. Forcing conclusion.")
                messages.append({
                    "role": "user",
                    "content": "Your tool-call budget is spent. "
                    "Output ONLY your final JSON object now, with no other text.",
                })
                forced_conclusion_sent = True
                continue

            # Normal tool execution path
            messages.append({
                "role": "assistant",
                "content": response.text,
                "tool_calls": [
                    {
                        "id": tc.call_id,
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in response.tool_calls
                ],
            })
            for tc in response.tool_calls:
                print(f"[gatekeeper] tool: {tc.name}({tc.arguments})")
                result = _run_tool_call(tc.name, tc.arguments)
                queries_run += 1
                print(f"[gatekeeper] result preview: {result[:200]}...")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.call_id,
                    "content": result,
                })
            continue

        # No tool calls — model is done; parse final output
        parsed = _parse_final_output(response.text)
        if parsed is None:
            print(f"[gatekeeper] could not parse model output:\n{response.text}")
            return None
        return parsed

    print(f"[gatekeeper] hit max turns ({MAX_TURNS}) without final answer")
    return None


def main() -> int:
    print("[gatekeeper] starting investigation daemon")
    while True:
        print("\n" + "=" * 60)
        print(f"[gatekeeper] cycle start at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            result = run_investigation()
            if result is None:
                print("[gatekeeper] investigation produced no parseable result")
            else:
                print("\n[gatekeeper] FINAL RESULT:")
                print(result.model_dump_json(indent=2))
        except Exception as e:  # noqa: BLE001
            print(f"[gatekeeper] ERROR: {type(e).__name__}: {e}")
        print(f"[gatekeeper] sleeping {LOOP_SLEEP_SECONDS}s...")
        time.sleep(LOOP_SLEEP_SECONDS)


if __name__ == "__main__":
    sys.exit(main() or 0)
