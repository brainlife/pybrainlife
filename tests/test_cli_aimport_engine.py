"""bl aimport: the engine container's lifecycle and its HTTP API client."""

import io
import os
import socket
import subprocess
import threading
import time

import pytest

from brainlife.cli.aimport import engine as eng
from brainlife.cli.aimport.engine import Engine, EngineError, UsageError, check_folders, docker_args

from .aimport_support import Stub

TOKEN = "f" * 64


# --- docker run arguments ----------------------------------------------------------------------

def args():
    return docker_args("img:1", "/in", "/w", "/k", 4321, "bl-x")


def test_docker_args_publish_on_loopback_and_mount_input_read_only():
    a = args()
    assert a[:4] == ["run", "--rm", "--platform", "linux/amd64"]
    assert a[a.index("-p") + 1] == "127.0.0.1:4321:8765"
    assert "/in:/data:ro" in a and "/w:/work" in a and "/k:/keys" in a
    assert a[a.index("--name") + 1] == "bl-x"
    assert "127.0.0.1:4321" in a and "localhost:4321" in a


def test_docker_args_pass_the_token_by_name_only():
    a = args()
    assert a[a.index("AIMPORT_TOKEN") - 1] == "-e"
    assert not any(TOKEN in x for x in a)


def test_docker_args_run_the_engine_venv_python():
    a = args()
    i = a.index("img:1")
    assert a[i + 1:i + 5] == [eng.ENGINE_PYTHON, "-m", "aimport", "serve"]


