# Operational Excellence (Phase 5C)

This document provides a guide to the operational strategies, metrics, and backup procedures for Nexora in a production environment.

## 1. Observability & Metrics
Nexora is equipped with an automatically generated Prometheus metrics endpoint.

- **Endpoint**: `/metrics`
- **Data Tracked**:
  - `http_requests_total`: Total number of HTTP requests, partitioned by method, path, and status code.
  - `http_request_size_bytes`: Distribution of incoming request sizes.
  - `http_response_size_bytes`: Distribution of outgoing response sizes.
  - `http_request_duration_seconds`: Request latencies useful for tracking p95 and p99 performance.

**Integration**: Configure your Prometheus instance to scrape `http://nexora-proxy:80/api/metrics` every 15s. No authentication is enforced on this endpoint by default.

## 2. Structured Logging
The backend uses JSON structured logging with Correlation IDs.
- **Correlation ID**: Every HTTP request is tagged with an `X-Request-ID`. This ID is injected into the logs as `correlation_id` and is also returned in any Error Responses.
- **Log Location**: Logs are emitted to `stdout` and collected by the Docker daemon. Configure `docker-compose.prod.yml` to use `json-file` with size limits, or forward them to an aggregator (e.g., Fluentd, Datadog).

## 3. Backup & Recovery

### PostgreSQL
To backup the Postgres database containing user configurations, ownerships, and check-pointed chat states:
```bash
docker exec nexora-postgres pg_dump -U nexora -d nexora > nexora_db_backup.sql
```
To restore:
```bash
cat nexora_db_backup.sql | docker exec -i nexora-postgres psql -U nexora -d nexora
```

### ChromaDB
ChromaDB uses volume-backed persistence. To backup:
1. Stop the application gracefully: `docker compose stop backend chromadb`
2. Tar the volume data: `docker run --rm -v nexora_chroma_data:/data -v $(pwd):/backup alpine tar czvf /backup/chroma_backup.tar.gz /data`
3. Restart: `docker compose start`

To restore:
1. Stop the stack.
2. Extract the archive into the volume mount.

### Media Files
Back up the `nexora_app_data` volume containing local media caches using a similar tar strategy.

## 4. Performance Tuning
- **Uvicorn Workers**: Modify the Dockerfile `CMD` to include `--workers 4` (or your CPU count). By default, it runs 1 worker.
- **Database Connection Pool**: The SQLite/PostgreSQL engine sets a default `pool_size=5`. You can adjust this via code injection in `engine.py` depending on load.
- **LLM Timeout**: Modify `NEXORA_LLM_TIMEOUT_SECONDS` (default: 30) if using cloud inference (OpenAI) to prevent blocking background worker threads indefinitely.

## 5. Runtime Security
- **CORS**: Controlled via `NEXORA_CORS_ORIGINS`. Do not use `["*"]` in production; restrict it to your specific frontend domains.
- **Trusted Host**: Configured inside FastAPI to prevent HTTP Host Header injection attacks.
