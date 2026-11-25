"""The aimport engine: a Docker container serving the engine's HTTP API on 127.0.0.1.

The session token travels in the docker child's environment (``-e AIMPORT_TOKEN``, by name
only), so it never shows in the process list.
"""

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from collections import deque

import requests

# one constant; pinned until maintainers publish a tag
ENGINE_IMAGE = "brainlife/aimport:dev"

BUILD_HINT = (
    "build it from the ezBIDS repository (https://github.com/brainlife/ezbids/tree/master/aimport): "
    "docker build --platform linux/amd64 -t " + ENGINE_IMAGE + " -f aimport/Dockerfile ."
)

# the image's own python is 2.7; aimport lives in this venv
ENGINE_PYTHON = "/opt/aimport-venv/bin/python"

# forwarded by name only (-e NAME) so values never show in the process list
MODEL_ENV = ["AIMPORT_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OLLAMA_BASE_URL", "DASHSCOPE_API_KEY"]

TERMINAL = ("planned", "validated", "invalid", "failed")
STDERR_KEEP = 20


class EngineError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class UsageError(Exception):
    pass


def docker_args(image, folder, work, keys, port, name=None):
    """The docker argument list; the token is not in it (it travels in the child's environment)."""
    args = ["run", "--rm", "--platform", "linux/amd64"]
    if name:
        args += ["--name", name]
    args += ["-e", "AIMPORT_TOKEN"]
    for v in MODEL_ENV:
        if os.environ.get(v):
            args += ["-e", v]
    args += [
        "-p", "127.0.0.1:%d:8765" % port,
        "-v", "%s:/data:ro" % folder,
        "-v", "%s:/work" % work,
        "-v", "%s:/keys" % keys,
        image or ENGINE_IMAGE,
        ENGINE_PYTHON, "-m", "aimport", "serve",
        "--input", "/data", "--work", "/work", "--keys", "/keys",
        "--host", "0.0.0.0", "--port", "8765",
        "--host-allow", "127.0.0.1:%d" % port,
        "--host-allow", "localhost:%d" % port,
    ]
    return args


def _real(p):
    # follows symlinks in the part that exists
    return os.path.realpath(os.path.abspath(p))


def _inside(child, parent):
    rel = os.path.relpath(_real(child), _real(parent))
    if rel == ".":
        return True
    return not (rel == ".." or rel.startswith(".." + os.sep) or os.path.isabs(rel))


def check_folders(folder, work, keys):
    """The keys folder must be separate from the work and input folders (either direction),
    and so must work and input (a re-scan would ingest the staged originals)."""
    # docker -v splits on ':' (and --mount on ',')
    for name, d in (("input", folder), ("work", work), ("keys", keys)):
        if re.search(r"[:,]", d):
            raise UsageError("the %s folder path must not contain ':' or ',': %s" % (name, d))
    for name, other in (("work", work), ("input", folder)):
        if _inside(keys, other) or _inside(other, keys):
            raise UsageError("the keys folder (%s) must not be inside or contain the %s folder (%s)" % (keys, name, other))
    if _inside(work, folder) or _inside(folder, work):
        raise UsageError("the work folder (%s) must not be inside or contain the input folder (%s)" % (work, folder))


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def error_message(text):
    try:
        body = json.loads(text)
        if isinstance(body, dict) and "detail" in body:
            d = body["detail"]
            return d if isinstance(d, str) else json.dumps(d, separators=(",", ":"))
    except ValueError:
        pass
    return text


def _docker(popen, args, quiet):
    """Run a docker command to the end; returns its exit code."""
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL} if quiet else {}
    p = popen(["docker"] + args, **kw)
    return p.wait()


def ensure_image(popen, image, log=None):
    """Pull the image first (with docker's own progress) so the ready timeout covers startup only."""
    if _docker(popen, ["image", "inspect", image], True) == 0:
        return
    (log or _stderr)("Pulling %s (first run; this can take a while)..." % image)
    code = _docker(popen, ["pull", image], False)
    if code != 0:
        raise Exception("docker pull %s failed (code %s)" % (image, code))


def _stderr(msg):
    print(msg, file=sys.stderr, flush=True)


