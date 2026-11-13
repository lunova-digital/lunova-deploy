# Wildcard tenancy, first admin and the privileged modes (v10)

For a multi-tenant Laravel app where `app.example.com` is the platform and every tenant lives on `<tenant>.example.com`. One site, one app root: the platform host and `*.example.com` are served by the same release. First user: Shikhon (`app.lunovait.com` + `*.lunovait.com`).

## `.lunova.yml`
```yaml
site: shikhon
type: laravel
database: mysql
queue: true
tenancy:
  root_domain: lunovait.com
  platform_host: app.lunovait.com
  wildcard: true            # serve *.lunovait.com too
  tls_cert: lunovait.com    # origin certificate name: /etc/caddy/certs/lunovait.com.{pem,key}
seeders: [DatabaseSeeder]   # the ONLY seeders reset-db may run ([] = migrate:fresh only)
tasks:                      # the ONLY commands run / bootstrap-admin may run; {email} and {name} are the only placeholders
  super_admin: "access:super-admin {email} --name={name}"
```
Rules (enforced on the server, not just here): exactly one wildcard and it must be `*.<root_domain>`, only with `wildcard: true` **and** `tls_cert`; `platform_host` is the root domain or a name under it; `domains:` may still list extra names (they keep Caddy's automatic certificates); `http_only` is refused; a task is `<namespaced:artisan-command> args…` (no shell, no quotes, `$`, `;`, `|`, `` ` ``); `seeders`/`tasks` are laravel only. Everything is optional: a manifest without these keys behaves exactly as before.

## One-time setup (do these once; nothing here is automatic)
1. **Ops, on the server:** `ops/setup-tenancy [host]` (installs `lunova-site`, `lunova-gate`, the root helper `lunova-priv`, one sudoers line, the cert/backup/secret directories, `mysqldump`).
2. **Cloudflare, certificate:** SSL/TLS → Origin Server → Create certificate for `lunovait.com` and `*.lunovait.com`. Keep the PEM text; set the zone's SSL mode to **Full (strict)**.
3. **Cloudflare, API token** (only needed for `dns_sync`): My Profile → API Tokens → custom token, **zone-scoped to this one zone**, permissions: Zone → Zone → Read, Zone → DNS → Edit, and the redirect-rules permission (Zone → *Single Redirect* / *Dynamic URL Redirects* → Edit; the exact name varies, it is the one that lets you edit "Redirect Rules"). Nothing account-wide.
4. **GitHub environment (in the app's repo):** Settings → Environments → `production` → *Required reviewers* (at least one person other than whoever starts the run if you can) and restrict deployment branches to the deploy branch.
5. **GitHub secrets**, stored as **environment secrets of `production`** (so only an approved job receives them): `ORIGIN_CERT` (the PEM certificate), `ORIGIN_KEY` (the PEM private key), `CF_API_TOKEN`. Run these yourself, they read files you hold:
   `gh secret set ORIGIN_CERT --env production < origin.pem` · `gh secret set ORIGIN_KEY --env production < origin.key` · `gh secret set CF_API_TOKEN --env production`
6. Regenerate the caller workflow (the skill does it) so it exposes the new modes and passes the three secrets, pointing at `@v10`.

## First-run order for a new tenancy site
```
tenancy-setup  ->  deploy  ->  check  ->  reset-db (only if wanted)  ->  bootstrap-admin
```
| step | command | what it does |
|---|---|---|
| 1 | `gh workflow run lunova-deploy.yml -f mode=tenancy-setup -f confirm=shikhon -f dns_sync=true` (approve the run in GitHub) | installs the origin cert on the server (validated, reload, previous cert restored on failure), syncs proxied A records for `*`, the platform host and the apex plus the apex → platform 301 redirect, registers the site and renders the wildcard Caddy block, then verifies the web server holds a site for the platform host *and* a random `zzz-probe-…` label. The site has no release yet, so this proves the vhost/TLS, not the app. |
| 2 | push to the deploy branch (or `-f mode=deploy`) | normal deploy; ends with a strict verify. |
| 3 | `-f mode=check` | preflight + verify against the origin, config + validation in the summary. |
| 4 | `-f mode=reset-db -f confirm=shikhon` | **backup first** (abort if it fails) → `migrate:fresh` → only the manifest `seeders` → cache clear/rebuild → `queue:restart`. |
| 5 | `-f mode=bootstrap-admin -f confirm=shikhon -f admin_email=… -f admin_name=…` | runs the manifest `super_admin` task. **There is no password input**: the admin gets the app's emailed invite / set-password link. |

Other modes: `backup` (mysqldump → `/srv/backups/<site>/<site>-<utc>.sql.gz`, `gzip -t`, path + size + sha256 in the job summary; never uploaded), `run -f task=<name> [-f admin_email=… -f admin_name=…]` (allow-listed tasks only; those two inputs fill `{email}`/`{name}`). Every mode is idempotent: re-running `tenancy-setup` changes nothing when nothing differs; `bootstrap-admin` is as idempotent as the app's own command.

## What protects the privileged modes
- `tenancy-setup`, `reset-db`, `bootstrap-admin` run in a **separate job bound to the `production` environment** (reviewers must approve) **and** the server refuses them unless the OIDC token says the run was in `production`, was a manual (`workflow_dispatch`) run, came from the site's own repo **and** deploy branch, and the typed `confirm` equals the site name. The workflow file is not trusted for any of this.
- All root actions go through `lunova-priv` (one sudoers line): install cert, create the backup dir, write a root-only secret file, validate the web server config. Secrets arrive on stdin, never argv.
- Whatever `bootstrap-admin`'s command prints (a set-password link, say) is written to `/var/lib/lunova/secrets/<site>/bootstrap-admin-<utc>.txt` (root-only, 0600) and **not returned**; the run reports only the path. Failure output is redacted of links and long tokens. Read the file over ssh as ops if the app printed a link instead of emailing it.
- Every privileged call writes one line `time actor repo ref mode site result` to `/srv/registry/audit.log`; the gate keeps logging to `gate.log`.

## Verify, in words
Each host is probed with `curl --resolve <host>:443:<server-ip>` (Cloudflare bypassed; `-k` because an Origin CA cert is not publicly trusted) on `/` (never `/up`: it answers 200 for any host). The wildcard is probed with a random label. Results are reported separately: **app responded**, **web server: No site configured** (TLS refused or the web server's own "no site" answer), **empty response** (web server answered, no app output: the vhost exists but there is no release yet), **unreachable**.

## Restoring a backup
`gunzip -c /srv/backups/<site>/<file>.sql.gz | mysql …` as ops, using the credentials in `/srv/sites/<site>/shared/db.env`. Check the sha256 from the job summary first. Backups are not rotated automatically: watch the disk.

## Troubleshooting
| message | cause | fix |
|---|---|---|
| `must run in the GitHub environment 'production'` | the run did not go through the `production` environment | create it in the repo; use the regenerated caller workflow |
| `confirmation does not match` | `confirm` is not exactly the `site:` name | retype it |
| `origin certificate '<n>' is not installed` | a deploy/register with a wildcard before `tenancy-setup` | run `tenancy-setup` first |
| `the certificate does not cover *.<root>` | the Origin certificate was created without the wildcard name | create a new one for `<root>` and `*.<root>` |
| `<name> already has a CNAME record` | dns-sync never replaces a record of another type | fix it in Cloudflare |
| `privileged helper failed … sudo: a password is required` | `ops/setup-tenancy` has not been run | ask ops (request #8) |
| verify says `No site configured` for the random label only | the wildcard host is missing from the rendered config | read the config in the job summary; re-run `tenancy-setup` |
