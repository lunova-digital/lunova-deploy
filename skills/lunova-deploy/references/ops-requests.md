# Ops requests (copy-paste messages)

Give the developer the matching message to send to the Lunova ops person. Fill the `<...>`. Never ask ops for keys: ops sets org-level secrets, developers never receive them.

## 0. One-time Lunova setup (only if the org repo/secret/variables are missing)
> Please set up the shared deploy workflow for our org: (1) create `<ORG>/lunova-deploy` with `.github/workflows/deploy.yml` from the lunova-deploy repo and tag `v1`; allow other org repos to use it (Actions > General > Access); (2) org secret `LUNOVA_DEPLOY_KEY` (private key of the server's `deploy` user) shared with the repos that deploy; (3) org variables `LUNOVA_HOST=152.42.168.192` and `LUNOVA_HOST_FPR=<fingerprint from config.yml>`.

## 1. Repo cannot see the org secrets/variables
> Repo `<org/repo>` needs access to org secret `LUNOVA_DEPLOY_KEY` and variables `LUNOVA_HOST`, `LUNOVA_HOST_FPR` (and permission to call `<ORG>/lunova-deploy`).

## 2. Runtime missing (from `mode=check`)
> Site `<site>` (<type>) needs `<php 8.3 + FPM pool 'lunova' as user deploy, socket /run/php/lunova.sock, composer | node <version> | ...>` on the Lunova server. Capabilities output: `<paste the capabilities lines>`.

## 3. DNS
> Please point `<domain>` (and `www.<domain>`) A record to `152.42.168.192`. If the zone is on Cloudflare: set the record to **DNS-only (grey cloud)** until the first HTTPS deploy has issued the certificate, then enable the proxy and set SSL mode to Full (strict). Needed before the first HTTPS deploy.

## 4. Move existing data (cutover from another host, ops-run)
> Site `<site>` currently runs on `<old host>`. Before DNS cutover: (1) put the old site in maintenance mode, (2) `mysqldump` its database and import it into the Lunova database `app_<site with _>` (ops has root access; the app credentials are in the site's shared env), (3) rsync its uploads (`storage/app/public`) into `/srv/sites/<site>/shared/storage/app/public/`, (4) run one deploy, verify with the check run and a test hostname, (5) switch DNS. Keep the old host untouched as the rollback until verified.

## 5. Anything else
Describe what the pipeline could not do and the error text from the workflow log.
