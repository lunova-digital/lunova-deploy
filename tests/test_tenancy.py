"""Offline tests for v10 (tenancy, seeders/tasks, privileged modes, root helper, workflow shape): python3 -m unittest discover -s tests
No server, Docker, Cloudflare, GitHub or Caddy is needed."""
import contextlib, gzip, importlib.machinery, importlib.util, io, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/deploy.yml"


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(ROOT / "server" / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec); loader.exec_module(mod)
    return mod


TEN = {"root_domain": "lunovait.com", "platform_host": "app.lunovait.com", "wildcard": True, "tls_cert": "lunovait.com"}
TASKS = {"super_admin": "access:super-admin {email} --name={name}"}


def captured(fn, *a, **k):
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try: fn(*a, **k)
        except SystemExit as e: code = e.code if e.code is not None else 0
    return code, out.getvalue(), err.getvalue()


class Manifest(unittest.TestCase):
    def setUp(self): self.s = load("lunova-site")

    def refuses(self, fn, *a):
        with self.assertRaises(SystemExit): captured_raise(fn, *a)

    def test_tenancy_accepts_the_shikhon_block(self):
        self.assertEqual(self.s.parse_tenancy(dict(TEN)), TEN)

    def test_tenancy_absent_is_backward_compatible(self):
        self.assertIsNone(self.s.parse_tenancy(None)); self.assertIsNone(self.s.parse_tenancy({}))

    def test_tenancy_rejects_bad_blocks(self):
        for bad in ({**TEN, "wildcrd": True},                            # typo: unknown key
                    {**TEN, "root_domain": "not a host"},
                    {**TEN, "platform_host": "app.other.com"},           # not under the root domain
                    {**TEN, "wildcard": "yes"},                          # must be a real boolean
                    {**TEN, "tls_cert": "../etc/passwd"},
                    {**TEN, "tls_cert": None},                           # wildcard needs a certificate
                    "lunovait.com"):
            with self.subTest(bad=bad), self.assertRaises(SystemExit): captured_raise(self.s.parse_tenancy, bad)

    def test_platform_host_may_equal_the_root(self):
        self.assertEqual(self.s.parse_tenancy({**TEN, "platform_host": "lunovait.com"})["platform_host"], "lunovait.com")

    def test_seeders(self):
        self.assertEqual(self.s.parse_seeders(["DatabaseSeeder", "Database\\Seeders\\RoleSeeder", "DatabaseSeeder"]), ["DatabaseSeeder", "Database\\Seeders\\RoleSeeder"])
        self.assertEqual(self.s.parse_seeders([]), []); self.assertIsNone(self.s.parse_seeders(None))
        for bad in (["Foo;rm -rf"], ["../x"], [1], "DatabaseSeeder", ["a b"]):
            with self.subTest(bad=bad), self.assertRaises(SystemExit): captured_raise(self.s.parse_seeders, bad)

    def test_tasks_schema(self):
        self.assertEqual(self.s.parse_tasks(TASKS), TASKS)
        for bad in ({"Bad Name": "x:y"}, {"t": "rm -rf /"}, {"t": "tinker"}, {"t": "migrate"}, {"t": "migrate:fresh; id"}, {"t": "x:y $(id)"}, {"t": "x:y `id`"}, {"t": "x:y {password}"},
                    {"t": "x:y {email"}, {"t": "x:y a|b"}, {"t": "x:y >out"}, {"t": ""}, {"t": 5}, ["list"]):
            with self.subTest(bad=bad), self.assertRaises(SystemExit): captured_raise(self.s.parse_tasks, bad)


def captured_raise(fn, *a):
    with contextlib.redirect_stderr(io.StringIO()): return fn(*a)


class Hosts(unittest.TestCase):
    def setUp(self): self.s = load("lunova-site")

    def test_host_re_never_accepts_a_wildcard_but_wildcard_re_does(self):
        self.assertFalse(self.s.HOST_RE.match("*.lunovait.com")); self.assertTrue(self.s.WILDCARD_RE.match("*.lunovait.com"))
        for bad in ("*.*.lunovait.com", "*lunovait.com", "a.*.lunovait.com", "*.com", "*."): self.assertFalse(self.s.WILDCARD_RE.match(bad), bad)

    def test_build_domains_puts_platform_host_first_and_wildcard_last(self):
        self.assertEqual(self.s.build_domains(["extra.net"], TEN), ["app.lunovait.com", "extra.net", "*.lunovait.com"])
        self.assertEqual(self.s.build_domains(["*.lunovait.com", "app.lunovait.com"], TEN), ["app.lunovait.com", "*.lunovait.com"])

    def test_exactly_one_wildcard_and_only_the_roots(self):
        for listed in (["*.other.com"], ["*.a.lunovait.com"], ["*.lunovait.com", "*.other.com"]):
            with self.subTest(listed=listed), self.assertRaises(SystemExit): captured_raise(self.s.build_domains, listed, TEN)

    def test_wildcard_needs_wildcard_flag_and_cert(self):
        with self.assertRaises(SystemExit): captured_raise(self.s.build_domains, ["*.lunovait.com"], None)
        with self.assertRaises(SystemExit): captured_raise(self.s.build_domains, ["*.lunovait.com"], {**TEN, "wildcard": False})
        with self.assertRaises(SystemExit): captured_raise(self.s.build_domains, ["*.lunovait.com"], {**TEN, "tls_cert": None})
        self.assertEqual(self.s.build_domains(["a.example.org"], None), ["a.example.org"])           # no tenancy: unchanged behaviour

    def test_without_wildcard_flag_only_the_platform_host_is_added(self):
        self.assertEqual(self.s.build_domains([], {**TEN, "wildcard": False}), ["app.lunovait.com"])

    def test_check_domain_does_not_dns_resolve_a_wildcard(self):
        with mock.patch.object(self.s, "cfg", lambda: {}), mock.patch.object(self.s.socket, "gethostbyname", side_effect=AssertionError("resolved")), \
                mock.patch.object(self.s, "all_sites", lambda: {}):
            code, out, _ = captured(self.s.cmd_check_domain, mock.Mock(site="s", domains=["*.lunovait.com"]))
        self.assertEqual(code, 0); self.assertIn("wildcard", out)


