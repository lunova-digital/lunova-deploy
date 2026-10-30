# Stack recipes

Server today: Ubuntu 24.04, 2 GB RAM + 4 GB swap. Installed: Python 3.12, **PHP 8.3 + FPM, Composer, Node 22, MariaDB 10.11**, Caddy. Installed on demand by the pipeline: PHP extensions, PostgreSQL, and any apt package declared in `packages:`. Not available: Docker, other PHP/Node versions. Use `mode=check` to read the live capabilities before assuming (it also shows free disk and registered sites). Memory is limited: avoid heavy build steps on the server, build in CI.

## laravel
Server provides (installed once): PHP 8.3 + FPM pool `lunova` (runs as `deploy`), Composer 2.7, MariaDB 10.11, Node 22. Per site everything else is automatic.
Manifest: `type: laravel`, `php: "8.3"`, `database: mysql|postgres|sqlite` (server creates DB + user + generated password and installs the PHP driver), `queue: true` if the app dispatches queued jobs/mail (`QUEUE_CONNECTION=database`), `scheduler: true` if `routes/console.php` schedules commands. Defaults: `build` = composer install, `hooks` = migrate, config/route/view/event cache, storage:link. Document root is `public`.
**PHP platform rule (important):** the server runs PHP 8.3. `composer.lock` must be installable on 8.3, otherwise CI/server `composer install` fails with "requires php >=8.4". Check `composer.json` for `"config": {"platform": {"php": "8.3.0"}}`; if missing add it and run `composer update` so the lock is resolved for 8.3 (do not resolve on a newer local PHP). Verify with the `check` run.
`public/build` committed = no Node build needed; otherwise set `node: "22"` and `build: [composer install ..., npm ci, npm run build]`.
Uploads: `shared/storage` persists across releases; `storage:link` runs automatically. Mail: seal the credentials (`MAIL_*`, or `RESEND_KEY` with `MAIL_MAILER=resend`) with `scripts/lunova-seal`. The server sets `APP_ENV=production`, `APP_DEBUG=false`, `APP_URL` from the first domain and generates `APP_KEY`; to keep an existing production key (live sessions/encrypted data) seal `APP_KEY` explicitly.
Sessions/cache in the database need the app's migrations (run automatically by the hook).

## node
Node 22 is installed. Needs ops only if `package.json` engines require a different major. Manifest: `type: node`, `start: node server.js` (or `npm start`), app must listen on `process.env.PORT` and `127.0.0.1`. Default hook: `npm ci --omit=dev` on the server. Next.js/Nuxt SSR: build in CI (`npm run build`), set `include_node_modules: true` or keep the default and let the server install, start with `npm start`/`node .output/server/index.mjs`.

## spa / static
No server runtime needed. `type: spa` rewrites unknown paths to `/index.html`. Set `root` to the build output (`dist`, `build`, `public`) and make sure the CI `build` produces it. Cheapest, safest option. Next.js static export, Vite, CRA, Astro static, plain HTML.

## python
Python 3.12 is available. Manifest: `type: python`, `start: .venv/bin/gunicorn app:app -b 127.0.0.1:$PORT`. Default hooks create `.venv` and install `requirements.txt` (gunicorn must be in it). System libraries go in `packages:`; a database is created like for Laravel (`database:`).

## Not supported yet (ask ops)
Docker/containers, WebSocket servers needing special proxy config, multi-process workers beyond one service per site, non-HTTP services. (Redis can be added through `packages: [redis-server]` for same-host use.)
