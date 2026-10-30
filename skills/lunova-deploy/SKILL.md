---
name: lunova-deploy
description: Deploy a project to the Lunova server with one push. Use when a Lunova developer wants to deploy, ship, host, set up CI/CD, migrate an existing deploy (FTP, rsync, other host) to Lunova, check a Lunova deployment, or roll one back. Works without any SSH key or server access; it audits the project, interviews the developer, generates the pipeline, pushes it and verifies the live site. Lunova-internal only.
---

# Lunova deploy

You are helping a **Lunova developer who has no server access, no SSH key and no ops rights**. They want their project live on the Lunova server by pushing code. You discover the project, show them how it deploys today, agree the target setup with them, generate the pipeline, push it, watch it run and verify the live site.

Read `config.yml` (server facts) and `references/manifest.md` (the `.lunova.yml` format) before generating anything. Read `references/stacks.md` for the project's tech and `references/ops-requests.md` when something needs ops.

## How deployment works (the target design)

```
developer push  ->  GitHub Actions (their repo)  ->  shared workflow <workflow_repo>
                    builds + uploads over SSH as the `deploy` user (repo secret set by ops, they never see it)
                    -> lunova-site on the server: register, release, health check, auto-rollback
```

- The developer's repo contains only two files: `.lunova.yml` (what the site is) and `.github/workflows/lunova-deploy.yml` (a ~20 line caller).
- Ops onboards each repo once (`ops/lunova-onboard`), which sets the repo secret `LUNOVA_DEPLOY_KEY` and variables `LUNOVA_HOST`, `LUNOVA_HOST_FPR` (GitHub Free has no org secrets for private repos). The key only works for `lunova-site` and rsync into releases. The repo-level secret `LUNOVA_ENV` holds the app's production `.env`.
- Every deploy is an immutable release. A failed hook or failed health check leaves the live site untouched or rolls back automatically. Manual rollback is one workflow run.

## Hard rules

1. **Never ask for, accept, create or look for SSH keys, tokens or passwords. Never SSH to the server.** If the developer offers a key, decline and explain that the pipeline holds it. Everything server-side goes through the shared workflow.
2. **Secrets are never printed, committed or put in files in the repo.** Read `.env` files only to list variable *names*. Set secrets with `gh secret set` from a file/stdin, never on a command line. Ask before setting any secret.
3. **Anything outside the pipeline's reach is an ops request** (installing PHP/Node/databases, DNS you cannot edit, repo onboarding, firewall). Stop, generate the ready-to-send message from `references/ops-requests.md`, give it to the developer, and continue only after they confirm ops did it. Do not invent workarounds.
4. **Ask before every outward action**: pushing a branch, opening/merging a PR, setting a secret, disabling the old deploy workflow, running a deployment. Merging to the deploy branch deploys to production.
5. Do not delete the developer's existing deploy setup. Disable it only after the first Lunova deploy is verified, and only with their yes.

## Process

### 1. Discover (read-only, no questions yet)
Inspect the repo and report facts, not guesses:
- **Stack**: `composer.json` (Laravel? PHP version, extensions), `package.json` (framework, build script, node engine), `requirements.txt`/`pyproject.toml`, `Dockerfile`, static `index.html`.
- **Current deploy approach**: `.github/workflows/*`, `deploy*` scripts, `Procfile`, `vercel.json`/`netlify.toml`/`fly.toml`, FTP/rsync/SSH actions, CI config of other providers. Say *how* it deploys today (trigger branch, mechanism, target host), whether `vendor/`, `node_modules` or built assets are built in CI or committed, and whether it runs migrations.
- **Runtime needs**: database (from `.env.example` / config), queue worker (`ShouldQueue`, `QUEUE_CONNECTION`), scheduler (`routes/console.php`), file uploads/storage, websockets, long-running processes, mail, required env var **names**. Lunova provides DB, queue worker and scheduler automatically via `.lunova.yml` (`database: mysql`, `queue: true`, `scheduler: true`).
- **PHP platform**: for Laravel/PHP, check `composer.lock` is installable on the server's PHP (8.3): `config.platform.php` must be set; otherwise plan to add it and re-resolve (see `references/stacks.md`).
- **Onboarding**: the repo can live in any org or account; ops must have run `lunova-onboard` on it. Check with `gh secret list` and `gh variable list` (names only); if missing, ops request #0.
- **Risks found**: secrets or passwords committed (in workflows, `.env`), plaintext FTP, no rollback, no health check, debug mode, missing build step. Quote the file and line, never the secret value.
- **Git**: remote, current branch, default branch, whether `gh` is authenticated (`gh auth status`) and can see the repo.

