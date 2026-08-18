# Observability Workflow

## Purpose
Add logging, metrics, tracing

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
id: ws_observability
priority: P2
description: Add logging, metrics, tracing
logging:
  format: JSON structured logging
  fields:
  - timestamp
  - level
  - message
  - service
  - trace_id
  - span_id
  example: "{\n  \"timestamp\": \"2025-01-18T12:00:00Z\",\n  \"level\": \"info\",\n  \"message\": \"Request processed\",\n\
    \  \"service\": \"api\",\n  \"trace_id\": \"abc123\",\n  \"duration_ms\": 42\n}\n"
metrics:
  standard:
  - request_count
  - request_duration_seconds
  - error_count
  - active_connections
tracing:
  standard: OpenTelemetry
  propagation: W3C Trace Context
```

## Validation
Must comply with `rup-schema.json`.
