"""bl aimport: run the aimport engine on a local DICOM/NIfTI (or EEG/MEG, microscopy) folder, review
its plan in the terminal, execute it (BIDS output, defacing, validation), check each object with
its brainlife datatype validator and upload the de-identified output to an existing project."""

import os
import re
import secrets
import signal
import subprocess
import sys

import jwt as pyjwt

from ...api.api import get_auth
from . import brainlife_api as bl
from . import upload as uploader
from .bids_walker import walk
from .chunks import ChunkMapError, load_chunk_map, streamed_bytes
from .engine import ENGINE_IMAGE, Engine, EngineError, UsageError, check_folders
from .objects import RefusedError, apply_plan, micr_datasets, preflight, project_files, local_bytes
from .plan_table import render_plan, render_result
from .validators import validate_dataset
from ..tables import upload_tables

UI_MESSAGE = "--ui needs the brainlife.io/aimport page, which is not available yet"
README_URL = "https://github.com/brainlife/ezbids/blob/master/aimport/README.md#the-workflow"
APPROVE_PROMPT = "Approve this plan? [y/N/e(dit)] "
QA_PROMPT = "Upload this dataset? [y/N/v(iewer link again)] "
ENTER_PROMPT = "Press Enter to close the viewer and stop the engine. "
DEFACE_METHODS = ("pydeface", "quickshear")
TARGETS = ("bids", "datatypes")
IMAGE_RE = re.compile(r"[A-Za-z0-9][\w./:@-]*", re.ASCII)
REMOTE_RE = re.compile(r"(https|s3)://\S+", re.IGNORECASE)
SIGNAL_EXIT = {"SIGINT": 130, "SIGTERM": 143, "SIGHUP": 129}


def args(subparsers):
    p = subparsers.add_parser(
        "aimport", help="Import a local folder (DICOM, NIfTI, EEG/MEG, microscopy) into a project with the aimport engine",
        description="Run the aimport engine in Docker on a local folder: review its plan, de-identify, "
                    "deface and validate, then upload the BIDS output to an existing brainlife project.")
    p.add_argument("folder", nargs="?", help="the folder to import")
    p.add_argument("-p", "--project", help="brainlife project id to upload to (it must exist)")
    p.add_argument("--target", default="bids", help="bids or datatypes (also show the brainlife datatype mapping)")
    p.add_argument("--ui", action="store_true", help="review the plan on brainlife.io (not available yet)")
    p.add_argument("--work", help="work folder (default ~/.cache/brainlife/aimport/<project id>/work)")
    p.add_argument("--keys", help="pseudonym key folder (default ~/.config/brainlife/aimport/keys)")
    p.add_argument("--deface", default="pydeface", help="pydeface or quickshear (default pydeface)")
    p.add_argument("--image", default=ENGINE_IMAGE, help="aimport engine image (default %s)" % ENGINE_IMAGE)
    p.add_argument("-y", "--yes", action="store_true", help="approve the plan without asking (for scripts)")
    p.add_argument("-t", "--tag", action="append", default=[], help="add a tag to every uploaded object (repeatable)")
    p.add_argument("--qa", action="store_true",
                   help="open the output in the engine's local QA viewer after validation and ask before uploading")
    p.add_argument("--remote", action="append", default=[],
                   help="a remote microscopy source (https:// or s3://, anonymous reads; repeatable); never printed")
    p.add_argument("--no-upload", dest="upload", action="store_false", help="stop after validation")


def options(ns):
    return {k: getattr(ns, k) for k in ("folder", "project", "target", "ui", "work", "keys", "deface", "image",
                                         "yes", "tag", "qa", "remote", "upload")}


# --- default collaborators (replaced in tests) ------------------------------------------------

def prompt(question):
    try:
        return input(question)
    except EOFError:
        return ""


def open_url(url):
    """Open a URL with the OS opener; raises if there is none (the URL is printed anyway)."""
    if sys.platform == "darwin":
        cmd = ["open", url]
    elif sys.platform == "win32":
        cmd = ["cmd", "/c", "start", "", url]
    else:
        cmd = ["xdg-open", url]
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def load_jwt():
    token = get_auth()
    if not token:
        raise Exception("not logged in; run: bl login")
    try:
        pyjwt.decode(token, options={"verify_signature": False, "verify_exp": True})
    except pyjwt.ExpiredSignatureError:
        raise Exception("your brainlife login has expired; run: bl login")
    except pyjwt.InvalidTokenError:
        raise Exception("the saved brainlife login is not valid; run: bl login")
    return token


