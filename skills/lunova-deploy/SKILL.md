---
name: lunova-deploy
description: Deploy a project to the Lunova server with one push. Use when a Lunova developer wants to deploy, ship, host, set up CI/CD, migrate an existing deploy (FTP, rsync, other host) to Lunova, update production environment values, check a Lunova deployment, or roll one back. Needs no SSH key, server access, GitHub secret or ops help; it reads the project, asks a few questions, builds the pipeline, pushes it and hands over a link. Lunova-internal only.
---

# Lunova deploy

The developer cloned a project, opened Claude Code and said "deploy it". They have **no server access, no key, no ops rights**, and should never need any. Your job: read the project, ask only what you cannot infer, build the pipeline, push it once they agree, give them the Actions link and leave them alone.

Read `config.yml` (server facts), `references/manifest.md` (`.lunova.yml`) and `references/stacks.md` (per-stack recipes) before generating anything.

## How it works (so you can explain it in one breath)

```
git push -> GitHub Actions runs the shared workflow lunova-digital/lunova-deploy@v2
         -> proves its identity to the server with GitHub's own OIDC token (no key, no secret)
         -> server: registers the site, installs missing packages, creates the database + user + password,
            builds .env, uploads the release, runs hooks, health-checks, switches, auto-rolls back on failure
```

- The repo gets two files, `.lunova.yml` and `.github/workflows/lunova-deploy.yml`, plus `.lunova/env.sealed` when environment values were provided.
- **The server accepts only repositories owned by `lunova-digital` or `jakiurcore`**, running the shared workflow. A site is bound to the repo and branch that first deployed it.
- **Database**: the developer only picks the engine. The server creates the database and user and generates the password; it is injected as `DB_*`. Never ask for DB name, user or password.
- **Packages**: PHP extensions (from `composer.lock`), the database engine and its driver are installed automatically. Extra apt packages go in `packages:` in `.lunova.yml`. System/security/container/web-server packages are refused.
- **Environment**: the server builds `.env` from sealed values, defaults, `.env.example` and the generated DB credentials. No GitHub secret is involved.

## Hard rules

1. **Never ask for, accept, create or look for SSH keys, tokens, passwords or GitHub secrets. Never SSH to the server.** If offered a key, decline: the pipeline needs none.
2. **Environment values are only ever sealed.** Take a value from the developer, pass it to `scripts/lunova-seal` on stdin, never put it in argv, a repo file in plaintext, a commit message or your replies. Never echo values back; refer to names. Read `.env` files only to list names. Delete any temp file.
3. **Ask before every outward action once**, in plain words, then do the whole sequence without nagging: (a) pushing a branch that will auto-deploy, (b) disabling an old deploy. Do not delete the old deploy setup unless they said yes.
4. **Repo owner gate**: the GitHub owner of `origin` must be `lunova-digital` or `jakiurcore`. Otherwise stop and tell them to transfer or fork the repo into `lunova-digital` (give the exact `gh repo transfer`/fork command); do not work around it.
5. Anything the pipeline cannot do is an ops request (DNS they do not control, a PHP version other than 8.3, a package apt refuses). Give them the ready message from `references/ops-requests.md`. Do not invent workarounds.
6. Once the push is done, **do not keep checking in**. Give the link, say what to expect, stop.

## Process

### 1. Discover (read-only, no questions yet)
- **Owner gate** (rule 4): `git remote get-url origin`, `gh repo view --json owner,isPrivate,defaultBranchRef`. Also `gh auth status` (they need push rights to the repo; nothing else).
- **Stack**: `composer.json` (Laravel? `ext-*`, PHP), `package.json` (framework, build script, node engine), `requirements.txt`/`pyproject.toml`, static `index.html`. Pick the site type from `references/stacks.md`.
- **Runtime needs**: `.env.example` names, `DB_CONNECTION` default and `config/database.php`, queue (`QUEUE_CONNECTION`, jobs), scheduler (`routes/console.php` / `Kernel`), uploads (`storage/app/public`), anything needing extra apt packages (imagemagick, ffmpeg, pdf tools).
- **Today's deploy**: `.github/workflows/*`, deploy scripts, FTP/rsync/SSH actions, other hosts. Note risks (plaintext credentials in workflows: quote file and line, never the value).
- **Branches**: `git branch -r`, default branch, any of main/master/develop/rhodium/laravel/production.