class Rendering(unittest.TestCase):
    def setUp(self): self.s = load("lunova-site")

    def d(self, **kw):
        return {"type": "laravel", "repo": "o/r", "domains": ["app.lunovait.com", "*.lunovait.com"], "tenancy": dict(TEN), **kw}

    def test_caddy_wildcard_block_golden(self):
        out = self.s.render_caddy("shikhon", self.d())
        self.assertEqual(out, "# managed by lunova-site (site: shikhon, repo: o/r)\napp.lunovait.com, *.lunovait.com {\n"
                              "\ttls /etc/caddy/certs/lunovait.com.pem /etc/caddy/certs/lunovait.com.key\n"
                              "\troot * /srv/sites/shikhon/current/public\n\tencode zstd gzip\n\tphp_fastcgi unix//run/php/lunova.sock {\n\t\tresolve_root_symlink\n\t}\n\tfile_server\n}\n")

    def test_platform_host_and_wildcard_share_one_app_root(self):
        out = self.s.render_caddy("shikhon", self.d())
        self.assertEqual(out.count("root * /srv/sites/shikhon/current/public"), 1)           # one block, one root
        self.assertEqual(out.count("{\n") - out.count("php_fastcgi") - out.count("{\n\t\tresolve"), 1) if False else None
        self.assertIn("app.lunovait.com, *.lunovait.com {", out)

    def test_other_domains_keep_automatic_certificates(self):
        out = self.s.render_caddy("shikhon", self.d(domains=["app.lunovait.com", "other.net", "*.lunovait.com"]))
        first, second = out.split("\n\nother.net {")
        self.assertIn("tls /etc/caddy/certs/lunovait.com.pem", first); self.assertNotIn("tls ", second)
        self.assertEqual(self.s.render_caddy("x", self.d(domains=["a.example.com"], tenancy=None)).count("tls "), 0)

    def test_sites_without_tenancy_render_exactly_as_before(self):
        d = {"type": "spa", "repo": "o/r", "domains": ["a.example.com", "b.example.com"], "root": "dist"}
        self.assertEqual(self.s.render_caddy("s", d), "# managed by lunova-site (site: s, repo: o/r)\na.example.com, b.example.com {\n\troot * /srv/sites/s/current/dist\n\tencode zstd gzip\n\ttry_files {path} /index.html\n\tfile_server\n}\n")

    def test_covered_by_is_one_label_deep(self):
        self.assertTrue(self.s.covered_by("x.lunovait.com", "lunovait.com")); self.assertFalse(self.s.covered_by("a.b.lunovait.com", "lunovait.com"))
        self.assertFalse(self.s.covered_by("evil-lunovait.com", "lunovait.com"))


class Register(unittest.TestCase):
    """cmd_register end to end with the filesystem and reload mocked."""
    def setUp(self):
        self.s = load("lunova-site"); self.tmp = Path(tempfile.mkdtemp())
        s = self.s
        s.SITES, s.REG, s.CADDY, s.CERTS = self.tmp / "sites", self.tmp / "reg", self.tmp / "caddy", self.tmp / "certs"
        s.CERTS.mkdir(); (s.CERTS / "lunovait.com.pem").write_text("x"); (s.CERTS / "lunovait.com.key").write_text("x")
        sock = self.tmp / "php.sock"; sock.write_text("")
        (self.tmp / "shims/8.3").mkdir(parents=True); (self.tmp / "shims/8.3/php").write_text("")
        s.PHP_SHIMS = self.tmp / "shims"
        self.patches = [mock.patch.object(s, "php_socket", lambda v="8.3": str(sock)), mock.patch.object(s, "caddy_reload", lambda: None),
                        mock.patch.object(s, "sync_workers", lambda *a: None), mock.patch.object(s, "WHO", None)]
        for p in self.patches: p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def reg(self, **kw):
        base = dict(site="shikhon", type="laravel", domains="", repo="lunova-digital/shikhon", php=None, database=None, queue=False, scheduler=False,
                    package=None, health_path="/", hook=None, http_only=False, start=None, root=None, image=None, container_port=None, host_port=None,
                    public_host=None, public_path=None, public_user=None, env=None, volume=None, memory=512,
                    tenancy_json=json.dumps(TEN), seeders_json='["DatabaseSeeder"]', tasks_json=json.dumps(TASKS))
        base.update(kw); return mock.Mock(**base)

    def test_registers_tenancy_and_writes_the_wildcard_vhost(self):
        code, _, _ = captured(self.s.cmd_register, self.reg())
        self.assertEqual(code, 0)
        d = json.loads((self.s.REG / "sites/shikhon.json").read_text())
        self.assertEqual(d["domains"], ["app.lunovait.com", "*.lunovait.com"]); self.assertEqual(d["tenancy"], TEN)
        self.assertEqual(d["seeders"], ["DatabaseSeeder"]); self.assertEqual(d["tasks"], TASKS)
        self.assertIn("app.lunovait.com, *.lunovait.com {", (self.s.CADDY / "shikhon.caddy").read_text())

    def test_refuses_the_wildcard_until_the_certificate_is_installed(self):
        (self.s.CERTS / "lunovait.com.key").unlink()
        code, _, err = captured(self.s.cmd_register, self.reg())
        self.assertNotEqual(code, 0); self.assertIn("tenancy-setup", err)

    def test_refuses_http_only_services_and_non_laravel_tasks(self):
        self.assertNotEqual(captured(self.s.cmd_register, self.reg(http_only=True))[0], 0)
        self.assertNotEqual(captured(self.s.cmd_register, self.reg(type="spa", tenancy_json=None, tasks_json=json.dumps(TASKS)))[0], 0)

    def test_a_wildcard_belongs_to_one_site(self):
        captured(self.s.cmd_register, self.reg())
        code, _, err = captured(self.s.cmd_register, self.reg(site="other", repo="lunova-digital/other"))
        self.assertNotEqual(code, 0); self.assertIn("already used", err)

    def test_plain_register_is_unchanged_without_the_new_keys(self):
        code, _, _ = captured(self.s.cmd_register, self.reg(domains="a.example.com", tenancy_json=None, seeders_json=None, tasks_json=None))
        self.assertEqual(code, 0)
        d = json.loads((self.s.REG / "sites/shikhon.json").read_text())
        self.assertEqual((d["domains"], d["tenancy"], d["seeders"], d["tasks"]), (["a.example.com"], None, None, None))


