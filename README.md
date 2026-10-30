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
Done: repo `lunova-digital/lunova-deploy` (private); server platform (PHP 8.3 + FPM pool `lunova`, Composer, Node 22, MariaDB); `lunova-site` and `lunova-db` installed (`/usr/local/bin`, `/usr/local/sbin`) with sudoers for `deploy`; registry `/srv/registry`.
Still needed once (GitHub Free plan: verify these work for private repos, see Known limits):
1. Org secret `LUNOVA_DEPLOY_KEY` = private key of the server's `deploy` user (`~/.ssh/lunova_deploy` on the ops machine), visibility `private` (or selected repos).
2. Org variables `LUNOVA_HOST=152.42.168.192`, `LUNOVA_HOST_FPR=SHA256:TwC/N1cK5ZgCM/3hfEKe24DWoYtpBsmU/PdPrnOHV3s`.
3. Settings > Actions > General > Access: allow repositories in the organization to use workflows from this repo.
4. Tag `v1` after changes to the workflow are merged.
Reinstall server tools after editing: `scp server/lunova-site server/lunova-db lunova:/tmp/ && ssh lunova 'sudo install -m 755 -o root -g root /tmp/lunova-site /usr/local/bin/ && sudo install -m 755 -o root -g root /tmp/lunova-db /usr/local/sbin/'`.

## Known limits
- The deploy key is shared by all deploying repos. Anyone who can write a workflow in a repo with access can use it. Acceptable for a private team; tighten later with an SSH forced command that only allows `lunova-site` and rsync into `/srv/sites/*/releases`.
- Sites are bound to the first repo that registers them, but release uploads are not authenticated per repo.
- GitHub Free: org secrets for private repos and sharing workflows from a private repo may require a paid plan. If the first run reports the secret/workflow is not accessible, either upgrade the org plan or set `LUNOVA_DEPLOY_KEY` per repo and make `lunova-deploy` public (it contains no secrets, only the server IP and host fingerprint).

## Test status
- `server/lunova-site` + `lunova-db`: tested live as `deploy`: register/release/rollback (healthy-release markers), hook failure leaves the site untouched, failed health check auto-rolls back, repo hijack/duplicate domain/bad name refused, put-env, database provisioning (PDO login over 127.0.0.1), queue worker and scheduler timer, logs, Cloudflare-aware domain check. Full dry run of the real Laravel app (composer install --no-dev, migrate on MariaDB, health 200). Survived a server reboot.
- `.github/workflows/deploy.yml`: YAML valid; **not yet executed on GitHub** (needs the org secret and variables).
