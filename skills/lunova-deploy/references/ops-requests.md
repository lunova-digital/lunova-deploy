# Ops requests (copy-paste messages)

Give the developer the matching message to send to the Lunova ops person. Fill the `<...>`. Never ask ops for keys: ops sets org-level secrets, developers never receive them.

## 0. One-time Lunova setup (if `workflow_repo` is still REPLACE_ORG or org secrets are missing)
> Please set up the shared deploy workflow for our org: (1) create `<ORG>/lunova-deploy` with `.github/workflows/deploy.yml` from the lunova-deploy repo and tag `v1`; allow other org repos to use it (Actions > General > Access); (2) org secret `LUNOVA_DEPLOY_KEY` (private key of the server's `deploy` user) shared with the repos that deploy; (3) org variables `LUNOVA_HOST=152.42.168.192` and `LUNOVA_HOST_FPR=<fingerprint from config.yml>`.

## 1. Repo cannot see the org secrets/variables
> Repo `<org/repo>` needs access to org secret `LUNOVA_DEPLOY_KEY` and variables `LUNOVA_HOST`, `LUNOVA_HOST_FPR` (and permission to call `<ORG>/lunova-deploy`).

## 2. Runtime missing (from `mode=check`)
> Site `<site>` (<type>) needs `<php 8.3 + FPM pool 'lunova' as user deploy, socket /run/php/lunova.sock, composer | node <version> | ...>` on the Lunova server. Capabilities output: `<paste the capabilities lines>`.

## 3. Database
> Site `<site>` needs a `<mysql|postgres>` database and user. Please create `<db_name>` with user `<db_user>` (local access only) and send the password to `<developer>` privately.

## 4. DNS
> Please point `<domain>` A record to `152.42.168.192` (TTL low). Needed before the first HTTPS deploy.

## 5. Scheduler / queue worker
> Site `<site>` needs `<php artisan schedule:run every minute | a queue worker service>` running as user `deploy` in `/srv/sites/<site>/current`.

## 6. Anything else
Describe what the pipeline could not do and the error text from the workflow log.
