# lunova-deploy

Private tooling so a Lunova developer can deploy any project to the Lunova server with a push, with no server access or SSH key.

```
skills/lunova-deploy/   Claude Code skill (what developers use)
workflows/deploy.yml    shared GitHub Actions workflow (lives in <ORG>/lunova-deploy at .github/workflows/)
server/lunova-site      server helper: register / release / rollback / status (installed at /usr/local/bin)
```

## For developers: install the skill
```
git clone git@github.com:<ORG>/lunova-deploy.git ~/lunova-deploy
mkdir -p ~/.claude/skills && ln -s ~/lunova-deploy/skills/lunova-deploy ~/.claude/skills/lunova-deploy
```
Then, inside your project, tell Claude Code: **"deploy this project to Lunova"** (or `/lunova-deploy`).
You need: `gh` logged in with access to your repo, push rights. You do NOT need SSH access, keys or ops rights.

## For ops: one-time setup
1. Create `<ORG>/lunova-deploy` (this repo). Put the workflow at `.github/workflows/deploy.yml` (copy `workflows/deploy.yml`), tag `v1`.
   Settings > Actions > General > Access: allow repositories in the organization to use it.
2. Org secret `LUNOVA_DEPLOY_KEY`: private key of the server `deploy` user (`~/.ssh/lunova_deploy` on the ops machine). Share it with the repos that deploy.
3. Org variables: `LUNOVA_HOST=152.42.168.192`, `LUNOVA_HOST_FPR=SHA256:TwC/N1cK5ZgCM/3hfEKe24DWoYtpBsmU/PdPrnOHV3s`.
4. In `skills/lunova-deploy/config.yml` replace `REPLACE_ORG`.
5. Server helper: `scp server/lunova-site lunova:/tmp/ && ssh lunova 'sudo install -m 755 -o root -g root /tmp/lunova-site /usr/local/bin/lunova-site'`. Registry: `/srv/registry` (owned by `deploy`) with `config.json` `{"public_ip": "...", "php_socket": "/run/php/lunova.sock"}`.
6. Runtimes as projects need them (see `skills/lunova-deploy/references/stacks.md`): PHP-FPM pool `lunova`, Node, databases.

## Known limits
- The deploy key is shared by all deploying repos. Anyone who can write a workflow in a repo with access can use it. Acceptable for a private team; tighten later with an SSH forced command that only allows `lunova-site` and rsync into `/srv/sites/*/releases`.
- Sites are bound to the first repo that registers them, but release uploads are not authenticated per repo.
- The shared workflow has not run on GitHub yet (see test status below).

## Test status
- `server/lunova-site`: tested on the live server as `deploy` (register, release, rollback, hook failure leaves the site untouched, failed health check auto-rolls back, repo hijack/duplicate domain/bad name refused, put-env).
- `workflows/deploy.yml`: YAML valid; **not yet executed on GitHub** (needs the org repo, secret and variables above).
