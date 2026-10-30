# lunova-deploy

Private tooling so a Lunova developer can deploy any project to the Lunova server with a push, with no server access or SSH key.

```
skills/lunova-deploy/   Claude Code skill (what developers use)
`.github/workflows/deploy.yml`  shared reusable workflow (called by developer repos, tagged v1)
server/lunova-site      server helper: register / release / rollback / status (installed at /usr/local/bin)
```

## For developers: install the skill
```
git clone git@github.com:lunova-digital/lunova-deploy.git ~/lunova-deploy
mkdir -p ~/.claude/skills && ln -s ~/lunova-deploy/skills/lunova-deploy ~/.claude/skills/lunova-deploy
```
Then, inside your project, tell Claude Code: **"deploy this project to Lunova"** (or `/lunova-deploy`).
You need: `gh` logged in with access to your repo, push rights. You do NOT need SSH access, keys or ops rights.

## For ops: setup state
Done: repo `lunova-digital/lunova-deploy` (**public**: it holds no secrets, and public is what lets private repos on the Free plan call it); server platform (PHP 8.3 + FPM pool `lunova`, Composer, Node 22, MariaDB, 4 GB swap); `lunova-site`, `lunova-db`, `lunova-shell` installed; registry `/srv/registry`; the deploy key is locked to `lunova-shell` (forced command, no shell, no PTY).

**Per project (GitHub Free: org secrets do not reach private repos, so secrets are per repo):**
```
ops/lunova-onboard [-p <mgit profile>] owner/repo     # sets LUNOVA_DEPLOY_KEY, LUNOVA_HOST, LUNOVA_HOST_FPR on that repo
```
Run it yourself from the ops machine; the developer never sees the key. The developer (or the skill) then sets the repo secret `LUNOVA_ENV`.
Tag `v1` after changes to the workflow are merged. Reinstall server tools after editing:
`scp server/lunova-site server/lunova-shell lunova:/tmp/ && ssh lunova 'sudo install -m 755 -o root -g root /tmp/lunova-site /tmp/lunova-shell /usr/local/bin/'` (and `server/lunova-db` into `/usr/local/sbin/`).

## Known limits
- The deploy key is shared by all deploying repos. It is restricted to `lunova-site` and rsync into `/srv/sites/*/releases/*`, but anyone who can write a workflow in an onboarded repo can still deploy to any site name. Only onboard repos you trust.
- Sites are bound to the first repo that registers them, but release uploads are not authenticated per repo.
- Upgrading to GitHub Team would allow org-level secrets and a private workflow repo; nothing else would need to change.

## Test status
- `server/lunova-site` + `lunova-db`: tested live as `deploy`: register/release/rollback (healthy-release markers), hook failure leaves the site untouched, failed health check auto-rolls back, repo hijack/duplicate domain/bad name refused, put-env, database provisioning (PDO login over 127.0.0.1), queue worker and scheduler timer, logs, Cloudflare-aware domain check. Full dry run of the real Laravel app (composer install --no-dev, migrate on MariaDB, health 200). Survived a server reboot.
- `.github/workflows/deploy.yml`: YAML valid; **not yet executed on GitHub** (needs `lunova-onboard` run on a repo).