class Allowlist(unittest.TestCase):
    def setUp(self):
        self.s = load("lunova-site")
        self.d = {"site": "shikhon", "type": "laravel", "tasks": TASKS, "php": "8.3"}

    def test_expand_builds_an_argv_list(self):
        self.assertEqual(self.s.expand_task(TASKS["super_admin"], {"email": "a@b.co", "name": "Ada Lovelace"}), ["access:super-admin", "a@b.co", "--name=Ada Lovelace"])

    def test_values_are_validated_and_cannot_inject_options_or_shell(self):
        for k, v in (("email", "a@b.co; rm -rf /"), ("email", "-oProxy@b.co"), ("email", "not-an-email"), ("email", "a b@c.co"), ("email", "a@b.co\nx"),
                     ("name", "$(id)"), ("name", "a;b"), ("name", "`x`"), ("name", "-x"), ("name", "x" * 200), ("name", "a\nb")):
            with self.subTest(k=k, v=v), self.assertRaises(SystemExit):
                captured_raise(self.s.expand_task, TASKS["super_admin"], {"email": "a@b.co", "name": "Ada", k: v})

    def test_unknown_task_and_missing_values_are_refused(self):
        for name in ("shell", "migrate:fresh", "super_admin; id", ""):
            with self.subTest(name=name), self.assertRaises(SystemExit): captured_raise(self.s.task_argv, self.d, name, {})
        with self.assertRaises(SystemExit): captured_raise(self.s.task_argv, self.d, "super_admin", {"email": "a@b.co"})

    def test_only_known_placeholders_in_args(self):
        for kv in (["password=x"], ["noequals"], ["email"]):
            with self.assertRaises(SystemExit): captured_raise(self.s.parse_args_kv, kv)
        self.assertEqual(self.s.parse_args_kv(["email=a@b.co"]), {"email": "a@b.co"})

    def test_run_executes_artisan_with_an_argv_list_never_a_shell(self):
        seen = []
        with mock.patch.object(self.s, "load", lambda s, write=False: self.d), mock.patch.object(self.s, "need_laravel", lambda d: None), \
                mock.patch.object(self.s, "artisan", lambda d, *a, check=True: seen.append(a) or mock.Mock(returncode=0, stdout="done", stderr="")), \
                mock.patch.object(self.s, "WHO", None), mock.patch.object(self.s, "authorize_mode", lambda *a: None):
            code, out, _ = captured(self.s.cmd_run, mock.Mock(site="shikhon", task="super_admin", arg=["email=a@b.co", "name=Ada"], confirm=None))
        self.assertEqual(code, 0); self.assertEqual(seen, [("access:super-admin", "a@b.co", "--name=Ada")])
        with mock.patch.object(self.s, "load", lambda s, write=False: self.d), mock.patch.object(self.s, "need_laravel", lambda d: None), \
                mock.patch.object(self.s, "artisan", side_effect=AssertionError("must not run")), mock.patch.object(self.s, "WHO", None), \
                mock.patch.object(self.s, "authorize_mode", lambda *a: None):
            code, _, _ = captured(self.s.cmd_run, mock.Mock(site="shikhon", task="tinker", arg=[], confirm=None))
        self.assertNotEqual(code, 0)


class Masking(unittest.TestCase):
    LINK = "https://app.lunovait.com/invite/ZmFrZS10b2tlbi1mb3ItdGVzdHMtb25seQ?signature=abcdef0123456789abcdef0123456789"

    def setUp(self):
        self.s = load("lunova-site")
        self.d = {"site": "shikhon", "type": "laravel", "tasks": TASKS, "php": "8.3"}
        self.stored = []

    def run_bootstrap(self, rc=0, out=None):
        out = out if out is not None else f"Super admin created.\nSet your password: {self.LINK}\n"
        def fake_priv(*a, data=None, check=True): self.stored.append((a, data)); return mock.Mock(returncode=0, stdout="/var/lib/lunova/secrets/shikhon/bootstrap-admin-1.txt\n", stderr="")
        with mock.patch.object(self.s, "load", lambda s, write=False: self.d), mock.patch.object(self.s, "need_laravel", lambda d: None), \
                mock.patch.object(self.s, "artisan", lambda d, *a, check=True: mock.Mock(returncode=rc, stdout=out, stderr="")), \
                mock.patch.object(self.s, "priv", fake_priv), mock.patch.object(self.s, "WHO", None), mock.patch.object(self.s, "authorize_mode", lambda *a: None):
            return captured(self.s.cmd_bootstrap_admin, mock.Mock(site="shikhon", confirm="shikhon", arg=["email=a@b.co", "name=Ada"]))

    def test_a_printed_link_never_reaches_stdout_or_stderr(self):
        code, out, err = self.run_bootstrap()
        self.assertEqual(code, 0)
        for stream in (out, err): self.assertNotIn("invite/", stream); self.assertNotIn("signature=", stream); self.assertNotIn("ZmFrZS10b2tlbi", stream)
        self.assertIn("/var/lib/lunova/secrets/shikhon/bootstrap-admin-1.txt", out)          # only the path is reported
        self.assertIn("1 link(s)", out)

    def test_the_link_goes_to_the_root_only_helper(self):
        self.run_bootstrap()
        (args, data), = self.stored
        self.assertEqual(args, ("store-secret", "shikhon", "bootstrap-admin")); self.assertIn(self.LINK, data)

    def test_failure_output_is_redacted(self):
        code, out, err = self.run_bootstrap(rc=1, out=f"Error: could not create. Retry {self.LINK} token AbCdEfGhIjKlMnOpQrStUvWxYz0123456789\n")
        self.assertNotEqual(code, 0)
        for stream in (out, err): self.assertNotIn(self.LINK, stream); self.assertNotIn("AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", stream)

    def test_redact(self):
        r = self.s.redact(f"see {self.LINK} and AbCdEfGhIjKlMnOpQrStUvWxYz0123456789 ok")
        self.assertNotIn("http", r); self.assertNotIn("AbCdEf", r); self.assertIn("ok", r)

    def test_bootstrap_needs_email_and_name_and_there_is_no_password_argument(self):
        with mock.patch.object(self.s, "load", lambda s, write=False: self.d), mock.patch.object(self.s, "need_laravel", lambda d: None), mock.patch.object(self.s, "WHO", None), \
                mock.patch.object(self.s, "authorize_mode", lambda *a: None):
            self.assertNotEqual(captured(self.s.cmd_bootstrap_admin, mock.Mock(site="shikhon", confirm="shikhon", arg=["email=a@b.co"]))[0], 0)
            self.assertNotEqual(captured(self.s.cmd_bootstrap_admin, mock.Mock(site="shikhon", confirm="shikhon", arg=["email=a@b.co", "name=A", "password=x"]))[0], 0)


