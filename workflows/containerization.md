# Containerization Workflow

## Purpose
Add containerization best practices

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
best_practices:
- Use multi-stage builds
- Use non-root user
- Use distroless/minimal base images
- Pin dependency versions
- Add health checks
- Minimize layers
- Use .dockerignore
compose_template: "version: '3.8'\nservices:\n  app:\n    build: .\n    ports:\n \
  \     - \"{port}:{port}\"\n    environment:\n      - NODE_ENV=production\n    healthcheck:\n\
  \      test: {health_check}\n      interval: 30s\n      timeout: 10s\n      retries:\
  \ 3\n"
description: Add containerization best practices
dockerfile_template: "# syntax=docker/dockerfile:1\n\n# Build stage\nFROM {base_image}\
  \ AS builder\nWORKDIR /app\nCOPY {lockfile} .\nRUN {install_command}\nCOPY . .\n\
  RUN {build_command}\n\n# Runtime stage\nFROM {runtime_image}\nRUN adduser --disabled-password\
  \ --gecos \"\" appuser\nUSER appuser\nWORKDIR /app\nCOPY --from=builder /app/{artifact}\
  \ .\nEXPOSE {port}\nHEALTHCHECK --interval=30s --timeout=3s \\\n  CMD {health_check_command}\n\
  CMD [\"{entrypoint}\"]\n"
id: ws_containers
priority: P2

```

## Validation
Must comply with `rup-schema.json`.