class Engine:
    def __init__(self, base=None, token=None, name=None, popen=subprocess.Popen):
        self.base = base
        self.token = token
        self.name = name
        self.popen = popen
        self.child = None
        self.stderr_lines = deque(maxlen=STDERR_KEEP)
        self._stderr_thread = None
        self.spawn_error = None
        self.stop_timeout = 30.0
        self._http = requests.Session()
        self._http.trust_env = False  # 127.0.0.1 only: no proxy, no netrc

    @classmethod
    def start(cls, image=None, folder=None, work=None, keys=None, name=None, popen=subprocess.Popen,
              timeout=120.0, stop_timeout=None, log=None):
        image = image or ENGINE_IMAGE
        try:
            ensure_image(popen, image, log)
        except FileNotFoundError:
            raise Exception("docker could not get the engine image: docker is not installed or not on the PATH")
        except Exception as err:
            msg = "docker could not get the engine image: %s" % err
            if image == ENGINE_IMAGE:
                msg += "; " + BUILD_HINT
            raise Exception(msg)
        port = free_port()
        token = secrets.token_hex(32)
        name = name or "bl-aimport-" + secrets.token_hex(4)
        args = docker_args(image, folder, work, keys, port, name)
        engine = cls(base="http://127.0.0.1:%d" % port, token=token, name=name, popen=popen)
        if stop_timeout:
            engine.stop_timeout = stop_timeout
        env = dict(os.environ)
        env["AIMPORT_TOKEN"] = token
        try:
            engine.child = popen(["docker"] + args, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except OSError as err:
            engine.spawn_error = err
        if engine.child is not None and getattr(engine.child, "stderr", None) is not None:
            # keep the last lines only (docker's own errors, e.g. a port or mount problem)
            def read():
                try:
                    for line in iter(engine.child.stderr.readline, b""):
                        if isinstance(line, bytes):
                            line = line.decode("utf-8", "replace")
                        engine.stderr_lines.append(line.rstrip("\r\n"))
                except (OSError, ValueError):
                    pass
            engine._stderr_thread = threading.Thread(target=read, daemon=True)
            engine._stderr_thread.start()
        try:
            engine.wait_ready(timeout)
        except BaseException:
            engine.stop()
            raise
        return engine

    def exit_error(self):
        """Why the docker run child is gone, or None while it runs."""
        if self.spawn_error is not None:
            return self.spawn_error
        if self.child is None:
            return None
        code = self.child.poll()
        if code is None:
            return None
        if self._stderr_thread is not None:
            self._stderr_thread.join(2)
        last = [l for l in self.stderr_lines if l.strip()][-5:]
        return Exception("docker exited with code %s" % code + (":\n" + "\n".join(last) if last else ""))

    def _headers(self):
        return {"Authorization": "Bearer " + self.token}

    def request(self, method, path, body=None):
        kw = {"headers": self._headers(), "timeout": (10, 600)}
        if body is not None:
            kw["json"] = body
        res = self._http.request(method, self.base + path, **kw)
        text = res.text
        if res.status_code < 200 or res.status_code >= 300:
            raise EngineError(error_message(text), res.status_code)
        if not text:
            return {}
        try:
            return json.loads(text)
        except ValueError:
            raise EngineError("bad answer from the engine: " + text[:200], res.status_code)

    def follow(self, on_event=None):
        """Read /events until a terminal stage; calls on_event for every event."""
        res = self._http.get(self.base + "/events", headers=self._headers(), stream=True, timeout=(10, None))
        try:
            if res.status_code < 200 or res.status_code >= 300:
                raise EngineError(error_message(res.text), res.status_code)
            for raw in res.iter_lines(decode_unicode=False):
                line = raw.decode("utf-8", "replace").rstrip("\r")
                if not line.startswith("data:"):
                    continue  # keepalives (": ...") and blanks
                try:
                    ev = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if not isinstance(ev, dict):
                    continue
                if on_event:
                    on_event(ev)
                if ev.get("stage") in TERMINAL:
                    return {"stage": ev.get("stage"), "message": ev.get("message")}
            raise Exception("the engine closed the event stream before the run finished")
        finally:
            res.close()

    def wait_ready(self, timeout=120.0):
        start = time.monotonic()
        last = None
        while time.monotonic() - start < timeout:
            exited = self.exit_error()
            if exited is not None:
                raise exited
            try:
                self.request("GET", "/status")
                return
            except EngineError as err:
                last = err
                if err.status == 401:
                    raise
            except requests.RequestException as err:
                last = err
            time.sleep(0.5)
        raise Exception("the engine did not become ready" + (": %s" % last if last else ""))

    def stop(self):
        """docker stop (10 s grace) with a watchdog, then make sure the docker run child is gone."""
        if not self.name:
            return
        p = None
        try:
            p = self.popen(["docker", "stop", "-t", "10", self.name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.wait(timeout=self.stop_timeout)
        except subprocess.TimeoutExpired:
            try:
                p.kill()
            except Exception:
                pass
        except Exception:
            pass
        if self.child is not None and self.child.poll() is None:
            try:
                self.child.terminate()
            except Exception:
                pass
