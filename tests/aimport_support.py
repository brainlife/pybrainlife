"""Shared helpers for the bl aimport tests: a local HTTP stub, a small BIDS tree and a fake engine.
Nothing here touches the network beyond 127.0.0.1."""

import gzip
import io
import json
import os
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PROJECT = {"_id": "0123456789abcdef01234567", "group_id": 7}
DATATYPES = [
    {"_id": "dt-t1w", "name": "neuro/anat/t1w", "files": [{"id": "t1", "filename": "t1.nii.gz", "required": True}]},
    {"_id": "dt-t2w", "name": "neuro/anat/t2w", "files": [{"id": "t2", "filename": "t2.nii.gz", "required": True}]},
    {"_id": "dt-dwi", "name": "neuro/dwi", "files": []},
    {"_id": "dt-func", "name": "neuro/func/task", "files": []},
    {"_id": "dt-zarr", "name": "neuro/ome-zarr", "files": [{"id": "zarr", "dirname": "data.ome.zarr", "required": True}]},
    {"_id": "dt-bv", "name": "neuro/eeg/brainvision", "files": [
        {"id": "eeg", "filename": "eeg.eeg"}, {"id": "vhdr", "filename": "eeg.vhdr"},
        {"id": "vmrk", "filename": "eeg.vmrk"}, {"id": "channels", "filename": "channels.tsv"}]},
]


class Stub:
    """A local HTTP server; handler(req) -> (status, headers, body) or None for 404.
    req: {"method", "path", "query", "headers", "body" (bytes), "json"}."""

    def __init__(self, handler, keep_bodies=True):
        self.calls = []
        stub = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _body(self):
                if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
                    size_total = 0
                    parts = []
                    while True:
                        size = int(self.rfile.readline().strip().split(b";")[0], 16)
                        if size == 0:
                            self.rfile.readline()
                            break
                        data = self.rfile.read(size)
                        self.rfile.readline()
                        size_total += len(data)
                        if keep_bodies:
                            parts.append(data)
                    return b"".join(parts), size_total
                n = int(self.headers.get("Content-Length") or 0)
                data = self.rfile.read(n) if n else b""
                return data, len(data)

            def _handle(self):
                u = urlsplit(self.path)
                body, size = self._body()
                req = {"method": self.command, "path": u.path, "query": {k: v[0] for k, v in parse_qs(u.query).items()},
                       "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body, "size": size}
                try:
                    req["json"] = json.loads(body) if body and "json" in req["headers"].get("content-type", "") else None
                except ValueError:
                    req["json"] = None
                stub.calls.append(req)
                out = handler(req)
                if out is None:
                    out = (404, {}, b'{"message": "unexpected"}')
                status, headers, payload = out
                if isinstance(payload, (dict, list)):
                    payload = json.dumps(payload).encode()
                    headers = dict({"Content-Type": "application/json"}, **headers)
                elif isinstance(payload, str):
                    payload = payload.encode()
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                if "Content-Length" not in headers:
                    self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)

            do_GET = do_POST = do_PUT = do_PATCH = do_HEAD = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(text, bytes) else "w"
    with open(path, mode) as f:
        f.write(text)


def make_bids(root):
    """A small BIDS output: two subjects, anat/dwi/func, a root-level sidecar, participants and
    project-level files."""
    write(os.path.join(root, "dataset_description.json"), '{"Name": "pilot", "BIDSVersion": "1.10.0"}')
    write(os.path.join(root, "README"), "a pilot\n")
    write(os.path.join(root, "CHANGES"), "1.0\n")
    write(os.path.join(root, "participants.tsv"), "participant_id\tage\nsub-01\t30\nsub-02\t40\n")
    write(os.path.join(root, "participants.json"), '{"participant_id": {}, "age": {"Description": "age in years"}}')
    write(os.path.join(root, "task-rest_bold.json"), '{"RepetitionTime": 2, "TaskName": "rest"}')
    write(os.path.join(root, "phenotype", "moca.tsv"), "participant_id\tmoca\nsub-01\t28\n")
    a = os.path.join(root, "sub-01")
    write(os.path.join(a, "anat", "sub-01_T1w.nii.gz"), b"t1")
    write(os.path.join(a, "anat", "sub-01_T1w.json"), '{"EchoTime": 0.003}')
    write(os.path.join(a, "dwi", "sub-01_dwi.nii.gz"), b"dwi")
    write(os.path.join(a, "dwi", "sub-01_dwi.bval"), "0 1000\n")
    write(os.path.join(a, "dwi", "sub-01_dwi.bvec"), "0 1\n0 0\n0 0\n")
    write(os.path.join(a, "func", "sub-01_task-rest_run-1_bold.nii.gz"), b"bold")
    write(os.path.join(a, "func", "sub-01_task-rest_run-1_events.tsv"), "onset\tduration\n0\t1\n")
    b = os.path.join(root, "sub-02", "ses-1")
    write(os.path.join(b, "anat", "sub-02_ses-1_T1w.nii.gz"), b"t1b")
    write(os.path.join(b, "anat", "sub-02_ses-1_T2w.nii.gz"), b"t2b")
    write(os.path.join(b, "sub-02_ses-1_scans.tsv"), "filename\nanat/sub-02_ses-1_T1w.nii.gz\n")
    return root


def tar_members(data):
    """{name: bytes} of a tar.gz."""
    out = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar:
            out[m.name] = tar.extractfile(m).read() if m.isfile() else None
    return out


class FakeEngine:
    """Stands in for engine.Engine: answers requests from a script and records them."""

    base = "http://127.0.0.1:9999"
    token = "tok123"

    def __init__(self, plan, status, scan_stage="planned", exec_stage="validated"):
        self.plan = plan
        self.status = status
        self.stages = [scan_stage, exec_stage]
        self.calls = []
        self.stops = 0
        self.started = None
        self.errors = {}
        self.hooks = {}  # "METHOD /path" -> fn(body) returning an answer (or raising)
        self.statuses = []  # GET /status answers after the first, in order

    def request(self, method, path, body=None):
        key = method + " " + path
        self.calls.append((key, body))
        if key in self.errors:
            raise self.errors[key]
        if key in self.hooks:
            return self.hooks[key](body)
        if key == "GET /plan":
            return self.plan
        if key == "GET /status":
            n = sum(1 for k, _ in self.calls if k == "GET /status")
            if n > 1 and self.statuses:
                return self.statuses[min(n - 2, len(self.statuses) - 1)]
            return self.status
        return {}

    def follow(self, on_event=None):
        stage = self.stages.pop(0) if self.stages else "validated"
        ev = {"stage": stage, "message": "boom" if stage == "failed" else None}
        if on_event:
            on_event(ev)
        return ev

    def stop(self):
        self.stops += 1

    def keys(self):
        return [k for k, _ in self.calls]


def engine_class(fake, start_error=None):
    class E:
        def __init__(self, name=None, **kw):
            self.name = name

        @staticmethod
        def start(**kw):
            fake.started = kw
            if start_error:
                raise start_error
            return fake

        def stop(self):
            fake.stops += 1

    return E


def gunzip(data):
    return gzip.decompress(data)
