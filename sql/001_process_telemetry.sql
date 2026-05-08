-- process_telemetry: ingestion target for Tetragon process_exec events
-- via Vector. Schema matches the VRL transform output in
-- k8s/vector/values.yaml (parse_tetragon transform).

CREATE TABLE IF NOT EXISTS default.process_telemetry
(
    timestamp           DateTime64(3, 'UTC'),
    node_name           LowCardinality(String),
    namespace           LowCardinality(String),
    pod_name            String,
    process_binary      String,
    process_arguments   Array(String),
    parent_process      String
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (namespace, pod_name, timestamp)
TTL toDateTime(timestamp) + INTERVAL 7 DAY
SETTINGS index_granularity = 8192;
