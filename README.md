# Gold API

A small synchronous Flask API that returns cached 18k gold and USD prices.

## Run locally

1. Copy `.env.example` to `.env`; `ONE_API_TOKEN` is used only as a gold-price fallback.
2. Start Redis (`redis-server`) or set `REDIS_HOST` to an accessible Redis instance.
3. Install dependencies with `pip install -r requirements.txt`.
4. Start the service with `gunicorn --bind 0.0.0.0:8000 app:app`.

Endpoints:

- `GET /gold` — cached/fresh 18k gold price
- `GET /usd` — cached/fresh USD price
- `GET /hokm` — compatibility endpoint
- `GET /xo` — compatibility endpoint
- `GET /hokm-ad` and `GET /xo-ad` — runtime-configured promotional card metadata
- `GET /hokm-ad/image` and `GET /xo-ad/image` — promotional image files served by this API
- `GET /counter` — request counters for all four routes
- `GET /health` — Redis readiness check

Cache TTLs and stale-data windows are configurable through `.env.example`; gold refreshes every 15 minutes and USD refreshes every 30 minutes by default.

## Docker Compose

Set `ONE_API_TOKEN` in the shell or a local `.env` file if the gold API fallback is needed, then run:

```bash
docker compose up --build -d
```

Caddy terminates HTTPS for `gold.benjiro.ir:8080` and reverse proxies to the internal Gold API on `gold:8000`. Host port `8080` is the public API endpoint; host port `443` is forwarded only to Caddy's internal `8443` listener for the Let's Encrypt TLS-ALPN-01 challenge, while host port `80` remains unused. Flask/Gunicorn and Redis are not published on host ports. Redis supports the optional `REDIS_PASSWORD` and persists in the `redis_data` volume. Compose also applies bounded CPU/memory/PID limits, rotated JSON logs, dropped Linux capabilities, `no-new-privileges`, and read-only root filesystems. Caddy runs as UID/GID `10001`; the one-shot `caddy-init` and `redis-init` services prepare ownership for their persistent volumes.

## Promotional cards

The promo API is implemented at `GET /hokm-ad`, `GET /xo-ad`, `GET /hokm-ad/image`, and `GET /xo-ad/image`. The metadata routes return JSON; image routes return the binary image file with its matching image MIME type. Gold API serves these images itself, so no CDN or external image host is required.

Hokm and XO configuration are independent. Edit `promo/hokm.json` or `promo/xo.json`; the corresponding `.webp`, `.png`, `.jpg`, or `.jpeg` asset belongs in the same `promo/` directory. WebP is the primary format; the bundled game-themed images are 512×512 WebP files. PNG and JPEG files are also supported. The default files disable both campaigns until real campaign details are provided. A disabled campaign returns HTTP 200:

```json
{
  "enabled": false,
  "cache_ttl_seconds": 21600
}
```

An enabled campaign returns the title and HTTPS destination along with a versioned image URL. For example:

```json
{
  "enabled": true,
  "id": "phoenix-coin",
  "title": "Phoenix Coin",
  "url": "https://phoenix-coin.ir",
  "image_url": "https://gold.benjiro.ir:8080/hokm-ad/image?v=<revision>",
  "cache_ttl_seconds": 21600
}
```

To enable a campaign, set its own JSON file. For example, in `promo/hokm.json`:

```json
{
  "enabled": true,
  "id": "phoenix-coin",
  "title": "Phoenix Coin",
  "url": "https://example.com",
  "image": "hokm.webp",
  "cache_ttl_seconds": 21600
}
```

XO uses the same fields in `promo/xo.json` and an image file such as `xo.webp`. Set `image` to `null` for a text-only card.

The default metadata cache TTL is 21,600 seconds (6 hours), configurable per campaign from 60 seconds to 7 days. Metadata responses include `Cache-Control: public, max-age=<cache_ttl_seconds>`, ETag, and Last-Modified validators. Images include ETag and Last-Modified validators and use `Cache-Control: public, max-age=31536000, immutable`. The `image_url` revision is derived from the image's modification time, size, and inode; replacing an image changes the URL and lets clients fetch the new bytes despite the long image cache lifetime.

`PUBLIC_BASE_URL=https://gold.benjiro.ir:8080` sets the public HTTPS origin used to build `image_url`. This default matches the Caddy site on public port 8080; set the variable to the public origin if the deployment changes. The API does not build this URL from request `Host` or forwarded headers.

Docker Compose mounts only the runtime promo directory read-only at `./promo:/app/promo:ro`. Each request checks the relevant JSON file's modification time, size, and inode, and reloads the parsed configuration when that signature changes. Replacing either JSON file or image on the host therefore takes effect on the next request without rebuilding the image or restarting Gunicorn. Campaign IDs are safe strings up to 64 characters; titles are plain text up to 60 characters; destination URLs must be valid HTTPS URLs; image names are restricted to local files within `promo/`; and cache TTLs must be between 60 seconds and 7 days. Missing or invalid configuration fails closed to the disabled response; a missing or invalid configured image is logged and omitted from metadata.

Verification for the promo implementation: `python3 -m pytest -q` passed with 47 tests, including metadata behavior, runtime reload, image bytes and MIME type, cache headers and revisioning, invalid URLs, traversal rejection, and disabled/missing-image behavior.

Provider credentials are intentionally loaded only from environment variables and are never stored in the repository.
