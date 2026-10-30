# Troubleshooting (workflow log -> cause -> fix)

| Message | Cause | Fix |
|---|---|---|
| `Org variables LUNOVA_HOST / LUNOVA_HOST_FPR are not visible` | repo not granted org vars | ops request #1 |
| `Server host key does not match the pinned fingerprint` | server rebuilt or MITM | stop; tell ops, do not bypass |
| `Permission denied (publickey)` | org secret missing/not shared with this repo | ops request #1 |
| `invalid site name` / `domain ... already used by site` | manifest | change `site`/`domains` |
| `site '<x>' belongs to repo ...` | name taken by another repo | choose another `site` |
| `PHP-FPM socket ... not found` | no PHP-FPM on server | ops request #2 |
| `command not found: composer/php/node/npm` in a hook | runtime missing for `deploy` | ops request #2 |
| `hook failed: ...` | migration/install error; **live site unchanged** | fix the cause shown above the error; redeploy |
| `health check failed (...)` + `rolled back` | new release did not answer | check `start`, port binding to `127.0.0.1:$PORT`, missing env var; compare `LUNOVA_ENV` |
| 502 from Caddy after deploy | app crashed/started on wrong port | `start` must use `$PORT` |
| `shared/.env is missing` | no `LUNOVA_ENV` secret yet | set the secret, redeploy |
| Certificate/HTTPS error on first visit | DNS not pointing at server yet or still propagating | `mode=check`, fix DNS, wait, retry |
| `Could not resolve to a Repository` (gh) | wrong gh account / no access | `gh auth status`, `gh auth switch` |