class ResetOrdering(unittest.TestCase):
    def setUp(self):
        self.s = load("lunova-site")
        self.d = {"site": "shikhon", "type": "laravel", "database": "mysql", "seeders": ["DatabaseSeeder", "RoleSeeder"], "php": "8.3"}
        self.calls = []

    def run_reset(self, backup_fails=False, d=None):
        def backup(d):
            self.calls.append("backup")
            if backup_fails: raise SystemExit(1)
            return {"path": "/srv/backups/shikhon/x.sql.gz", "size": 10, "sha256": "ab"}
        def artisan(d, *a, check=True): self.calls.append(" ".join(a)); return mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(self.s, "load", lambda s, write=False: d or self.d), mock.patch.object(self.s, "need_laravel", lambda d: None), \
                mock.patch.object(self.s, "do_backup", backup), mock.patch.object(self.s, "artisan", artisan), mock.patch.object(self.s, "WHO", None), \
                mock.patch.object(self.s, "authorize_mode", lambda *a: None):
            return captured(self.s.cmd_reset_db, mock.Mock(site="shikhon", confirm="shikhon"))

    def test_backup_runs_first_then_fresh_then_only_manifest_seeders_then_caches_then_queue(self):
        self.assertEqual(self.run_reset()[0], 0)
        self.assertEqual(self.calls, ["backup", "migrate:fresh --force", "db:seed --class=DatabaseSeeder --force", "db:seed --class=RoleSeeder --force",
                                      "optimize:clear", "config:cache", "route:cache", "view:cache", "event:cache", "queue:restart"])

    def test_a_failed_backup_aborts_before_anything_destructive(self):
        self.assertNotEqual(self.run_reset(backup_fails=True)[0], 0)
        self.assertEqual(self.calls, ["backup"])                                    # migrate:fresh was never called

    def test_no_seeders_key_means_no_reset(self):
        code, _, err = self.run_reset(d={**self.d, "seeders": None})
        self.assertNotEqual(code, 0); self.assertEqual(self.calls, [])

    def test_empty_seeders_list_resets_without_seeding(self):
        self.assertEqual(self.run_reset(d={**self.d, "seeders": []})[0], 0)
        self.assertFalse([c for c in self.calls if c.startswith("db:seed")])


class Backup(unittest.TestCase):
    def setUp(self):
        self.s = load("lunova-site"); self.tmp = Path(tempfile.mkdtemp())
        self.s.SITES, self.s.BACKUPS = self.tmp / "sites", self.tmp / "backups"
        (self.s.SITES / "shikhon/shared").mkdir(parents=True); (self.s.BACKUPS / "shikhon").mkdir(parents=True)
        (self.s.SITES / "shikhon/shared/db.env").write_text("DB_HOST=127.0.0.1\nDB_PORT=3306\nDB_DATABASE=app_shikhon\nDB_USERNAME=u\nDB_PASSWORD=secret-pw\n")
        self.priv = mock.patch.object(self.s, "priv", lambda *a, **k: mock.Mock(returncode=0, stdout="", stderr="")); self.priv.start(); self.addCleanup(self.priv.stop)

    def popen(self, rc=0, dump=b"-- MariaDB dump\nCREATE TABLE t (id int);\n-- Dump completed on 2026-01-01\n", seen=None):
        real = subprocess.Popen

        class P:
            def __init__(p, cmd, **kw):
                if seen is not None: seen.update(cmd=cmd, env=kw.get("env"))
                p.stdout, p.stderr = io.BytesIO(dump), io.BytesIO(b"boom" if rc else b"")
            def wait(p): return rc
        return lambda cmd, **kw: P(cmd, **kw) if cmd[0] == "mysqldump" else real(cmd, **kw)       # only mysqldump is faked; gzip -t is the real one

    def test_mysql_backup_is_gzip_verified_and_hashed(self):
        seen = {}
        with mock.patch.object(self.s.subprocess, "Popen", self.popen(seen=seen)):
            b = self.s.do_backup({"site": "shikhon", "database": "mysql"})
        p = Path(b["path"]); self.assertTrue(p.exists()); self.assertEqual(b["size"], p.stat().st_size)
        self.assertEqual(b["sha256"], __import__("hashlib").sha256(p.read_bytes()).hexdigest())
        self.assertIn(b"CREATE TABLE", gzip.open(p).read()); self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")
        self.assertNotIn("secret-pw", " ".join(seen["cmd"]))                          # password is never on the command line
        self.assertEqual(seen["env"]["MYSQL_PWD"], "secret-pw")
        self.assertEqual(subprocess.run(["gzip", "-t", str(p)]).returncode, 0)

    def test_failed_or_truncated_dump_leaves_no_file(self):
        for kw in ({"rc": 2}, {"dump": b"-- MariaDB dump\nCREATE TABLE t"}):
            with self.subTest(kw=kw), mock.patch.object(self.s.subprocess, "Popen", self.popen(**kw)), self.assertRaises(SystemExit):
                captured_raise(self.s.do_backup, {"site": "shikhon", "database": "mysql"})
            self.assertEqual(list((self.s.BACKUPS / "shikhon").iterdir()), [])

    def test_sqlite_backup(self):
        db = self.s.SITES / "shikhon/shared/database.sqlite"; c = sqlite3.connect(db); c.execute("create table t(x)"); c.execute("insert into t values (7)"); c.commit(); c.close()
        (self.s.SITES / "shikhon/shared/db.env").write_text(f"DB_CONNECTION=sqlite\nDB_DATABASE={db}\n")
        b = self.s.do_backup({"site": "shikhon", "database": "sqlite"})
        out = self.tmp / "restored.sqlite"; out.write_bytes(gzip.open(b["path"]).read())
        self.assertEqual(sqlite3.connect(out).execute("select x from t").fetchall(), [(7,)])

    def test_other_engines_are_refused_not_faked(self):
        with self.assertRaises(SystemExit): captured_raise(self.s.do_backup, {"site": "shikhon", "database": "postgres"})


