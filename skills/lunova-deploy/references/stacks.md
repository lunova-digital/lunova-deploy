# Stack recipes

Server today: Ubuntu 24.04, 2 GB RAM + 4 GB swap. Installed: Python 3.12, **PHP 8.3, 8.4 and 8.5 (each with its own FPM pool; default 8.3), Composer, Node 22, MariaDB 10.11**, Caddy. Installed on demand by the pipeline: PHP extensions, PostgreSQL, and any apt package declared in `packages:`. Docker only for `service` sites (needs `ops/setup-containers`; use `mode=check` to see `containers:` and the allowed images). Not available: other PHP versions (only 8.3/8.4/8.5), other Node versions. Use `mode=check` to read the live capabilities before assuming (it also shows free disk and registered sites). Memory is limited: avoid heavy build steps on the server, build in CI.

## laravel
Server provides (installed once): PHP 8.3/8.4/8.5 + one FPM pool `lunova` per version (runs as `deploy`), Composer 2.7, MariaDB 10.11, Node 22. Per site everything else is automatic.
Manifest: `type: laravel`, `php: "8.3"` (or `"8.4"` / `"8.5"`; default 8.3), `database: mysql|postgres|sqlite` (server creates DB + user + generated password and installs the PHP driver), `queue: true` if the app dispatches queued jobs/mail (`QUEUE_CONNECTION=database`), `scheduler: true` if `routes/console.php` schedules commands. Defaults: `build` = composer install, `hooks` = migrate, config/route/view/event cache, storage:link. Document root is `public`.
**PHP platform rule (important):** the site runs on the PHP version in the manifest (`php:`, default 8.3). `composer.lock` must be installable on that version, otherwise CI/server `composer install` fails with e.g. "requires php >=8.4". Check `composer.json` for `"config": {"platform": {"php": "<version>.0"}}` matching the manifest (e.g. `8.4.0`); if missing add it and run `composer update` so the lock is resolved for that version (do not resolve on a newer local PHP). Or set `php: "8.4"`/`"8.5"` in the manifest if the project needs it. Verify with the `check` run.
`public/build` committed = no Node build needed; otherwise set `node: "22"` and `build: [composer install ..., npm ci, npm run build]`.
Uploads: `shared/storage` persists across releases; `storage:link` runs automatically. Mail: seal the credentials (`MAIL_*`, or `RESEND_KEY` with `MAIL_MAILER=resend`) with `scripts/lunova-seal`. The server sets `APP_ENV=production`, `APP_DEBUG=false`, `APP_URL` from the first domain and generates `APP_KEY`; to keep an existing production key (live sessions/encrypted data) seal `APP_KEY` explicitly.
Sessions/cache in the database need the app's migrations (run automatically by the hook).

## node
Node 22 is installed. Needs ops only if `package.json` engines require a different major. Manifest: `type: node`, `start: node server.js` (or `npm start`), app must listen on `process.env.PORT` and `127.0.0.1`. Default hook: `npm ci --omit=dev` on the server. Next.js/Nuxt SSR: build in CI (`npm run build`), set `include_node_modules: true` or keep the default and let the server install, start with `npm start`/`node .output/server/index.mjs`.

## spa / static
No server runtime needed. `type: spa` rewrites unknown paths to `/index.html`. Set `root` to the build output (`dist`, `build`, `public`) and make sure the CI `build` produces it. Cheapest, safest option. Next.js static export, Vite, CRA, Astro static, plain HTML.

## python
Python 3.12 is available. Manifest: `type: python`, `start: .venv/bin/gunicorn app:app -b 127.0.0.1:$PORT`. Default hooks create `.venv` and install `requirements.txt` (gunicorn must be in it). System libraries go in `packages:`; a database is created like for Laravel (`database:`).

## service (internal container)
An INTERNAL container from an allow-listed image: no domain, no certificate, published on `127.0.0.1:<host_port>` only. Used for things like the Signal gateway that only the hub on the same server may call. Manifest: `type: service`, `image: <name>:<exact tag>`, `container_port`, `host_port` (optional), `env` (fixed, non-secret), `volumes` (`name:/path`), `memory_mb`, `health_path` (an HTTP path on the container that returns 2xx/3xx). A release is the container's configuration: `lunova-site` starts it through a root helper, checks health and switches; if the container does not start or fail health, the previous configuration is started again. Rollback does the same. The image is pulled by tag on each new configuration, and an unchanged configuration never restarts the container. Needs ops once: `ops/setup-containers` (Docker + the allow-list). Images are added to `/etc/lunova/containers.json` by ops only (ops request #6). The container has no privileges beyond a small fixed set (no host mounts, no extra capabilities, memory/process limits).

## Not supported yet (ask ops)
Arbitrary Docker/compose (only allow-listed `service` images), WebSocket servers needing special proxy config, multi-process workers beyond one service per site, non-HTTP services. (Redis can be added through `packages: [redis-server]` for same-host use.)
