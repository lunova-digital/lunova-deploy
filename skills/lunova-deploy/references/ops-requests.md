# Ops requests (copy-paste messages)

Give the developer the matching message to send to the Lunova ops person. Fill the `<...>`. Never ask ops for keys: ops sets the repo's secret, developers never receive it.

## 0. / 1. Repo is not onboarded (missing LUNOVA_DEPLOY_KEY / LUNOVA_HOST / LUNOVA_HOST_FPR)
> Please onboard `<owner/repo>` for Lunova deploys: run `lunova-deploy/ops/lunova-onboard <owner/repo>` (it sets repo secret `LUNOVA_DEPLOY_KEY` and variables `LUNOVA_HOST`, `LUNOVA_HOST_FPR`). The repo's admin must be able to add secrets, and the repo may be private.

## 2. Runtime missing (from `mode=check`)
> Site `<site>` (<type>) needs `<php 8.3 + FPM pool 'lunova' as user deploy, socket /run/php/lunova.sock, composer | node <version> | ...>` on the Lunova server. Capabilities output: `<paste the capabilities lines>`.

## 3. DNS
> Please point `<domain>` (and `www.<domain>`) A record to `152.42.168.192`. If the zone is on Cloudflare: set the record to **DNS-only (grey cloud)** until the first HTTPS deploy has issued the certificate, then enable the proxy and set SSL mode to Full (strict). Needed before the first HTTPS deploy.

## 4. Move existing data (cutover from another host, ops-run)
> Site `<site>` currently runs on `<old host>`. Before DNS cutover: (1) put the old site in maintenance mode, (2) `mysqldump` its database and import it into the Lunova database `app_<site with _>` (ops has root access; the app credentials are in the site's shared env), (3) rsync its uploads (`storage/app/public`) into `/srv/sites/<site>/shared/storage/app/public/`, (4) run one deploy, verify with the check run and a test hostname, (5) switch DNS. Keep the old host untouched as the rollback until verified.

## 5. Anything else
Describe what the pipeline could not do and the error text from the workflow log.
