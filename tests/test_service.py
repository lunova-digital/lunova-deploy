"""Offline tests for `service` sites (no Docker, no server): python3 -m unittest discover -s tests"""
import importlib.machinery, importlib.util, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(ROOT / "server" / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec); loader.exec_module(mod)
    return mod


CFG = {"allowed_images": ["bbernhard/signal-cli-rest-api"], "max_memory_mb": 1024, "min_host_port": 1024}
GOOD = {"image": "bbernhard/signal-cli-rest-api:0.95", "container_port": 8080, "host_port": 8080, "memory_mb": 768,
        "env": {"MODE": "normal"}, "volumes": ["signal-data:/home/.local/share/signal-cli"]}


class ContainerHelper(unittest.TestCase):
    def setUp(self): self.c = load("lunova-container")

    def refused(self, **over):
        spec = {**GOOD, **over}
        with self.assertRaises(SystemExit): self.c.validate("lunova-signal", spec, CFG)

    def test_accepts_the_signal_gateway(self):
        v = self.c.validate("lunova-signal", GOOD, CFG)
        self.assertEqual(v["image"], "bbernhard/signal-cli-rest-api:0.95")
        self.assertEqual(v["volumes"], [("signal-data", "/home/.local/share/signal-cli")])

    def test_refuses_images_that_are_not_allow_listed_or_not_pinned(self):
        self.refused(image="alpine:3.20")
        self.refused(image="evil/signal-cli-rest-api:0.95")
        self.refused(image="bbernhard/signal-cli-rest-api:latest")
        self.refused(image="bbernhard/signal-cli-rest-api")
        self.refused(image="bbernhard/signal-cli-rest-api@sha256:abc")
        self.refused(image="BBernhard/Signal:1")

    def test_refuses_bad_ports_memory_env_and_mounts(self):
        self.refused(host_port=80)
        self.refused(host_port=70000)
        self.refused(container_port=0)
        self.refused(memory_mb=8192)
        self.refused(env={"lower": "x"})
        self.refused(env={"A": "line\nbreak"})
        self.refused(volumes=["/etc:/etc"])                    # host paths can never be mounted
        self.refused(volumes=["data:/proc/self"])
        self.refused(volumes=["data:/a/../etc"])
        self.refused(volumes=["a:/x", "b:/x", "c:/x", "d:/x", "e:/x"])

    def test_unquote_matches_what_lunova_site_writes(self):
        self.assertEqual(self.c.unquote('"a \\"b\\" \\$c"'), 'a "b" $c')
        self.assertEqual(self.c.unquote("plain"), "plain")


class SiteService(unittest.TestCase):
    def setUp(self):
        self.s = load("lunova-site")
        self.tmp = Path(tempfile.mkdtemp())
        self.s.SITES = self.tmp / "sites"; self.s.REG = self.tmp / "reg"
        (self.s.SITES / "lunova-signal" / "releases").mkdir(parents=True)
        self.d = {"site": "lunova-signal", "type": "service", "repo": "lunova-digital/lunova-signal-gateway", "branch": "main", **{k: GOOD[k] for k in GOOD}}
        self.calls = []

    def release(self, rid):
        r = self.s.SITES / "lunova-signal" / "releases" / rid; r.mkdir(parents=True, exist_ok=True); return r

    def run_release(self, rid, up_ok=True, health=200):
        self.release(rid)
        def fake(*args, check=True):
            self.calls.append(args); return mock.Mock(returncode=0 if (up_ok or args[1:3] != ("lunova-signal", rid)) else 1, stdout="", stderr="")
        a = mock.Mock(site="lunova-signal", id=rid)
        with mock.patch.object(self.s, "container", fake), mock.patch.object(self.s, "health", lambda *x: (health, "url")):
            try: self.s.release_service(a, self.d, self.s.SITES / "lunova-signal" / "releases" / rid); return 0
            except SystemExit as e: return e.code

    def test_a_healthy_release_is_switched_and_marked(self):
        self.assertEqual(self.run_release("r1"), 0)
        cur = self.s.SITES / "lunova-signal" / "current"
        self.assertEqual(os.path.realpath(cur), str(self.s.SITES / "lunova-signal" / "releases" / "r1"))
        spec = json.loads((self.s.SITES / "lunova-signal" / "releases" / "r1" / ".lunova-service.json").read_text())
        self.assertEqual(spec["image"], GOOD["image"]); self.assertTrue((self.s.SITES / "lunova-signal" / "releases" / "r1" / ".lunova-ok").exists())

    def test_a_failed_health_check_puts_the_previous_release_back(self):
        self.run_release("r1")
        self.assertEqual(self.run_release("r2", health=500), 3)
        self.assertEqual(os.path.basename(os.path.realpath(self.s.SITES / "lunova-signal" / "current")), "r1")
        self.assertIn(("up", "lunova-signal", "r1"), self.calls)               # the old container configuration was started again

    def test_a_container_that_will_not_start_leaves_the_live_service_alone(self):
        self.run_release("r1")
        self.assertEqual(self.run_release("r2", up_ok=False), 3)
        self.assertEqual(os.path.basename(os.path.realpath(self.s.SITES / "lunova-signal" / "current")), "r1")

    def test_a_service_takes_no_domain_and_needs_containers_enabled(self):
        a = mock.Mock(site="lunova-signal", type="service", domains="signal.example.com", repo=None)
        with self.assertRaises(SystemExit): self.s.cmd_register(a)

    def test_health_uses_the_host_port(self):
        seen = {}
        class R:  # noqa
            status = 204
        class Op:
            def open(self, req, timeout=0): seen["url"] = req.full_url; return R()
        with mock.patch("urllib.request.build_opener", lambda *x: Op()):
            code, url = self.s.health("lunova-signal", {**self.d, "health_path": "/v1/health"})
        self.assertEqual((code, url), (204, "http://127.0.0.1:8080/v1/health"))


if __name__ == "__main__":
    unittest.main()
