# Troubleshooting (workflow log -> cause -> fix)

| Message | Cause | Fix |
|---|---|---|
| `The server refused this run` | repo owner is not `lunova-digital`/`jakiurcore`, or the caller is not the shared workflow | move the repo (ops-requests #0); use the generated caller unchanged |
| `No OIDC token available` | caller workflow lacks `permissions: id-token: write` | use the generated caller |
| `lunova-gate: refused (...)` | the reason is in the brackets (owner, expired token, workflow, site binding, branch) | fix what it names; a PR/tag run may only use check/status/logs |
| `Server host key does not match the pinned fingerprint` | server rebuilt or MITM | stop; tell ops, do not bypass |
| `invalid site name` / `domain ... already used by site` | manifest | change `site`/`domains` |
| `site '<x>' belongs to repo/another repository` | name taken by another repo | choose another `site` |
| `deploys from branch '<b>' only` | the site is bound to the branch that first deployed it | push to `<b>`, or ops request #1 |
| `PHP-FPM socket ... not found` | no PHP-FPM on server | ops request #2 |
| `command not found: composer/php/node/npm` in a hook | runtime missing for `deploy` | ops request #2 |
| `hook failed: ...` | migration/install error; **live site unchanged** | fix the cause shown above the error; redeploy |
| `health check failed (...)` + `rolled back` | new release did not answer | check `start`, port binding to `127.0.0.1:$PORT`, a missing env value (see `mode=status` for names that are empty) |
| 502 from Caddy after deploy | app crashed/started on wrong port | `start` must use `$PORT` |
| Certificate/HTTPS error on first visit | DNS not pointing at server yet or still propagating | `mode=check`, fix DNS, wait, retry |
| `Could not resolve to a Repository` (gh) | wrong gh account / no access | `gh auth status`, `gh auth switch` |
| `requires php >=8.4` during composer install | lock resolved on a newer PHP than the server's 8.3 | add `config.platform.php = 8.3.0` to composer.json and `composer update` (see stacks.md) |
| `Access denied for user` / SQLSTATE[HY000] [1045] | `database:` missing in `.lunova.yml`, or the app ignores `DB_*` (hard-coded config) | set `database:`; use `env('DB_...')` in config |
| `DB_x is managed by the server` | a sealed patch tried to set DB_* | remove DB_* from the patch; the server generates them |
| `could not install <pkg>` / `not deployment tooling` | apt refused or the package does not exist | fix the name in `packages:`, or ops request #2 |
| `needs PHP extension '<x>' which Lunova does not know` | extension not in the installer's map | add its apt package to `packages:` |
| queued jobs/mail never sent | `queue: true` missing | add `queue: true`, redeploy |
| scheduled task never runs | `scheduler: true` missing | add `scheduler: true`, redeploy |
| 500 right after deploy, `rolled back` | see `logs` mode | `gh workflow run lunova-deploy.yml -f mode=logs` |
| `OK (Cloudflare proxy)` for a domain in check | domain is behind Cloudflare | origin not verifiable: keep DNS-only for the first cert (ops request #3) |
| `rollback`: no earlier successful release | only one healthy release exists | deploy again or use `-f rollback_to=<id>` |
