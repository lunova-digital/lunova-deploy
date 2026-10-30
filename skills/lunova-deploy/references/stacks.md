# Stack recipes

Server today: Ubuntu 24.04, 2 GB RAM, **only Python 3.12, git, rsync preinstalled**. Node, PHP, Composer, databases are **not installed**: the first project needing them triggers an ops request. Use `mode=check` to read the live capabilities before assuming.

## laravel
Needs ops (one time per server, shared by all Laravel sites): PHP-FPM (8.3 or 8.4) with Laravel extensions, a pool `lunova` running as user `deploy` with socket `/run/php/lunova.sock` (`listen.owner=caddy`, `listen.group=caddy`, mode 0660), PHP CLI + Composer for `deploy`, plus a database (MySQL/MariaDB or PostgreSQL) with a DB and user **per site** (ops creates these; the developer puts the credentials in `LUNOVA_ENV`).
Manifest: `type: laravel`, `php: "8.3"` (match `composer.json`), `build` defaults to composer install; if assets are built (Vite) add `node` and `npm ci && npm run build` **unless** `public/build` is committed. Default server hooks run migrations and caches. Document root is `public`.
Also decide: queue worker (needs a user service: ask ops or use `QUEUE_CONNECTION=sync`), scheduler (needs a cron/timer: ops request), file uploads (use `shared/storage`, persists across releases), mail (SMTP credentials in `LUNOVA_ENV`).
`.env` must have `APP_ENV=production`, `APP_DEBUG=false`, real `APP_URL`, `APP_KEY`.

## node
Needs ops: Node (version in `package.json` engines) available to `deploy`. Manifest: `type: node`, `start: node server.js` (or `npm start`), app must listen on `process.env.PORT` and `127.0.0.1`. Default hook: `npm ci --omit=dev` on the server. Next.js/Nuxt SSR: build in CI (`npm run build`), set `include_node_modules: true` or keep the default and let the server install, start with `npm start`/`node .output/server/index.mjs`.

## spa / static
No server runtime needed. `type: spa` rewrites unknown paths to `/index.html`. Set `root` to the build output (`dist`, `build`, `public`) and make sure the CI `build` produces it. Cheapest, safest option. Next.js static export, Vite, CRA, Astro static, plain HTML.

## python
Python 3.12 is available. Manifest: `type: python`, `start: .venv/bin/gunicorn app:app -b 127.0.0.1:$PORT`. Default hooks create `.venv` and install `requirements.txt` (gunicorn must be in it). Packages needing system libraries or a database need ops.

## Not supported yet (ask ops)
Docker/containers, WebSocket servers needing special proxy config, multi-process workers beyond one service per site, Redis, non-HTTP services.