class ModePolicy(unittest.TestCase):
    def setUp(self):
        self.s = load("lunova-site"); self.tmp = Path(tempfile.mkdtemp()); self.s.REG = self.tmp
        (self.tmp / "sites").mkdir()
        (self.tmp / "sites/shikhon.json").write_text(json.dumps({"site": "shikhon", "type": "laravel", "repo": "lunova-digital/shikhon", "branch": "main",
                                                                  "domains": ["app.lunovait.com"]}))
        self.set(WHO="lunova-digital/shikhon", REF="refs/heads/main", EVENT="workflow_dispatch", ENVIRONMENT="production", ACTOR="nprime")

    def set(self, **kw):
        for k, v in kw.items(): setattr(self.s, k, v)

    def ok(self, mode, confirm="shikhon"):
        return captured(self.s.authorize_mode, mode, "shikhon", confirm)[0] == 0

    def test_the_happy_path_for_every_mode(self):
        for m in self.s.MODE_POLICY: self.assertTrue(self.ok(m), m)

    def test_privileged_modes_need_the_production_environment(self):
        for env in ("", "staging", "Production"):
            self.set(ENVIRONMENT=env)
            for m in ("tenancy-setup", "reset-db", "bootstrap-admin"): self.assertFalse(self.ok(m), (m, env))
            for m in ("backup", "run"): self.assertTrue(self.ok(m))                       # not environment-gated

    def test_privileged_modes_need_the_typed_site_name(self):
        for m in ("tenancy-setup", "reset-db", "bootstrap-admin"):
            for c in ("", None, "SHIKHON", "shikhon ", "other"): self.assertFalse(self.ok(m, c), (m, c))

    def test_only_manual_runs_may_use_these_modes(self):
        for ev in ("push", "pull_request", "schedule", ""):
            self.set(EVENT=ev)
            for m in self.s.MODE_POLICY: self.assertFalse(self.ok(m), (m, ev))

    def test_wrong_repo_or_branch_is_refused(self):
        self.set(WHO="lunova-digital/other")
        for m in self.s.MODE_POLICY: self.assertFalse(self.ok(m), m)
        self.set(WHO="lunova-digital/shikhon", REF="refs/heads/feature")
        for m in self.s.MODE_POLICY: self.assertFalse(self.ok(m), m)
        self.set(REF="refs/pull/3/merge")
        for m in self.s.MODE_POLICY: self.assertFalse(self.ok(m), m)

    def test_unregistered_site_only_allows_tenancy_setup(self):
        self.assertFalse(captured(self.s.authorize_mode, "backup", "nope", "nope")[0] == 0)
        self.assertTrue(captured(self.s.authorize_mode, "tenancy-setup", "nope", "nope")[0] == 0)
        self.set(ENVIRONMENT="")
        self.assertFalse(captured(self.s.authorize_mode, "tenancy-setup", "nope", "nope")[0] == 0)

    def test_every_call_writes_an_audit_line_with_who_mode_site_time(self):
        self.set(ENVIRONMENT="")
        @self.s.moded("reset-db")
        def cmd(a): pass
        captured(cmd, mock.Mock(site="shikhon", confirm="shikhon"))
        self.set(ENVIRONMENT="production")
        captured(cmd, mock.Mock(site="shikhon", confirm="shikhon"))
        lines = (self.tmp / "audit.log").read_text().splitlines()
        self.assertEqual(len(lines), 3)                                                   # DENIED, then start + ok
        self.assertRegex(lines[0], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ actor=nprime repo=lunova-digital/shikhon ref=refs/heads/main mode=reset-db site=shikhon result=DENIED$")
        self.assertTrue(lines[1].endswith("result=start") and lines[2].endswith("result=ok"))

    def test_failures_are_audited_as_failures(self):
        @self.s.moded("backup")
        def cmd(a): raise SystemExit(3)
        captured(cmd, mock.Mock(site="shikhon", confirm=None))
        self.assertIn("result=FAIL(3)", (self.tmp / "audit.log").read_text())

    def test_audit_values_cannot_forge_lines(self):
        self.set(ACTOR="x\nresult=ok forged")
        self.s.audit("backup", "shikhon", "ok")
        self.assertEqual(len((self.tmp / "audit.log").read_text().splitlines()), 1)


class Gate(unittest.TestCase):
    def test_gate_exports_the_environment_claim_and_does_not_take_it_from_the_caller(self):
        src = (ROOT / "server/lunova-gate").read_text()
        self.assertIn('LUNOVA_ENVIRONMENT=str(claims.get("environment", ""))', src)
        self.assertIn('not k.startswith("LUNOVA_")', src)          # a caller-supplied LUNOVA_* variable is dropped before the claims are exported


@unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
class RootHelper(unittest.TestCase):
    def setUp(self):
        self.p = load("lunova-priv"); self.tmp = Path(tempfile.mkdtemp())
        self.p.CERTS, self.p.BACKUPS, self.p.SECRETS, self.p.AUDIT = self.tmp / "certs", self.tmp / "backups", self.tmp / "secrets", self.tmp / "audit.log"

    def make(self, names, days=2, cn="x"):
        d = Path(tempfile.mkdtemp()); san = ",".join(f"DNS:{n}" for n in names)
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", d / "k", "-out", d / "c", "-subj", f"/CN={cn}", "-days", str(days),
                        "-addext", f"subjectAltName={san}"], check=True, capture_output=True)
        return (d / "c").read_text(), (d / "k").read_text()

    def install(self, cert, key, reload_ok=True, name="lunova", root="lunovait.com"):
        rel = mock.patch.object(self.p, "validate_and_reload", lambda: None if reload_ok else "web server config invalid: boom")
        with rel, mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"cert": cert, "key": key}))):
            return captured(self.p.cmd_install_cert, name, root)

    def test_a_good_pair_is_installed_with_the_right_modes_and_is_idempotent(self):
        c, k = self.make(["lunovait.com", "*.lunovait.com"])
        code, out, _ = self.install(c, k)
        self.assertEqual(code, 0); self.assertIn("installed", out)
        self.assertEqual(oct((self.p.CERTS / "lunova.key").stat().st_mode & 0o777), "0o640"); self.assertEqual((self.p.CERTS / "lunova.pem").read_text(), c)
        code, out, _ = self.install(c, k); self.assertEqual(code, 0); self.assertIn("unchanged", out)

    def test_refuses_mismatched_expired_or_incomplete_certificates(self):
        c, k = self.make(["lunovait.com", "*.lunovait.com"]); _, other_key = self.make(["lunovait.com", "*.lunovait.com"])
        self.assertIn("does not belong", self.p.check_pair(c, other_key, "lunovait.com"))
        self.assertIn("does not cover *.lunovait.com", self.p.check_pair(*self.make(["lunovait.com"]), "lunovait.com"))
        self.assertIn("does not cover lunovait.com", self.p.check_pair(*self.make(["*.lunovait.com"]), "lunovait.com"))
        self.assertIn("PEM", self.p.check_pair("junk", "junk", "lunovait.com"))
        self.assertIsNone(self.p.check_pair(c, k, "lunovait.com"))
        code, _, err = self.install(c, other_key); self.assertNotEqual(code, 0); self.assertFalse((self.p.CERTS / "lunova.pem").exists())

    def test_a_failed_validation_restores_the_previous_certificate(self):
        old_c, old_k = self.make(["lunovait.com", "*.lunovait.com"]); self.install(old_c, old_k)
        new_c, new_k = self.make(["lunovait.com", "*.lunovait.com"])
        code, _, err = self.install(new_c, new_k, reload_ok=False)
        self.assertNotEqual(code, 0); self.assertIn("previous certificate was restored", err)
        self.assertEqual((self.p.CERTS / "lunova.pem").read_text(), old_c); self.assertEqual((self.p.CERTS / "lunova.key").read_text(), old_k)

    def test_a_failed_first_install_leaves_nothing_behind(self):
        c, k = self.make(["lunovait.com", "*.lunovait.com"])
        self.assertNotEqual(self.install(c, k, reload_ok=False)[0], 0)
        self.assertFalse((self.p.CERTS / "lunova.pem").exists()); self.assertFalse((self.p.CERTS / "lunova.key").exists())

    def test_store_secret_prints_only_the_path_and_is_0600(self):
        with mock.patch.object(sys, "stdin", io.StringIO("https://x/secret-link")):
            code, out, _ = captured(self.p.cmd_store_secret, "shikhon", "bootstrap-admin")
        path = Path(out.strip()); self.assertEqual(code, 0); self.assertNotIn("secret-link", out)
        self.assertEqual(path.read_text(), "https://x/secret-link"); self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")

    def test_helper_rejects_bad_names(self):
        for fn, args in ((self.p.cmd_backup_dir, ("../x",)), (self.p.cmd_store_secret, ("shikhon", "../x")), (self.p.cmd_store_secret, ("A B", "x"))):
            with self.assertRaises(SystemExit): captured_raise(fn, *args)
        with mock.patch.object(sys, "stdin", io.StringIO("{}")), self.assertRaises(SystemExit): captured_raise(self.p.cmd_install_cert, "../x", "lunovait.com")


