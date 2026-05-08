## Day 1 (2026-05-08)
- ClickHouse deployed to telemetry ns with 20Gi PVC
- process_telemetry table created from sql/001_process_telemetry.sql
- Cross-namespace DNS verified (gatekeeper → telemetry)
- Decision: dropped istio, no value for this project
- Decision: telemetry/gatekeeper namespace split for clean lifecycle separation