def test_model_keys_are_forwarded_by_name_when_set(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "ANTHROPIC_API_KEY" not in args()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    a = args()
    assert a[a.index("ANTHROPIC_API_KEY") - 1] == "-e"
    assert not any("sk-secret" in x for x in a)


def test_default_image_is_one_constant():
    assert eng.ENGINE_IMAGE == "brainlife/aimport:dev"
    assert eng.ENGINE_IMAGE in eng.BUILD_HINT


# --- folder rules ------------------------------------------------------------------------------

@pytest.mark.parametrize("folder,work,keys", [
    ("/in", "/w", "/w/keys"), ("/in", "/w/sub", "/w"), ("/in", "/w", "/in/keys"), ("/in/sub", "/w", "/in"),
    ("/in", "/in/work", "/k"), ("/w/in", "/w", "/k"), ("/same", "/same", "/k"),
    ("/in", "/in/..foo", "/k"), ("/in", "/w", "/w/..keys"),
])
def test_overlapping_folders_are_refused(folder, work, keys):
    with pytest.raises(UsageError):
        check_folders(folder, work, keys)


@pytest.mark.parametrize("folder,work,keys", [("/in:x", "/w", "/k"), ("/in", "/w,ro", "/k"), ("/in", "/w", "/k:/etc")])
def test_paths_with_docker_mount_syntax_are_refused(folder, work, keys):
    with pytest.raises(UsageError, match="must not contain"):
        check_folders(folder, work, keys)


def test_symlinks_are_followed_also_below_a_missing_folder(tmp_path):
    os.makedirs(tmp_path / "work" / "k")
    os.makedirs(tmp_path / "in")
    os.symlink(tmp_path / "work" / "k", tmp_path / "keys")
    for keys in (tmp_path / "keys", tmp_path / "keys" / "new"):
        with pytest.raises(UsageError, match="keys folder"):
            check_folders(str(tmp_path / "in"), str(tmp_path / "work"), str(keys))


def test_separate_folders_pass():
    check_folders("/in", "/w", "/k")
    check_folders("/in", "/w", "/w2")


# --- HTTP API ----------------------------------------------------------------------------------

def api_stub():
    def handler(req):
        if req["path"] == "/status":
            return 200, {}, {"stage": "idle", "auth": req["headers"].get("authorization")}
        if req["path"] == "/busy":
            return 409, {}, {"detail": "busy: scanning"}
        if req["path"] == "/bad":
            return 422, {}, {"detail": [{"loc": ["body"], "msg": "x"}]}
        if req["path"] == "/echo":
            return 200, {}, {"got": req["json"]}
        if req["path"] == "/events":
            return 200, {"Content-Type": "text/event-stream"}, (
                ": keepalive\n\ndata: {\"stage\": \"scanning\", \"message\": \"go\"}\r\n\r\n"
                "data: not json\n\ndata: {\"stage\": \"planned\", \"message\": \"done\"}\n\n"
                "data: {\"stage\": \"executing\"}\n\n")
        return None
    return Stub(handler)


def test_requests_carry_the_bearer_token_and_json():
    with api_stub() as s:
        e = Engine(base=s.base, token="tok")
        assert e.request("GET", "/status") == {"stage": "idle", "auth": "Bearer tok"}
        assert e.request("POST", "/echo", {"a": 1}) == {"got": {"a": 1}}


def test_error_answers_raise_engine_error_with_the_detail():
    with api_stub() as s:
        e = Engine(base=s.base, token="tok")
        with pytest.raises(EngineError) as info:
            e.request("POST", "/busy", {})
        assert info.value.status == 409 and str(info.value) == "busy: scanning"
        with pytest.raises(EngineError) as info:
            e.request("GET", "/bad")
        assert info.value.status == 422 and '"msg":"x"' in str(info.value)


def test_follow_reads_events_up_to_the_first_terminal_stage():
    with api_stub() as s:
        seen = []
        r = Engine(base=s.base, token="tok").follow(lambda ev: seen.append(ev["stage"]))
        assert r == {"stage": "planned", "message": "done"}
        assert seen == ["scanning", "planned"]


def test_follow_fails_when_the_stream_ends_early():
    with Stub(lambda req: (200, {"Content-Type": "text/event-stream"}, 'data: {"stage": "scanning"}\n\n')) as s:
        with pytest.raises(Exception, match="closed the event stream"):
            Engine(base=s.base, token="tok").follow()


def test_wait_ready_gives_up_at_once_on_401():
    with Stub(lambda req: (401, {}, {"detail": "bad token"})) as s:
        t = time.monotonic()
        with pytest.raises(EngineError):
            Engine(base=s.base, token="tok").wait_ready(10)
        assert time.monotonic() - t < 5


# --- lifecycle with a fake docker --------------------------------------------------------------

class FakeProc:
    def __init__(self, code=0, hang=False, stderr=None):
        self.code = code
        self.hang = hang
        self.stderr = stderr
        self.signals = []

    def wait(self, timeout=None):
        if self.hang:
            time.sleep(timeout or 0)
            raise subprocess.TimeoutExpired("docker", timeout)
        return self.code

    def poll(self):
        return self.code

    def kill(self):
        self.signals.append("kill")

    def terminate(self):
        self.signals.append("term")


class FakeDocker:
    """popen stand-in: `docker run` serves /status on the requested port unless told to fail."""

    def __init__(self, image_present=True, pull_ok=True, run="serve", stop_hangs=False):
        self.calls = []
        self.image_present, self.pull_ok, self.run, self.stop_hangs = image_present, pull_ok, run, stop_hangs
        self.servers = []
        self.child = None

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        sub = cmd[1]
        if sub == "image":
            return FakeProc(0 if self.image_present else 1)
        if sub == "pull":
            return FakeProc(0 if self.pull_ok else 1)
        if sub == "stop":
            return FakeProc(0, hang=self.stop_hangs)
        if sub == "run":
            if self.run == "serve":
                port = int(cmd[cmd.index("-p") + 1].split(":")[1])
                self.servers.append(PortServer(port))
                self.child = FakeProc(None)
            else:
                lines = "".join("line %d\n" % i for i in range(1, 6))
                lines += "docker: Error response from daemon: port is already allocated.\n"
                self.child = FakeProc(125, stderr=io.BytesIO(lines.encode()))
            return self.child
        raise AssertionError(cmd)

    def close(self):
        for s in self.servers:
            s.close()


class PortServer(Stub):
    def __init__(self, port):
        from http.server import ThreadingHTTPServer
        super().__init__(lambda req: (200, {}, {"stage": "idle"}))
        self.close()
        # rebind on the port docker would publish
        self.server = ThreadingHTTPServer(("127.0.0.1", port), self.server.RequestHandlerClass)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


def start(d, **kw):
    return Engine.start(image="img", folder="/in", work="/w", keys="/k", name="bl-test", popen=d, log=lambda m: None, **kw)


def test_start_inspects_runs_waits_and_stops_by_name():
    d = FakeDocker()
    try:
        e = start(d)
        cmds = [c for c, _ in d.calls]
        assert cmds[0] == ["docker", "image", "inspect", "img"]
        assert cmds[1][:2] == ["docker", "run"]
        kw = d.calls[1][1]
        assert kw["env"]["AIMPORT_TOKEN"] == e.token and len(e.token) == 64
        assert kw["stderr"] == subprocess.PIPE
        assert not any(e.token in a for a in cmds[1])
        e.stop()
        assert d.calls[-1][0] == ["docker", "stop", "-t", "10", "bl-test"]
        assert d.child.signals == ["term"]  # the docker run child was still alive
    finally:
        d.close()


def test_a_missing_image_is_pulled_with_docker_progress_first():
    d = FakeDocker(image_present=False)
    try:
        start(d).stop()
        assert [c[1] for c, _ in d.calls[:3]] == ["image", "pull", "run"]
        assert d.calls[1][1] == {}  # progress goes to the terminal
    finally:
        d.close()


def test_a_missing_default_image_says_how_to_build_it():
    d = FakeDocker(image_present=False, pull_ok=False)
    with pytest.raises(Exception) as info:
        Engine.start(folder="/in", work="/w", keys="/k", name="bl-test", popen=d, log=lambda m: None)
    assert "docker pull brainlife/aimport:dev failed" in str(info.value)
    assert "docker build --platform linux/amd64 -t brainlife/aimport:dev" in str(info.value)


def test_no_docker_at_all_is_said_plainly():
    def popen(cmd, **kw):
        raise FileNotFoundError("docker")
    with pytest.raises(Exception, match="docker is not installed"):
        Engine.start(folder="/in", work="/w", keys="/k", popen=popen)


def test_docker_run_failing_reports_its_last_stderr_lines():
    d = FakeDocker(run="fail")
    with pytest.raises(Exception) as info:
        start(d)
    msg = str(info.value)
    assert msg.startswith("docker exited with code 125:")
    assert "port is already allocated" in msg and "line 2" in msg and "line 1" not in msg
    assert d.calls[-1][0] == ["docker", "stop", "-t", "10", "bl-test"]
    assert d.child.signals == []  # already gone


def test_a_hung_docker_stop_is_killed_and_the_child_terminated():
    d = FakeDocker(stop_hangs=True)
    try:
        e = start(d, stop_timeout=0.05)
        e.stop()
        assert d.child.signals == ["term"]
    finally:
        d.close()


def test_free_port_is_on_loopback():
    p = eng.free_port()
    s = socket.socket()
    s.bind(("127.0.0.1", p))
    s.close()