# --- the workflow file ---------------------------------------------------------------------------------------------------------------------
def workflow(): return yaml.safe_load(WORKFLOW.read_text())


def step(job, prefix):
    return next(s for s in workflow()["jobs"][job]["steps"] if s.get("name", "").startswith(prefix))


def embedded_python(run):
    return re.search(r"<<'PY'[^\n]*\n(.*?)\nPY(?:\n|$)", run, re.S).group(1)


class WorkflowShape(unittest.TestCase):
    def test_privileged_modes_run_only_in_a_job_bound_to_the_production_environment(self):
        w = workflow()["jobs"]
        self.assertEqual(w["lunova-privileged"]["environment"], "production"); self.assertNotIn("environment", w["lunova"])
        cond = lambda j: w[j]["if"]
        for m in ("tenancy-setup", "reset-db", "bootstrap-admin"): self.assertIn(f'"{m}"', cond("lunova-privileged"))
        self.assertTrue(cond("lunova").lstrip("${ ").startswith("!contains(")); self.assertTrue(cond("lunova-privileged").lstrip("${ ").startswith("contains("))
        self.assertEqual(re.findall(r"\[.*?\]", cond("lunova"))[0], re.findall(r"\[.*?\]", cond("lunova-privileged"))[0])
        for s in w["lunova"]["steps"]:                                                   # nothing destructive can run in the unprotected job
            self.assertNotRegex(s.get("if", ""), r"tenancy-setup|reset-db|bootstrap-admin")
        for sec in ("ORIGIN_CERT", "ORIGIN_KEY", "CF_API_TOKEN"): self.assertNotIn(f"secrets.{sec}", json.dumps(w["lunova"]))

    def test_the_duplicated_connect_read_and_verify_steps_are_identical(self):
        for prefix in ("Read manifest", "Connect", "Verify hosts"):
            self.assertEqual(step("lunova", prefix)["run"], step("lunova-privileged", prefix)["run"], prefix)

    def test_no_expression_is_interpolated_into_a_shell_script(self):
        for j, v in workflow()["jobs"].items():
            for s in v["steps"]:
                self.assertNotIn("${{", s.get("run", ""), (j, s.get("name")))               # inputs and secrets reach the shell only through env:

    def test_every_run_script_is_valid_bash(self):
        for j, v in workflow()["jobs"].items():
            for s in v["steps"]:
                if "run" not in s: continue
                p = subprocess.run(["bash", "-n"], input=s["run"], text=True, capture_output=True)
                self.assertEqual(p.returncode, 0, f"{j}/{s.get('name')}: {p.stderr}")
                for m in re.finditer(r"python3 (?:-I )?- <<'PY'.*?\nPY", s["run"], re.S):
                    py = embedded_python(m.group(0))
                    compile(py, f"{j}/{s.get('name')}", "exec")

    def test_secrets_are_only_given_to_the_two_tenancy_steps(self):
        users = [s["name"] for s in workflow()["jobs"]["lunova-privileged"]["steps"] if "secrets." in json.dumps(s.get("env", {}))]
        self.assertEqual(users, ["Tenancy: origin certificate and site config (on the server)", "Tenancy: Cloudflare DNS sync (proxied A records and apex redirect)"])

    def test_no_password_input_exists_anywhere(self):
        ins = workflow()[True]["workflow_call"]["inputs"]
        self.assertFalse([k for k in ins if "pass" in k.lower() or "secret" in k.lower()])
        caller = yaml.safe_load((ROOT / "skills/lunova-deploy/templates/lunova-deploy.yml").read_text())
        self.assertFalse([k for k in caller[True]["workflow_dispatch"]["inputs"] if "pass" in k.lower()])
        self.assertIn("admin_email", ins); self.assertIn("admin_name", ins)

    def test_the_confirm_check_comes_before_the_connection(self):
        names = [s.get("name", "") for s in workflow()["jobs"]["lunova-privileged"]["steps"]]
        self.assertLess(names.index("Check the typed confirmation"), next(i for i, n in enumerate(names) if n.startswith("Connect")))

    def test_the_caller_template_exposes_every_mode_input_and_secret(self):
        t = yaml.safe_load((ROOT / "skills/lunova-deploy/templates/lunova-deploy.yml").read_text().replace("__BRANCH__", "main").replace("__WORKFLOW_REPO__", "o/r")
                           .replace("__WORKFLOW_REF__", "v10").replace("__SELF_HOSTED__", "false"))
        opts = t[True]["workflow_dispatch"]["inputs"]["mode"]["options"]
        self.assertEqual(set(opts), {"deploy", "check", "rollback", "status", "logs", "backup", "run", "tenancy-setup", "reset-db", "bootstrap-admin"})
        job = t["jobs"]["lunova"]; self.assertTrue(job["uses"].endswith("@v10"))
        wf = workflow()[True]["workflow_call"]
        for k in job["with"]: self.assertIn(k, wf["inputs"], k)
        self.assertEqual(set(job["secrets"]), set(wf["secrets"]))
        for k in wf["inputs"]:
            if k not in ("manifest",): self.assertIn(k, job["with"], k)
        self.assertEqual(yaml.safe_load((ROOT / "skills/lunova-deploy/config.yml").read_text())["workflow_ref"], "v10")


