# Gold API

A small synchronous Flask API that returns cached 18k gold and USD prices.

## Run locally

1. Copy `.env.example` to `.env` and provide provider credentials if external refreshes are needed.
2. Start Redis (`redis-server`) or set `REDIS_HOST` to an accessible Redis instance.
3. Install dependencies with `pip install -r requirements.txt`.
4. Start the service with `gunicorn --bind 0.0.0.0:8000 app:app`.

Endpoints:

- `GET /gold` — cached/fresh 18k gold price
- `GET /usd` — cached/fresh USD price
- `GET /hokm` — compatibility endpoint
- `GET /counter` — request counters for all three routes
- `GET /health` — Redis readiness check

Cache TTLs and stale-data windows are configurable through `.env.example`; the defaults preserve the existing gold (15 minutes) and USD (10 minutes) refresh behavior.

## Docker Compose

Set `ONE_API_TOKEN` and `BRS_API_TOKEN` in the shell or a local `.env` file, then run:

```bash
docker compose up --build -d
```

Caddy terminates HTTPS for `gold.benjiro.ir:8080` and reverse proxies to the internal Gold API on `gold:8000`. Host port `8080` is the public API endpoint; host port `443` is forwarded only to Caddy's internal `8443` listener for the Let's Encrypt TLS-ALPN-01 challenge, while host port `80` remains unused. Flask/Gunicorn and Redis are not published on host ports. Redis supports the optional `REDIS_PASSWORD` and persists in the `redis_data` volume. Compose also applies bounded CPU/memory/PID limits, rotated JSON logs, dropped Linux capabilities, `no-new-privileges`, and read-only root filesystems. Caddy runs as UID/GID `10001`; the one-shot `caddy-init` service prepares ownership for its persistent volumes.

Provider credentials are intentionally loaded only from environment variables and are never stored in the repository.