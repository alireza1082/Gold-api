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

The API is exposed on port `8080`; Redis is internal-only, supports the optional `REDIS_PASSWORD`, and persists in the `redis_data` volume.

Provider credentials are intentionally loaded only from environment variables and are never stored in the repository.