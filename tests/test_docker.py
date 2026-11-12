"""Offline tests for `docker` sites (no Docker, no server): python3 -m unittest discover -s tests"""
import importlib.machinery, importlib.util, json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(ROOT / "server" / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec); loader.exec_module(mod)
    return mod


D = {"site": "shop", "type": "docker", "domains": ["shop.example.com"], "port": 3105, "container_port": 3000,
     "env": {"NODE_ENV": "production"}, "volumes": ["data:/app/data"], "memory_mb": 256}


class DockerSites(unittest.TestCase):
    def setUp(self):
        self.s = load("lunova-site"); self.tmp = Path(tempfile.mkdtemp())
        self.s.SITES = self.tmp; self.calls = []
        self.s.cfg = lambda: {}

    def fake_dk(self, load_out="Loaded image: lunova-shop:r1\n", run_rc=0):
        def dk(*args, check=True, env=None):
            self.calls.append((args, env))
            out = load_out if args[0] == "load" else ""
            rc = run_rc if args[0] == "run" else (1 if args[0] in ("inspect", "image") else 0)
            return NS(returncode=rc, stdout=out, stderr="")
        return dk

    def rel(self, tar=True):
        r = self.tmp / "shop" / "releases" / "r1"; r.mkdir(parents=True)
        if tar: (r / "image.tar.gz").write_bytes(b"x")
        (self.tmp / "shop" / "shared").mkdir(parents=True)
        return r

    def test_caddy_proxies_to_the_container_port(self):
        self.assertIn("reverse_proxy 127.0.0.1:3105", self.s.render_caddy("shop", D))

    def test_volumes_are_named_volumes_only(self):
        ok = ["data:/app/data", "uploads:/var/www/uploads"]
        bad = ["/etc:/host", "../x:/a", "data:relative", "Data:/a", "data:/a b"]
        self.assertTrue(all(self.s.VOLUME_RE.match(v) for v in ok))
        self.assertFalse(any(self.s.VOLUME_RE.match(v) for v in bad))

    def test_archive_must_contain_exactly_this_sites_release_tag(self):
        r = self.rel()
        with mock.patch.object(self.s, "dk", self.fake_dk("Loaded image: evil/other:1\n")):
            with self.assertRaises(SystemExit): self.s.docker_load("shop", r, "r1")
        with mock.patch.object(self.s, "dk", self.fake_dk()): self.s.docker_load("shop", r, "r1")
        with self.assertRaises(SystemExit): self.s.docker_load("shop", self.rel.__self__.tmp / "nope", "r1")

    def test_container_is_published_on_loopback_with_limits_and_secrets_out_of_argv(self):
        r = self.rel(); (self.tmp / "shop" / "shared" / ".env").write_text('API_KEY="s3 cret"\nPORT=9\n')
        with mock.patch.object(self.s, "dk", self.fake_dk()):
            self.assertTrue(self.s.docker_up("shop", D, "r1"))
        args, env = [c for c in self.calls if c[0][0] == "run"][0]
        a = " ".join(args)
        self.assertIn("-p 127.0.0.1:3105:3000", a); self.assertIn("--memory 256m", a); self.assertIn("no-new-privileges", a)
        self.assertIn("-v lunova-shop-data:/app/data", a)
        self.assertNotIn("s3 cret", a); self.assertEqual(env["API_KEY"], "s3 cret"); self.assertEqual(env["PORT"], "9")
        self.assertEqual(env["NODE_ENV"], "production"); self.assertNotIn("--privileged", a)

    def register_args(self, **kw):
        base = dict(site="shop", type="docker", domains="shop.example.com", repo=None, package=None, php=None, database=None, hook=None,
                    root=None, http_only=False, health_path="/", queue=False, scheduler=False, start=None, image=None,
                    container_port=3000, host_port=None, env=["A=1"], volume=["data:/d"], memory=256)
        return NS(**{**base, **kw})

    def test_register_requires_rootless_docker_a_port_and_refuses_database(self):
        self.s.REG = self.tmp / "reg"; self.s.CADDY = self.tmp / "caddy"; self.s.REG.mkdir()
        with mock.patch.object(self.s, "docker_ready", lambda: False):
            with self.assertRaises(SystemExit): self.s.cmd_register(self.register_args())
        with mock.patch.object(self.s, "docker_ready", lambda: True):
            with self.assertRaises(SystemExit): self.s.cmd_register(self.register_args(database="mysql"))
            with self.assertRaises(SystemExit): self.s.cmd_register(self.register_args(container_port=None))
            with self.assertRaises(SystemExit): self.s.cmd_register(self.register_args(volume=["/etc:/x"]))
            with mock.patch.object(self.s, "caddy_reload", lambda: None), mock.patch.object(self.s, "listening_ports", lambda: set()):
                self.s.cmd_register(self.register_args())
        reg = json.loads(self.s.reg_path("shop").read_text())
        self.assertEqual((reg["type"], reg["container_port"], reg["env"], reg["volumes"]), ("docker", 3000, {"A": "1"}, ["data:/d"]))
        self.assertTrue(reg["port"] in self.s.PORTS)

    def test_failed_start_puts_the_previous_container_back(self):
        r = self.rel(); self.s.REG = self.tmp / "reg"; self.s.REG.mkdir()
        self.s.save("shop", D)
        self.s.docker_ready = lambda: True
        a = NS(site="shop", id="r1")
        dk = self.fake_dk(run_rc=1)

        def dk2(*args, check=True, env=None):  # `inspect` of the live container succeeds so there is a previous one to restore
            p = dk(*args, check=check, env=env)
            if args[0] == "inspect": p.returncode = 0
            return p
        with mock.patch.object(self.s, "dk", dk2):
            with self.assertRaises(SystemExit) as e: self.s.release_docker(a, D, r)
        self.assertEqual(e.exception.code, 3)
        names = [c[0][0] for c in self.calls]
        self.assertIn("rename", names); self.assertIn("start", names)
        self.assertFalse((r / ".lunova-ok").exists())


if __name__ == "__main__": unittest.main()
