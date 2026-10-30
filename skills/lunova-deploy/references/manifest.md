# `.lunova.yml` reference

Lives at the repo root. Read by the shared workflow with `yq`. Unknown keys are ignored.

| key | required | meaning |
|---|---|---|
| `site` | yes | Unique site id: lowercase letters/digits/hyphens, 2-41 chars, starts with a letter. Reserved: default, caddy, registry, lunova, admin, root, deploy, ops. A site is bound to the first repo AND branch that registers it. |
| `type` | yes | `static`, `spa`, `node`, `python`, `laravel` |
| `domains` | yes | List of hostnames. Each needs a DNS A record to the server IP before TLS can be issued. A domain can belong to one site only. |
| `root` | static/spa | Folder to serve inside the release (e.g. `dist`). Default: release root. |
| `start` | node/python | Command that listens on `127.0.0.1:$PORT`. No `'`, `%` or newlines. Example: `node server.js`, `.venv/bin/gunicorn app:app -b 127.0.0.1:$PORT`. |
| `php` / `node` | no | Versions for the CI build (setup-php / setup-node). |
| `build` | no | Commands CI runs before upload. If omitted: laravel = `composer install --no-dev ...`; node/spa/static = `npm ci` + `npm run build --if-present` when `package.json` exists. |
| `hooks` | no | Commands run **on the server inside the new release before it goes live**. A failure aborts the release and the live site is unchanged. Omit for per-type defaults, `[]` for none. Defaults: laravel = migrate, config/route/view/event cache, storage:link; node = `npm ci --omit=dev`; python = venv + pip install. |
| `health_path` | no | Path that must return 2xx/3xx after switching. Default `/`. Failing = automatic rollback. |
| `exclude` | no | Extra rsync excludes. Always excluded: `.git`, `.github`, `.env`, `.env.*`, `.lunova.yml`, `node_modules` (unless `include_node_modules`). |
| `include_node_modules` | no | Upload `node_modules` built in CI instead of installing on the server. |
| `database` | no | `mysql` (MariaDB), `postgres` (installed on first use) or `sqlite`. The server creates the database and user and **generates the password**, then injects `DB_*` into the app environment. Sealed env values for `DB_*` are refused; developers never see or choose the password. Idempotent: credentials are kept on every deploy. |
| `packages` | no | Extra apt packages the project needs (e.g. `ffmpeg`). PHP extensions (from `composer.lock`) and the database engine/driver are installed automatically, so most projects list nothing. System, security, container and web-server packages are refused. |
| `queue` | no | Laravel only. `true` = a queue worker (`queue:work`) runs as a service for the site and is restarted on each release. Use with `QUEUE_CONNECTION=database`. |
| `scheduler` | no | Laravel only. `true` = `php artisan schedule:run` runs every minute (systemd timer). |
| `http_only` | no | Serve over plain HTTP (no certificate). Testing only. |

## Server paths (for reference, not editable)
`/srv/sites/<site>/releases/<id>` (immutable) · `current` (symlink) · `shared/.env` (built on the server, see below) · `shared/storage` (Laravel storage, persists across releases).

## Environment variables (no GitHub secrets)
The server builds the app's `.env` itself, in this order of precedence:
1. **Database credentials** (`DB_*`), generated and injected by the server. Always win.
2. **Sealed values** the developer provided, committed as `.lunova/env.sealed` (encrypted with the server's public key by `scripts/lunova-seal`; only the server can read it, so it is safe in git). Applying it is a merge: only the listed keys change, the rest are kept. A given file is applied once (by hash).
3. **Server defaults** for Laravel: `APP_ENV=production`, `APP_DEBUG=false`, `APP_URL=https://<first domain>`, a generated `APP_KEY`.
4. **`.env.example`** from the repo, for every key not set above.
`shared/.env` is mode 600. Node/Python services receive it via systemd `EnvironmentFile` plus `PORT` and `HOST`.
To change a value later: seal a patch containing just that key and push. To see what is set (names only, never values) run the workflow in `status` mode.
