# Ops requests (copy-paste messages)

Give the developer the matching message to send to the Lunova ops person. Fill the `<...>`. Ops is rarely needed: keys, secrets, databases, passwords and packages are all handled by the pipeline. Never ask ops for keys.

## 0. Repo owner is not allowed
Not an ops message: the server accepts only repos owned by `lunova-digital` or `jakiurcore`. Tell the developer to transfer (`gh api repos/<owner>/<repo>/transfer -f new_owner=lunova-digital`, needs admin on the repo and org membership) or fork the repo into `lunova-digital`, then continue.

## 1. Move a site to another branch (or rename the repo it is bound to)
> Site `<site>` is bound to `<owner/repo>` branch `<old>`. Please re-bind it to branch `<new>`: edit `branch` in `/srv/registry/sites/<site>.json` (and `repo` if the repo was renamed/transferred).

## 2. Runtime missing (from `mode=check`)
> Site `<site>` (<type>) needs something the pipeline cannot install by itself (`<PHP other than 8.3/8.4/8.5 | Node other than 22 | a package apt refused: name + message>`). Capabilities / error output: `<paste the lines>`.

## 3. DNS
> Please point `<domain>` (and `www.<domain>`) A record to `152.42.168.192`. If the zone is on Cloudflare: set the record to **DNS-only (grey cloud)** until the first HTTPS deploy has issued the certificate, then enable the proxy and set SSL mode to Full (strict). Needed before the first HTTPS deploy.

## 4. Move existing data (cutover from another host, ops-run)
> Site `<site>` currently runs on `<old host>`. Before DNS cutover: (1) put the old site in maintenance mode, (2) `mysqldump` its database and import it into the Lunova database `app_<site with _>` (ops has root access; the app credentials are in the site's shared env), (3) rsync its uploads (`storage/app/public`) into `/srv/sites/<site>/shared/storage/app/public/`, (4) run one deploy, verify with the check run and a test hostname, (5) switch DNS. Keep the old host untouched as the rollback until verified.

## 5. Anything else
Describe what the pipeline could not do and the error text from the workflow log.

## 7. Enable Dockerfile sites (`type: docker`, rootless Docker for `deploy`)
> Please run `ops/setup-docker-rootless` from the lunova-deploy repo against the Lunova server (installs uidmap/slirp4netns, a pinned rootless Docker into ~deploy/bin, the AppArmor user-namespace profile and a `systemd --user` docker service, and installs the current `lunova-site`). `lunova-site capabilities` must then show `docker_rootless: True`.

## 6. Enable containers / allow an image (internal `type: service`)
> Please run `ops/setup-containers` from the lunova-deploy repo against the Lunova server (installs Docker, the `lunova-container` helper and the sudo rule, and creates `/etc/lunova/containers.json`). Allowed image(s) needed: `<image name without the tag, e.g. bbernhard/signal-cli-rest-api>`. Expected memory use: `<memory_mb>` MB. `mode=check` should then list `containers: True`.

## 8. Enable wildcard tenancy, backups, reset-db and bootstrap-admin (v10)
> Please run `ops/setup-tenancy` from the lunova-deploy repo against the Lunova server (installs `lunova-priv` and one sudoers line for `deploy`, the v10 `lunova-site` and `lunova-gate`, `/etc/caddy/certs`, `/srv/backups`, `/var/lib/lunova/secrets`, and `mysqldump`). Afterwards `sudo -u deploy sudo -n /usr/local/sbin/lunova-priv validate` should print a valid Caddy config.