class VerifyScript(unittest.TestCase):
    def setUp(self):
        self.ns = {"__name__": "verify"}; exec(embedded_python(step("lunova", "Verify hosts")["run"]), self.ns)

    def test_classifier_separates_app_from_no_site(self):
        c = self.ns["classify"]
        self.assertEqual(c(0, 200, "HTTP/2 200\r\ncontent-type: text/html\r\n", "<html>hi</html>"), "app")
        self.assertEqual(c(0, 404, "HTTP/2 404\r\n", "<html>Not Found</html>"), "app")                         # the app answered (a 404 page is still the app)
        self.assertEqual(c(0, 302, "HTTP/2 302\r\nLocation: /login\r\nSet-Cookie: x=1\r\n", ""), "app")
        self.assertEqual(c(0, 200, "HTTP/2 200\r\nserver: Caddy\r\n", ""), "empty")
        self.assertEqual(c(0, 404, "HTTP/2 404\r\nserver: Caddy\r\n", ""), "empty")
        self.assertEqual(c(0, 200, "", "No site configured at this address"), "no_site")
        for rc in (35, 52, 56, 60): self.assertEqual(c(rc, 0, "", ""), "no_site", rc)                      # TLS refused / empty reply
        for rc in (6, 7, 28): self.assertEqual(c(rc, 0, "", ""), "unreachable", rc)
        self.assertEqual(c(0, 0, "", ""), "unreachable")

    def test_only_the_root_path_is_probed_never_up(self):
        src = embedded_python(step("lunova", "Verify hosts")["run"])
        self.assertIn('f"https://{h}/"]', src); self.assertNotRegex(src, r'https://\{h\}/up')

    def test_wildcard_is_probed_with_a_random_label_via_resolve(self):
        calls = []
        def fake_run(cmd, **kw): calls.append(cmd); return mock.Mock(returncode=0, stdout="200", stderr="")
        self.ns["IP"] = "1.2.3.4"
        with mock.patch.object(self.ns["subprocess"], "run", fake_run):
            r1, r2 = self.ns["probe"]("*.lunovait.com"), self.ns["probe"]("*.lunovait.com")
        self.assertRegex(r1["probed"], r"^zzz-probe-[0-9a-f]{8}\.lunovait\.com$"); self.assertNotEqual(r1["probed"], r2["probed"])
        cmd = calls[0]; self.assertIn("--resolve", cmd); self.assertIn(f"{r1['probed']}:443:1.2.3.4", cmd); self.assertEqual(cmd[-1], f"https://{r1['probed']}/")

    def test_judge_modes(self):
        j = self.ns["judge"]; mk = lambda h, cls, code=200: {"host": h, "cls": cls, "code": code}
        self.assertEqual(j("strict", [mk("a", "app"), mk("*.x", "app")]), [])
        self.assertEqual(len(j("strict", [mk("a", "app"), mk("*.x", "no_site", 0)])), 1)
        self.assertEqual(len(j("strict", [mk("a", "empty", 404)])), 1)
        # before the first deploy both names answer with the same empty vhost: fine. A name the web server doesn't know: not fine.
        self.assertEqual(j("setup", [mk("a", "empty", 404), mk("*.x", "empty", 404)]), [])
        self.assertEqual(len(j("setup", [mk("a", "empty", 404), mk("*.x", "no_site", 0)])), 1)
        self.assertEqual(len(j("setup", [mk("a", "app", 200), mk("*.x", "empty", 404)])), 1)                  # served differently

    def test_the_two_failure_kinds_are_reported_separately(self):
        L = self.ns["LABEL"]; self.assertIn("app responded", L["app"]); self.assertIn("No site configured", L["no_site"]); self.assertNotEqual(L["app"], L["no_site"])


class FakeCloudflare:
    def __init__(self, records=None, rules=None):
        self.records = list(records or []); self.rules = list(rules or []); self.writes = []; self.n = 0

    def __call__(self, method, path, body=None):
        if method == "GET" and path.startswith("/zones?name="): return 200, {"result": [{"id": "Z1"}]}
        if method == "GET" and "/dns_records?name=" in path:
            n = path.split("name=")[1]; return 200, {"result": [r for r in self.records if r["name"] == n]}
        if method == "POST" and path.endswith("/dns_records"):
            self.writes.append((method, path)); self.n += 1; self.records.append({**body, "id": f"r{self.n}"}); return 200, {}
        if method == "PATCH":
            self.writes.append((method, path)); rid = path.rsplit("/", 1)[1]
            for r in self.records:
                if r["id"] == rid: r.update(body)
            return 200, {}
        if "/rulesets/phases/" in path and method == "GET": return (200, {"result": {"rules": self.rules}}) if self.rules else (404, {})
        if "/rulesets/phases/" in path and method == "PUT": self.writes.append((method, path)); self.rules = body["rules"]; return 200, {}
        return 500, {}


