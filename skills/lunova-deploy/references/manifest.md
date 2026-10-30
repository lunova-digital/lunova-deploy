# `.lunova.yml` reference

Lives at the repo root. Read by the shared workflow with `yq`. Unknown keys are ignored.

| key | required | meaning |
|---|---|---|
| `site` | yes | Unique site id: lowercase letters/digits/hyphens, 2-41 chars, starts with a letter. Reserved: default, caddy, registry, lunova, admin, root, deploy, ops. A site is bound to the first repo that registers it. |
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
| `http_only` | no | Serve over plain HTTP (no certificate). Testing only. |

## Server paths (for reference, not editable)
`/srv/sites/<site>/releases/<id>` (immutable) · `current` (symlink) · `shared/.env` (written from the `LUNOVA_ENV` secret) · `shared/storage` (Laravel storage, persists across releases).

## Environment variables
The repo secret `LUNOVA_ENV` contains the whole production `.env` (dotenv format). Each deploy writes it to `shared/.env` (mode 600). Node/Python services receive it via systemd `EnvironmentFile` plus `PORT` and `HOST`. If the secret is absent the previous `shared/.env` is kept.
