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

## For ops: how access works (no keys, no secrets, no per-repo setup)
- The shared workflow (public, no secrets) proves its identity with GitHub's **OIDC token**. On the server `lunova-gate` (forced command for runner logins) verifies the signature against GitHub's keys, the audience `lunova`, expiry, that the owner is in `/srv/registry/config.json` `allowed_owners` (**name and numeric id**: `lunova-digital`, `jakiurcore`), and that it was called from `lunova-digital/lunova-deploy/.github/workflows/deploy.yml`. Then only `lunova-site ...` or an rsync into `/srv/sites/<site>/releases/<id>/` of a site bound to that repo and branch can run.
- One-time enablement: `ops/enable-gate` (adds the sshd `AuthorizedKeysCommand` for user `deploy`: any throwaway ed25519 key may open a session, but only into the gate). Undo: remove `/etc/ssh/sshd_config.d/99-lunova.conf` and reload ssh.
- **Allowed owners** are edited in `/srv/registry/config.json`. Gate decisions are logged to `/srv/registry/gate.log`; package installs to `/var/log/lunova-provision.log`.
- **Provisioning**: `lunova-site release` installs missing PHP extensions (from composer's platform check), the DB driver/engine and manifest `packages:` through `sudo lunova-provision` (root helper; refuses system/security/container/web-server packages). Databases are created by `sudo lunova-db ensure <site>` (MariaDB or PostgreSQL); passwords are generated and kept root-side.
- **Sealed env**: `scripts/lunova-seal` encrypts values with the server's public key (`skills/lunova-deploy/seal.pub.pem`; the private key is `/var/lib/lunova/seal/private.pem`, owner deploy, mode 600). The sealed file is committed in the project.
- **Release retention**: after each healthy deploy `lunova-site release` keeps only the last 3 healthy releases (`KEEP = 3`, always including `current`) and deletes the rest, including failed ones.
- Server tools: `server/lunova-site`, `lunova-gate`, `lunova-authkeys` -> `/usr/local/bin`; `lunova-provision`, `lunova-db` -> `/usr/local/sbin`. Reinstall after editing with `scp` + `sudo install -m 755 -o root -g root`. Tag `v2` after workflow changes are merged.

## Known limits
- Anyone who can push to the deploy branch of an allowed-owner repo deploys that site. Protect the branch in GitHub if that matters.
- Owners are trusted: a `packages:` entry or a hook in a repo of an allowed owner runs on the server as that site's deploy.
- GitHub Free: OIDC works on every plan, and a public workflow repo is what lets private repos call it.

## Test status
- Tested live on the server (simulated verified identity): site/repo/branch binding (other repo, other branch and PR refs refused), sealed env (apply once, DB_* refused, wrong repo refused, names-only status), automatic provisioning (PHP DB driver, apt package, `openssh-server` refused), MariaDB and PostgreSQL creation with generated passwords (real TCP login), Laravel env seeding (production defaults, generated APP_KEY, `.env.example` keys), release + health check.
- `lunova-gate` token verification unit-tested: valid token accepted; expired, wrong audience/issuer, owner not allowed, right name but wrong owner id, custom workflow, forged signature and unknown key all refused.
- Earlier (v1 era): rollback with healthy-release markers, hook failure leaves the site untouched, auto-rollback on failed health check, queue worker and scheduler, survived a reboot.
- **Not yet run end to end on GitHub:** v2 needs `ops/enable-gate` on the server and a repo owned by `lunova-digital` or `jakiurcore`.