### 2. Show "how it deploys today" and the plan
Give the developer a short, plain summary:
- **Today**: one paragraph + the risks.
- **On Lunova**: site type, what runs where, the two files you will add, what changes for them (push to `<branch>` deploys; rollback is a workflow run).
- **Blockers needing ops** (from step 4), if any.

### 3. Interview (AskUserQuestion, one batch, with defaults)
Ask only what you cannot infer: site name (suggest from repo name), production domain(s) (and whether DNS A record points to the server IP in `config.yml` or they need ops/IT to set it), deploy branch, app environment (offer to build `LUNOVA_ENV` from their local `.env.production`/`.env` for them to review; DB_* are not needed, the server injects them), whether there is **existing production data to move** from another host (if yes it is an ops-run cutover: `references/ops-requests.md` #4), anything ambiguous found in discovery (queues, uploads, scheduler).

### 4. Preflight
- Check the org workflow repo from `config.yml` exists and is reachable: `gh repo view <workflow_repo>`. If `workflow_repo` still says `REPLACE_ORG`, or the repo lacks `LUNOVA_DEPLOY_KEY`/`LUNOVA_HOST`/`LUNOVA_HOST_FPR`, that is an ops request (one-time Lunova setup).
- After the files exist (step 5), run the **check** mode to read the server's real capabilities and domain status without deploying. `workflow_dispatch` only works for workflows on the default branch, so before the first merge the check runs automatically on the **pull request** (the caller template maps `pull_request` to `mode=check`): open the PR, then `gh run watch` and read the log. After the first merge, `gh workflow run lunova-deploy.yml -f mode=check` also works. Compare `capabilities` with `references/stacks.md`: missing runtime/DB/FPM socket = ops request. DNS problems = ask the developer to fix DNS, or `http_only: true` for a temporary test.

### 5. Generate (show the files before writing)
- `.lunova.yml` from `templates/lunova.yml`, filled from discovery and answers, following `references/manifest.md` and the stack recipe.
- `.github/workflows/lunova-deploy.yml` from `templates/lunova-deploy.yml`, replacing `__BRANCH__`, `__WORKFLOW_REPO__`, `__WORKFLOW_REF__` from `config.yml`.
- Do **not** touch the old deploy workflow yet unless the developer already asked to remove it. Work on a new branch `lunova-deploy`.
- Offer to set `LUNOVA_ENV` (`gh secret set LUNOVA_ENV < file`): build the file from the real `.env` with production-appropriate values (APP_ENV=production, APP_DEBUG=false, correct APP_URL, a generated APP_KEY only if absent). Show only variable names and which ones need the developer's input. Delete any temp file after.

### 6. Push and verify
1. With approval: commit, push the `lunova-deploy` branch, open a PR. The PR run is the preflight; push fixes to the branch to rerun it.
2. With approval: merge to the deploy branch (this deploys), or run `gh workflow run lunova-deploy.yml` on the branch for a first deploy.
3. Watch: `gh run list`, `gh run watch <id>`, show the failing step's log (`gh run view <id> --log-failed`) and diagnose. Typical causes are in `references/troubleshooting.md`.
4. Verify the live site yourself: `curl -sI https://<domain>` (status, TLS), fetch the home page, check an app-specific route, and report the result. For Laravel also confirm no debug output and that login/queue-dependent pages work if they can be tested.
5. Only now offer to disable the old deploy workflow (with the developer's yes), and to remove committed secrets (explain that old secrets stay in git history and must be rotated).

### 7. Day-2 help
- Deploy: push to the deploy branch. Check: `gh workflow run lunova-deploy.yml -f mode=check`.
- Roll back: `gh workflow run lunova-deploy.yml -f mode=rollback` (previous release) or `-f rollback_to=<release id>`.
- Status / logs (no server access needed): `gh workflow run lunova-deploy.yml -f mode=status` and `-f mode=logs` (optional `-f lines=200`), then `gh run watch` and read the job log. Server-level logs (Caddy, system) need ops.

## Output style
Plain language for the developer. Short summaries, concrete next step at the end of each phase. When you need something from ops, give them one copy-pasteable message, not a lecture.