def _out(msg):
    print(msg, flush=True)


def _err(msg):
    print(msg, file=sys.stderr, flush=True)


class Deps:
    """What run() talks to; tests replace any of these."""

    def __init__(self, **kw):
        self.Engine = Engine
        self.prompt = prompt
        self.open_url = open_url
        self.log = _out
        self.error = _err
        self.load_jwt = load_jwt
        self.api = None
        self.find_project = bl.project_by_id
        self.all_datatypes = bl.all_datatypes
        self.project_subjects = bl.project_subjects
        self.walk = walk
        self.validate = validate_dataset
        self.upload_datasets = uploader.upload_datasets
        self.update_participants = uploader.update_participants
        self.upload_project_files = uploader.upload_project_files
        self.upload_tables = upload_tables
        self.exit = sys.exit
        for k, v in kw.items():
            if not hasattr(self, k):
                raise TypeError("unknown dependency " + k)
            setattr(self, k, v)


def private_dir(path, refuse_open=False):
    """Create a folder only this user can read. An existing folder keeps its mode, but an existing
    keys folder that others can read is refused."""
    if os.path.exists(path):
        if refuse_open and os.stat(path).st_mode & 0o077:
            raise UsageError("the keys folder %s can be read by other users; run: chmod 700 %s" % (path, path))
        return
    created = []
    d = path
    while not os.path.exists(d):
        created.append(d)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    os.makedirs(path, mode=0o700)
    for d in created:  # makedirs' mode is masked by the umask
        os.chmod(d, 0o700)


def _gb(n):
    return "%.2f GB" % (n / 1e9)