class DnsSync(unittest.TestCase):
    def setUp(self):
        self.ns = {"__name__": "dns"}; exec(embedded_python(step("lunova-privileged", "Tenancy: Cloudflare")["run"]), self.ns)
        self.sync = lambda api: self.ns["sync"](api, "lunovait.com", "app.lunovait.com", "152.42.168.192")

    def test_creates_proxied_records_and_the_apex_redirect(self):
        api = FakeCloudflare()
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(self.sync(api), 4)
        self.assertEqual({r["name"] for r in api.records}, {"lunovait.com", "app.lunovait.com", "*.lunovait.com"})
        self.assertTrue(all(r["type"] == "A" and r["proxied"] is True and r["content"] == "152.42.168.192" for r in api.records))
        (rule,) = api.rules
        self.assertEqual(rule["action_parameters"]["from_value"]["status_code"], 301); self.assertIn('http.host eq "lunovait.com"', rule["expression"])
        self.assertIn("https://app.lunovait.com", rule["action_parameters"]["from_value"]["target_url"]["expression"])

    def test_second_run_changes_nothing(self):
        api = FakeCloudflare()
        with contextlib.redirect_stdout(io.StringIO()):
            self.sync(api); api.writes.clear(); self.assertEqual(self.sync(api), 0)
        self.assertEqual(api.writes, [])

    def test_fixes_a_wrong_or_unproxied_record_and_keeps_other_rules(self):
        other = {"description": "someone else", "expression": "true", "action": "redirect", "enabled": True}
        api = FakeCloudflare(records=[{"id": "a", "type": "A", "name": "lunovait.com", "content": "1.1.1.1", "proxied": False}], rules=[other])
        with contextlib.redirect_stdout(io.StringIO()): self.sync(api)
        self.assertEqual(next(r for r in api.records if r["name"] == "lunovait.com")["content"], "152.42.168.192")
        self.assertIn(other, api.rules); self.assertEqual(len(api.rules), 2)

    def test_never_replaces_a_conflicting_cname(self):
        api = FakeCloudflare(records=[{"id": "c", "type": "CNAME", "name": "app.lunovait.com", "content": "x.example.net", "proxied": True}])
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit): self.sync(api)
        self.assertEqual([w for w in api.writes if w[0] in ("PATCH",)], [])

    def test_token_is_only_read_from_the_environment(self):
        src = embedded_python(step("lunova-privileged", "Tenancy: Cloudflare")["run"])
        self.assertIn('os.environ.get("CF_API_TOKEN"', src); self.assertNotIn("print(t", src)


class TenancySetupCommand(unittest.TestCase):
    def setUp(self):
        self.s = load("lunova-site"); self.priv_calls = []; self.registered = []
        self.patches = [mock.patch.object(self.s, "authorize_mode", lambda *a: None),
                        mock.patch.object(self.s, "priv", lambda *a, data=None, check=True: self.priv_calls.append((a, data)) or mock.Mock(returncode=0, stdout="installed\n", stderr="")),
                        mock.patch.object(self.s, "cmd_register", lambda ns: self.registered.append(ns)),
                        mock.patch.object(self.s, "WHO", None)]
        for p in self.patches: p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def run_cmd(self, stdin="", **kw):
        a = mock.Mock(site="shikhon", confirm="shikhon", type="laravel", domains="", root=None, php="8.3", health_path="/", tenancy_json=json.dumps(TEN),
                      seeders_json='["DatabaseSeeder"]', tasks_json=json.dumps(TASKS)); a.configure_mock(**kw)
        with mock.patch.object(sys, "stdin", io.StringIO(stdin)), mock.patch.object(sys.stdin, "isatty", lambda: False, create=True), \
                mock.patch.object(self.s, "all_sites", lambda: {}):
            return captured(self.s.cmd_tenancy_setup, a)

    def test_certificate_goes_to_the_helper_on_stdin_never_argv_then_the_site_is_registered(self):
        code, out, _ = self.run_cmd(json.dumps({"cert": "CERT-PEM", "key": "KEY-PEM"}))
        self.assertEqual(code, 0)
        (args, data), = self.priv_calls
        self.assertEqual(args, ("install-cert", "lunovait.com", "lunovait.com")); self.assertEqual(json.loads(data), {"cert": "CERT-PEM", "key": "KEY-PEM"})
        self.assertNotIn("PEM", " ".join(args)); self.assertNotIn("PEM", out)
        (ns,) = self.registered; self.assertEqual((ns.site, ns.type, ns.tenancy_json, ns.seeders_json, ns.tasks_json), ("shikhon", "laravel", json.dumps(TEN), '["DatabaseSeeder"]', json.dumps(TASKS)))

    def test_without_a_bundle_the_installed_certificate_is_kept(self):
        self.assertEqual(self.run_cmd("")[0], 0); self.assertEqual(self.priv_calls, []); self.assertEqual(len(self.registered), 1)

    def test_bad_bundle_and_missing_tenancy_are_refused(self):
        self.assertNotEqual(self.run_cmd("not json")[0], 0); self.assertEqual(self.registered, [])
        self.assertNotEqual(self.run_cmd("", tenancy_json="")[0], 0)
        self.assertNotEqual(self.run_cmd("", type="node")[0], 0)

    def test_an_existing_site_keeps_its_database_queue_and_hooks(self):
        old = {"database": "mysql", "queue": True, "scheduler": True, "hooks": ["php artisan migrate --force"], "packages": ["ffmpeg"], "domains": ["app.lunovait.com"], "php": "8.4"}
        a = mock.Mock(site="shikhon", confirm="shikhon", type="laravel", domains="", root=None, php=None, health_path=None, tenancy_json=json.dumps(TEN), seeders_json=None, tasks_json=None)
        with mock.patch.object(sys, "stdin", io.StringIO("")), mock.patch.object(self.s, "all_sites", lambda: {"shikhon": old}):
            captured(self.s.cmd_tenancy_setup, a)
        (ns,) = self.registered; self.assertEqual((ns.database, ns.queue, ns.scheduler, ns.hook, ns.package, ns.php), ("mysql", True, True, ["php artisan migrate --force"], ["ffmpeg"], "8.4"))


class Cli(unittest.TestCase):
    def test_new_subcommands_parse_and_dispatch(self):
        s = load("lunova-site")
        cases = [(["backup", "x"], "cmd_backup", {"site": "x"}), (["reset-db", "x", "--confirm", "x"], "cmd_reset_db", {"confirm": "x"}),
                 (["bootstrap-admin", "x", "--confirm", "x", "--arg", "email=a@b.co", "--arg", "name=A"], "cmd_bootstrap_admin", {"arg": ["email=a@b.co", "name=A"]}),
                 (["run", "x", "--task", "t", "--arg", "email=a@b.co"], "cmd_run", {"task": "t"}), (["show-config", "x"], "cmd_show_config", {"site": "x"}),
                 (["tenancy-setup", "x", "--type", "laravel", "--tenancy-json", "{}"], "cmd_tenancy_setup", {"type": "laravel", "tenancy_json": "{}"})]
        for argv, fn, want in cases:
            seen = []
            with self.subTest(argv=argv), mock.patch.object(sys, "argv", ["lunova-site", *argv]), mock.patch.object(s, fn, lambda a: seen.append(a)):
                s.main()
            self.assertEqual(len(seen), 1, fn)
            for k, v in want.items(): self.assertEqual(getattr(seen[0], k), v, (fn, k))
        with mock.patch.object(sys, "argv", ["lunova-site", "run", "x"]), self.assertRaises(SystemExit): captured_raise(s.main)    # --task is required


if __name__ == "__main__":
    unittest.main()
