# lunova-deploy

Private tooling so a Lunova developer can deploy any project to the Lunova server with a push, with no server access or SSH key.

```
skills/lunova-deploy/   Claude Code skill (what developers use)
`.github/workflows/deploy.yml`  shared reusable workflow (called by developer repos, tagged v1)
server/lunova-site      server helper: register / release / rollback / status (installed at /usr/local/bin)
server/lunova-container root helper that runs an allow-listed container for `type: service` sites (installed at /usr/local/sbin)
ops/setup-containers    one-time ops script: Docker + the helper + the image allow-list
ops/setup-docker-rootless  one-time ops script: rootless Docker for `deploy` (type: docker sites) + installs lunova-site
tests/                  offline tests: python3 -m unittest discover -s tests
```

## For developers: install the skill
```
git clone git@github.com:lunova-digital/lunova-deploy.git ~/lunova-deploy
mkdir -p ~/.claude/skills && ln -s ~/lunova-deploy/skills/lunova-deploy ~/.claude/skills/lunova-deploy
```
Then, inside your project, tell Claude Code: **"deploy this project to Lunova"** (or `/lunova-deploy`).
You need: `gh` logged in with access to your repo, push rights. You do NOT need SSH access, keys or ops rights.

## For ops: how access works (no keys, no secrets, no per-repo setup)
- The shared workflow (public, no secrets) proves its identity with GitHub's **OIDC token**. On the server `lunova-gate` (forced command for runner logins) verifies the signature against GitHub's keys, the audience `lunova`, expiry, that the owner is in `/srv/registry/config.json` `allowed_owners` (**name and numeric id**: `lunova-digital`, `jakiurcore`), and that it was called from `lunova-digital/lunova-deploy/.github/workflows/deploy.yml`. Then only `lunova-site ...` or an rsync into `/srv/sites/<site>/releases/<id>/` of a site bound to that repo and branch can run.
- One-time enablement: `ops/enable-gate` (adds the sshd `AuthorizedKeysCommand` for user `deploy`: any throwaway ed25519 key may open a session, but only into the gate). Undo: remove `/etc/ssh/sshd_config.d/99-lunova.conf` and reload ssh.
- **Allowed owners** are edited in `/srv/registry/config.json`. Gate decisions are logged to `/srv/registry/gate.log`; package installs to `/var/log/lunova-provision.log`.
- **Provisioning**: `lunova-site release` installs missing PHP extensions (from composer's platform check), the DB driver/engine and manifest `packages:` through `sudo lunova-provision` (root helper; refuses system/security/container/web-server packages). Databases are created by `sudo lunova-db ensure <site>` (MariaDB or PostgreSQL); passwords are generated and kept root-side.
- **Sealed env**: `scripts/lunova-seal` encrypts values with the server's public key (`skills/lunova-deploy/seal.pub.pem`; the private key is `/var/lib/lunova/seal/private.pem`, owner deploy, mode 600). The sealed file is committed in the project.
- **Release retention**: after each healthy deploy `lunova-site release` keeps only the last 3 healthy releases (`KEEP = 3`, always including `current`) and deletes the rest, including failed ones.
- Server tools: `server/lunova-site`, `lunova-gate`, `lunova-authkeys` -> `/usr/local/bin`; `lunova-provision`, `lunova-db` -> `/usr/local/sbin`. Reinstall after editing with `scp` + `sudo install -m 755 -o root -g root`. Tag `v2` after workflow changes are merged.

## Dockerfile sites (v8: `type: docker`)
A normal public site (domain, TLS via Caddy) whose app is a container built from the project's own Dockerfile. The image is built **in CI**, shipped as `image.tar.gz` through the existing gate/rsync path (no gate change), loaded on the server and run in a **rootless** Docker daemon owned by `deploy` (`ops/setup-docker-rootless`; a container escape is `deploy`, not root, and this is separate from the root daemon of `type: service`). Caddy reverse-proxies the domain to `127.0.0.1:<auto port>`. Manifest: `container_port` (required), `dockerfile`, `context`, `env`, `volumes` (named only), `memory_mb`. Archive must contain exactly `lunova-<site>:<release>`; container runs with `no-new-privileges`, a memory limit and pids limit; env/secrets are passed via the process environment, never argv or disk. Failed start/health check restores the previous container. `database:` is refused. Offline tests: `tests/test_docker.py`. **Not yet run against a real rootless daemon** until `ops/setup-docker-rootless` has been run.

## Internal services (v8: `type: service`)
A site can be an **internal container** instead of a web site: no domain, no certificate, no Caddy entry. It is published on `127.0.0.1:<host_port>` only, so only things on the same server (the hub) can call it. First user: the Signal gateway (`lunova-digital/lunova-signal-gateway`).
- Manifest keys: `image` (exact tag, never `latest`), `container_port`, `host_port`, `env`, `volumes`, `memory_mb`, `health_path`. See `skills/lunova-deploy/references/manifest.md`.
- **Docker is root-equivalent, so `deploy` never gets it.** `lunova-site` calls `sudo lunova-container up|down|status|logs <site>`, a root helper that re-validates everything against `/etc/lunova/containers.json` (editable by root only): image must be on the allow-list and pinned; ports are loopback-only; memory capped; no host mounts (named volumes only); fixed small capability set; no privileged mode, no host network.
- A release is the container configuration (`.lunova-service.json` inside the release). Deploy = start, health-check, switch; any failure restarts the previous configuration. An unchanged configuration never restarts the container (a README-only push is harmless). Rollback and `status`/`logs` work as for other sites. `unregister` stops the container and keeps its data volumes.
- Enable once: `ops/setup-containers [host] [image...]` (it also installs the v8 `lunova-site`; until that is installed on the server a `type: service` deploy stops at `register: the following arguments are required: --domains`, which is how you recognise the old tool). To allow another image, ops add it to `allowed_images`.
- **Public admin name (v9, optional `public:`)**: a service may publish only the allow-listed admin paths (`/v1/qrcodelink`, `/v1/register`, `/v1/accounts`, `/v1/about`, `/v1/health`) on an HTTPS name, behind basic auth (user from the manifest, password = sealed `LUNOVA_PUBLIC_PASSWORD`, hashed on the server with `caddy hash-password`; only the hash is written to the Caddy file). Any other path is a 404, so message sending/receiving can never be reached from outside. `lunova-site` enforces the path allow-list server-side, not just the manifest.
- Secrets for a service travel as sealed env like any site; they are written to a root-only temp env-file for `docker run` and removed.

## Known limits
- Anyone who can push to the deploy branch of an allowed-owner repo deploys that site. Protect the branch in GitHub if that matters.
- Owners are trusted: a `packages:` entry or a hook in a repo of an allowed owner runs on the server as that site's deploy.
- GitHub Free: OIDC works on every plan, and a public workflow repo is what lets private repos call it.

## Test status
- v8 service sites: `tests/` (offline): allow-list and spec validation, health on the host port, switch and mark on success, previous configuration restored on a failed start or failed health check, no domain accepted. **Not yet run against a real Docker host** and the `yq` expressions in the workflow's service branch are untested on GitHub; the first real deploy is the test (use `mode=check` first).
- Tested live on the server (simulated verified identity): site/repo/branch binding (other repo, other branch and PR refs refused), sealed env (apply once, DB_* refused, wrong repo refused, names-only status), automatic provisioning (PHP DB driver, apt package, `openssh-server` refused), MariaDB and PostgreSQL creation with generated passwords (real TCP login), Laravel env seeding (production defaults, generated APP_KEY, `.env.example` keys), release + health check.
- `lunova-gate` token verification unit-tested: valid token accepted; expired, wrong audience/issuer, owner not allowed, right name but wrong owner id, custom workflow, forged signature and unknown key all refused.
- Earlier (v1 era): rollback with healthy-release markers, hook failure leaves the site untouched, auto-rollback on failed health check, queue worker and scheduler, survived a reboot.
- **Not yet run end to end on GitHub:** v2 needs `ops/enable-gate` on the server and a repo owned by `lunova-digital` or `jakiurcore`.