def run(opts, deps=None):
    """-> exit code: 0 done (or nothing approved), 1 failed, 2 usage."""
    deps = deps or Deps()
    log, error = deps.log, deps.error
    state = {"engine": None, "name": None, "stopped": False, "interrupted": False}

    def stop_engine():
        if state["stopped"]:
            return
        state["stopped"] = True
        engine = state["engine"] or (deps.Engine(name=state["name"]) if state["name"] else None)
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass

    def on_signal(signum, _frame):
        state["interrupted"] = True
        error("aimport: interrupted; stopping the engine")
        stop_engine()
        deps.exit(SIGNAL_EXIT[signal.Signals(signum).name])

    previous = {}
    try:
        # flags and folders
        if opts.get("ui"):
            raise UsageError(UI_MESSAGE)
        target = opts.get("target") or "bids"
        if target not in TARGETS:
            raise UsageError("--target must be bids or datatypes")
        deface = opts.get("deface") or "pydeface"
        if deface not in DEFACE_METHODS:
            raise UsageError("--deface must be pydeface or quickshear")
        image = opts.get("image") or ENGINE_IMAGE
        if not IMAGE_RE.fullmatch(image):
            raise UsageError("--image is not a docker image reference: " + image)
        if not opts.get("folder"):
            raise UsageError("please give the folder to import")
        folder = os.path.abspath(os.path.expanduser(opts["folder"]))
        if not os.path.isdir(folder):
            raise UsageError("not a folder: " + folder)
        project_id = opts.get("project")
        if not project_id:
            raise UsageError("please give the brainlife project id (--project)")
        if not bl.OBJECT_ID.fullmatch(project_id):
            raise UsageError("--project must be a brainlife project id: " + project_id)
        # remote sources for the microscopy modules; the engine checks them again. Never echoed:
        # a URL can name the donor
        remote = list(opts.get("remote") or [])
        for url in remote:
            if not isinstance(url, str) or not REMOTE_RE.fullmatch(url):
                raise UsageError("--remote must be an https:// or s3:// URL")

        # the project must exist; aimport never creates one
        api = deps.api or bl.default_api()
        headers = {"Authorization": "Bearer " + deps.load_jwt()}
        project = deps.find_project(headers, project_id, api)
        if not project:
            raise Exception("project %s not found" % project_id)

        home = os.path.expanduser("~")
        work = os.path.abspath(os.path.expanduser(opts.get("work") or os.path.join(
            home, ".cache", "brainlife", "aimport", project["_id"], "work")))
        keys = os.path.abspath(os.path.expanduser(opts.get("keys") or os.path.join(
            home, ".config", "brainlife", "aimport", "keys")))
        check_folders(folder, work, keys)
        private_dir(work)
        private_dir(keys, refuse_open=True)

        existing = deps.project_subjects(headers, project["_id"], api)

        # start the engine; from here on every exit path stops it
        state["name"] = "bl-aimport-" + secrets.token_hex(4)
        for sig in SIGNAL_EXIT:
            if hasattr(signal, sig):
                try:
                    previous[sig] = signal.signal(getattr(signal, sig), on_signal)
                except ValueError:
                    pass  # not the main thread
        log("Starting the aimport engine (%s)..." % image)
        engine = state["engine"] = deps.Engine.start(image=image, folder=folder, work=work, keys=keys, name=state["name"])

        def on_event(ev):
            log("  %s%s" % (ev.get("stage"), ": " + ev["message"] if ev.get("message") else ""))

        def open_viewer():
            """A one-time viewer link (POST /viewer/session), or None when the engine has none."""
            try:
                session = engine.request("POST", "/viewer/session")
            except EngineError as err:
                if err.status == 404:
                    error("aimport: the engine image is too old for --qa; rebuild it")
                    return None
                raise
            url = engine.base + session["url"]
            log("QA viewer: " + url)
            try:
                deps.open_url(url)
            except Exception:
                log("(could not open a browser; open the address above yourself)")
            return url

        # scan
        scan = {"project_id": project["_id"], "existing_subjects": existing["existing_subjects"],
                "existing_sessions": existing["existing_sessions"], "target": target}
        if remote:
            scan["remote"] = remote
        engine.request("POST", "/scan", scan)
        scanned = engine.follow(on_event)
        if scanned["stage"] != "planned":
            error("aimport: the scan %s%s" % (scanned["stage"], ": " + scanned["message"] if scanned.get("message") else ""))
            return 1

        # review
        plan = engine.request("GET", "/plan")
        log(render_plan(plan, target=target, deface=deface))
        if not opts.get("yes"):
            while True:
                answer = str(deps.prompt(APPROVE_PROMPT)).strip().lower()
                if answer in ("y", "yes"):
                    break
                if answer in ("e", "edit"):
                    log("Edit the plan with PATCH /plan, as described in " + README_URL)
                    log("  engine: " + engine.base)
                    log("  token:  %s (valid only while this engine runs)" % engine.token)
                    log("  for example: curl -s -X PATCH %s/plan -H \"Authorization: Bearer %s\" "
                        "-H 'Content-Type: application/json' -d '{\"edits\": [{\"id\": \"<entry id>\", \"exclude\": true}]}'"
                        % (engine.base, engine.token))
                    deps.prompt("Press Enter when you are done editing ")
                    plan = engine.request("GET", "/plan")
                    log(render_plan(plan, target=target, deface=deface))
                    continue
                log("The plan was not approved. Nothing was written or uploaded.")
                return 0

        # approve and execute
        engine.request("POST", "/approve", {"deface_method": deface})
        engine.request("POST", "/execute")
        executed = engine.follow(on_event)
        status = engine.request("GET", "/status")
        log(render_result(status))
        if executed["stage"] != "validated" or status.get("stage") != "validated":
            msg = status.get("message") or executed.get("message")
            error("aimport: the output is %s%s; nothing was uploaded" % (status.get("stage"), " (%s)" % msg if msg else ""))
            # an invalid output was written: it can still be looked at, to see what to fix
            if opts.get("qa") and status.get("stage") == "invalid":
                if open_viewer() is None:
                    return 1
                deps.prompt(ENTER_PROMPT)
            return 1

        # without a manifest, objects cannot be matched to plan entries
        manifest = status.get("manifest")
        if not isinstance(manifest, dict):
            error("aimport: the engine image is too old (its /status has no manifest); rebuild it")
            return 1
        plan = engine.request("GET", "/plan")

        # the viewer is served by the engine: open it and answer before the engine stops
        confirmed = False
        if opts.get("qa"):
            if open_viewer() is None:
                return 1
            if opts.get("upload", True):
                while True:
                    answer = str(deps.prompt(QA_PROMPT)).strip().lower()
                    if answer in ("y", "yes"):
                        confirmed = True
                        break
                    if answer == "v":  # the one-time code expires after 60 s: a fresh one
                        if open_viewer() is None:
                            return 1
                        continue
                    log("Not uploaded. The output stays in " + os.path.join(work, "output", "bids"))
                    return 0
            else:
                # nothing to upload: keep the engine (and so the viewer) up until the person is done
                deps.prompt(ENTER_PROMPT)
            # bad channels marked in the viewer rewrite channels.tsv and validate the output again:
            # go on only if it is still valid (a save in progress is waited for)
            after = engine.request("GET", "/status")
            if after.get("stage") == "executing":
                engine.follow(lambda ev: None)
                after = engine.request("GET", "/status")
            if after.get("stage") != "validated":
                error("aimport: after the QA review the output is %s%s; nothing was uploaded" % (
                    after.get("stage"), " (%s)" % after["message"] if after.get("message") else ""))
                return 1
            manifest = after.get("manifest") if isinstance(after.get("manifest"), dict) else manifest

        # everything below works on the host side of the engine's /work mount; the engine is done
        stop_engine()
        bids_dir = os.path.join(work, "output", "bids")
        # reference datasets: where their chunks are (input paths and URLs: local only, never printed)
        chunk_map = load_chunk_map(work, bids_dir, folder, status.get("chunk_map"))
        preflight(bids_dir, chunk_map=chunk_map, manifest=manifest, input_dir=folder)
        bids = deps.walk(bids_dir)
        datatypes = {d["name"]: d for d in deps.all_datatypes(headers, api)}
        datasets, warnings, notes = apply_plan(bids, plan, manifest, datatypes, bids_dir)
        # micr images: one object per written .ome.zarr
        micr, micr_warnings, held = micr_datasets(bids_dir, plan, manifest, datatypes)
        datasets += micr
        for w in warnings + micr_warnings:
            log("! " + w)
        for n in notes:
            log(n)

        # host datatype validators; a failure keeps that object out of the upload
        good, blocked = [], []
        for item in datasets:
            desc = item["dataset"]["desc"]
            r = deps.validate(item, datatypes.get(item["dataset"]["datatype"]))
            if not r["ok"]:
                error("aimport: not uploading %s: %s" % (desc, "; ".join(r["errors"]) or "validator failed"))
                blocked.append(item)
                continue
            if r.get("skipped"):
                log("! %s was not checked by a datatype validator (%s)" % (desc, r["skipped"]))
            for w in r.get("warnings") or []:
                log("! %s: %s" % (desc, w))
            good.append(item)
        # blocked objects' files are not sent as project files either
        files = project_files(bids_dir, datasets, held)

        object_rels = [os.path.relpath(full, bids_dir) for item in good for full in item["files"].values()]
        streamed, upper, arrays = streamed_bytes(chunk_map, good)
        log("%d objects, %s from local output, %s streamed from sources%s" % (
            len(good), _gb(local_bytes(bids_dir, object_rels + files)), _gb(streamed),
            " (at most: remote chunk sizes are known only when they are read)" if upper else ""))

        if not opts.get("upload", True):
            log("--no-upload: stopping here. %d object(s) and %d project file(s) would be uploaded from %s"
                % (len(good), len(files), bids_dir))
            return 1 if blocked else 0

        # streaming from the sources can be long: ask, unless --yes or the --qa question was answered
        if arrays > 0 and not opts.get("yes") and not confirmed:
            answer = str(deps.prompt("Upload? [y/N] ")).strip().lower()
            if answer not in ("y", "yes"):
                log("Not uploaded. The output stays in " + bids_dir)
                return 0

        if bids["participants"] or bids["participants_json"]:
            deps.update_participants(headers, project, bids, api=api, log=log)
        uploaded, skipped = deps.upload_datasets(headers, project, good, tags=opts.get("tag") or [], api=api,
                                                 log=log, chunk_map=chunk_map)
        deps.upload_project_files(headers, project, bids_dir, files, api=api)
        # phenotype/, sessions, scans, ... also become project tables (rows linked to subjects)
        tables = deps.upload_tables(headers, project, bids_dir, api=api, log=log)
        log("Uploaded %d object(s), skipped %d already in the project, %d project file(s), %d table(s)"
            % (len(uploaded), len(skipped), len(files), tables))
        if blocked:
            error("aimport: %d object(s) failed validation and were not uploaded" % len(blocked))
        log("%s/project/%s" % (api.get("main") or "https://brainlife.io", project["_id"]))
        return 1 if blocked else 0
    except UsageError as err:
        if state["interrupted"]:
            return 1
        error(str(err))
        return 2
    except (EngineError, ChunkMapError, RefusedError, Exception) as err:
        # after a signal the in-flight request fails because the engine stops: say nothing more
        if state["interrupted"]:
            return 1
        error("aimport: %s" % err)  # the message only, no traceback
        return 1
    finally:
        if state["name"]:
            stop_engine()
        for sig, handler in previous.items():
            signal.signal(getattr(signal, sig), handler)


def main(ns):
    return run(options(ns))
