# Observability Workflow

## Purpose
Add logging, metrics, tracing

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
description: Add logging, metrics, tracing
id: ws_observability
logging:
  example: "{\n  \"timestamp\": \"2025-01-18T12:00:00Z\",\n  \"level\": \"info\",\n\
    \  \"message\": \"Request processed\",\n  \"service\": \"api\",\n  \"trace_id\"\
    : \"abc123\",\n  \"duration_ms\": 42\n}\n"
  fields:
  - timestamp
  - level
  - message
  - service
  - trace_id
  - span_id
  format: JSON structured logging
metrics:
  standard:
  - request_count
  - request_duration_seconds
  - error_count
  - active_connections
priority: P2
tracing:
  propagation: W3C Trace Context
  standard: OpenTelemetry

```

## Validation
Must comply with `rup-schema.json`.
