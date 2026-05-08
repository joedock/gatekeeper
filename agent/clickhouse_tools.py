"""ClickHouse query tools exposed to the LLM.

Each function corresponds to a tool the agent can call during an
investigation. Functions return human-readable strings (PrettyCompact
table format) because that's what LLMs reason about best — they're
optimized for text, not parsed structures.

Connection target is configurable via CLICKHOUSE_URL env var.
Default assumes `kubectl port-forward -n telemetry svc/clickhouse-service 8123:8123`
is running on the host.
"""

import os

import requests

CLICKHOUSE_URL = os.environ.get("CLICKHOUSE_URL", "http://localhost:8123")
QUERY_TIMEOUT_SECONDS = 10


def _query(sql: str) -> str:
    """Execute SQL against ClickHouse and return PrettyCompact-formatted text."""
    formatted = f"{sql} FORMAT PrettyCompact"
    try:
        resp = requests.post(
            CLICKHOUSE_URL, data=formatted, timeout=QUERY_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        text = resp.text.strip()
        return text if text else "Query returned no rows."
    except requests.exceptions.Timeout:
        return f"Query timed out after {QUERY_TIMEOUT_SECONDS}s."
    except requests.exceptions.RequestException as e:
        return f"ClickHouse query error: {e}"


def query_recent_executions(minutes: int = 5, limit: int = 50) -> str:
    """Return the most recent process exec events across the cluster.

    Args:
        minutes: Look-back window in minutes (1 to 60).
        limit: Max rows to return (1 to 200).
    """
    minutes = max(1, min(60, int(minutes)))
    limit = max(1, min(200, int(limit)))
    sql = f"""
        SELECT timestamp, namespace, pod_name, process_binary,
               arrayStringConcat(process_arguments, ' ') AS args,
               parent_process
        FROM default.process_telemetry
        WHERE timestamp > now() - INTERVAL {minutes} MINUTE
        ORDER BY timestamp DESC
        LIMIT {limit}
    """
    return _query(sql)


def query_pod_activity(pod_name: str, minutes: int = 10) -> str:
    """Return all process exec events for a single pod.

    Args:
        pod_name: Exact pod name (e.g. 'pipeline-test').
        minutes: Look-back window in minutes (1 to 120).
    """
    if not pod_name or not pod_name.replace("-", "").replace(".", "").isalnum():
        return "Invalid pod_name. Must be alphanumeric with dashes/dots only."
    minutes = max(1, min(120, int(minutes)))
    pod_escaped = pod_name.replace("'", "")
    sql = f"""
        SELECT timestamp, process_binary,
               arrayStringConcat(process_arguments, ' ') AS args,
               parent_process
        FROM default.process_telemetry
        WHERE pod_name = '{pod_escaped}'
          AND timestamp > now() - INTERVAL {minutes} MINUTE
        ORDER BY timestamp DESC
        LIMIT 100
    """
    return _query(sql)


def query_binary_history(binary_path: str, minutes: int = 60) -> str:
    """Return where and when a specific binary has been executed.

    Useful for asking 'has this been seen before?' or
    'where else is this binary running?'.

    Args:
        binary_path: Full path to the binary (e.g. '/bin/sh').
        minutes: Look-back window in minutes (1 to 1440).
    """
    if not binary_path or "'" in binary_path:
        return "Invalid binary_path."
    minutes = max(1, min(1440, int(minutes)))
    sql = f"""
        SELECT namespace, pod_name, count() AS execs,
               min(timestamp) AS first_seen,
               max(timestamp) AS last_seen
        FROM default.process_telemetry
        WHERE process_binary = '{binary_path}'
          AND timestamp > now() - INTERVAL {minutes} MINUTE
        GROUP BY namespace, pod_name
        ORDER BY execs DESC
        LIMIT 50
    """
    return _query(sql)


# Tool schema in JSON Schema format. Used by both Ollama and Anthropic;
# minor format differences are normalized inside the backend layer.
TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_recent_executions",
            "description": (
                "Get the most recent process exec events across the entire "
                "cluster. Use this to start an investigation — it's a broad "
                "sweep showing what's been running."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {
                        "type": "integer",
                        "description": "Look-back window in minutes (1-60).",
                        "default": 5,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max rows to return (1-200).",
                        "default": 50,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_pod_activity",
            "description": (
                "Get all process exec events for one specific pod. Use this "
                "to drill into a pod that looked suspicious in the broad sweep."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pod_name": {
                        "type": "string",
                        "description": "Exact pod name.",
                    },
                    "minutes": {
                        "type": "integer",
                        "description": "Look-back window in minutes (1-120).",
                        "default": 10,
                    },
                },
                "required": ["pod_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_binary_history",
            "description": (
                "See where and when a specific binary has been executed. "
                "Use this to check 'is this binary normal?' — a binary "
                "running in only one weird place is more suspicious than "
                "one running everywhere routinely."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "binary_path": {
                        "type": "string",
                        "description": "Full path to the binary, e.g. '/bin/sh'.",
                    },
                    "minutes": {
                        "type": "integer",
                        "description": "Look-back window in minutes (1-1440).",
                        "default": 60,
                    },
                },
                "required": ["binary_path"],
            },
        },
    },
]


# Dispatch table for the agent loop.
TOOL_FUNCTIONS = {
    "query_recent_executions": query_recent_executions,
    "query_pod_activity": query_pod_activity,
    "query_binary_history": query_binary_history,
}