### 2. Interview (AskUserQuestion, one batch, inferred defaults pre-selected)
Ask only what you cannot infer:
- **Site name** (suggest from the repo name) and **production domain(s)**. If DNS is not pointed at `server_ip` yet, tell them to ask whoever controls DNS (message in `references/ops-requests.md` #3); the deploy does not wait for it.
- **Database**: mysql (default for Laravel), postgres, sqlite, or none. Pre-select what you detected.
- **Queue worker / scheduler** (Laravel), only if the code uses them.
- **Deploy branch**: offer the branches you found, default branch first. State the consequence in the question: "Every push to `<branch>` will automatically deploy to https://<domain>. OK, or use a different branch?" If they pick a new branch name, create it from the current one.
- **Old deploy workflow**: disable it after the first successful Lunova deploy? (yes/no)
- **Environment values**: list the names from `.env.example` that need a human value and have no safe default (mail, third-party APIs, payment, analytics). Do not list `APP_*` basics, `DB_*`, cache/queue/session drivers. Ask whether they want to enter them now or later; entering later is a normal one-liner.

### 3. Generate (show the files, then write them)
- `.lunova.yml` from `templates/lunova.yml`, following `references/manifest.md` and the stack recipe.
- `.github/workflows/lunova-deploy.yml` from `templates/lunova-deploy.yml` (`__BRANCH__`, `__WORKFLOW_REPO__`, `__WORKFLOW_REF__` from `config.yml`).
- If values were provided: `printf '%s' '{"set": {...}}' | scripts/lunova-seal --site <site> --repo <owner/repo>` writes `.lunova/env.sealed` (safe to commit). Build the JSON with a heredoc or python, not in a command line. Never print it.
- Work on a branch `lunova-deploy`; if the developer chose a deploy branch that does not exist yet, create it.

### 4. Publish (one confirmation, then go)
Tell them in two lines what will happen and ask once: "I will commit these files and push to `<branch>`. From then on every push to `<branch>` deploys to https://<domain>. Go?" On yes: commit, push the deploy branch (merge the `lunova-deploy` branch into it if that is how their flow works; ask nothing more), then:
1. Get the run: `gh run list --workflow lunova-deploy.yml --limit 1 --json url,status` (retry briefly until it exists).
2. Say, and stop:
   > Deploying now. It takes about 3 to 6 minutes. Watch it here: <run url>. When the run is green the site is live at https://<domain>. Rolling back is automatic if it fails. Ask me to "check the deploy" any time.

### 5. When they come back ("check it", "did it work?")
`gh run view <id>` and, if it failed, `gh run view <id> --log-failed`; diagnose with `references/troubleshooting.md`. On success `curl -sI https://<domain>` and a page fetch, then report. Offer to disable the old deploy workflow (only if they said yes earlier) and to remove committed secrets from old workflows (they stay in git history: say they must rotate them).

### 6. Day-2
- **Change an environment value** ("set RESEND_KEY", "change the payment number"): ask only for the name and value; `printf` the JSON to `scripts/lunova-seal` (only that key; other keys on the server are kept); commit `.lunova/env.sealed` and push to the deploy branch. Tell them it deploys on push (one sentence, no extra confirmation if they already agreed to auto-deploy). To remove a key use `"unset": [...]`.
- **See what is set** (names only, never values): `gh workflow run lunova-deploy.yml -f mode=status`, then read the run log.
- **Roll back**: `gh workflow run lunova-deploy.yml -f mode=rollback` (previous healthy release) or `-f rollback_to=<release id>`. **Logs**: `-f mode=logs`. **Preflight without deploying**: `-f mode=check`. (`workflow_dispatch` works only once the workflow file is on the default branch.)
- A new release can only come from the branch the site was registered with. To move a site to another branch is an ops request.

## Output style
Plain language, short. Name the next step at the end of each phase. No secret values anywhere. One ops message, copy-pasteable, when ops is needed.
