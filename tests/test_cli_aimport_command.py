"""bl aimport: the whole command, with a fake engine and fake brainlife.io calls."""

import json
import os
import signal
import stat

import pytest

from brainlife.cli.aimport import brainlife_api as bl
from brainlife.cli.aimport.command import APPROVE_PROMPT, ENTER_PROMPT, QA_PROMPT, Deps, run
from brainlife.cli.aimport.engine import EngineError

from .aimport_support import DATATYPES, PROJECT, FakeEngine, Stub, engine_class, make_bids, write

PLAN = {"dataset_name": "pilot", "deface_method": "pydeface", "warnings": [], "ancillary": [], "entries": [
    {"id": "e1", "subject": "01", "session": None, "datatype": "anat", "suffix": "T1w", "entities": {},
     "deface": True, "status": "ok", "source": "heuristic", "confidence": 1,
     "brainlife_datatype": "neuro/anat/t1w", "brainlife_tags": []}]}
VALIDATED = {"stage": "validated", "message": None, "output_dir": "/work/output/bids",
             "manifest": {"e1": ["sub-01/anat/sub-01_T1w.nii.gz", "sub-01/anat/sub-01_T1w.json"]},
             "validation": {"error_count": 0, "warning_count": 0, "errors": [], "warnings": []}}
VIEWER = {"code": "abc", "url": "/viewer/open?code=abc"}


class Case:
    def __init__(self, tmp_path, answers=(), status=None, plan=None, **opts):
        root = os.path.realpath(str(tmp_path))
        self.input = os.path.join(root, "input")
        self.work = os.path.join(root, "work")
        self.keys = os.path.join(root, "keys")
        self.bids = os.path.join(self.work, "output", "bids")
        os.makedirs(self.input)
        make_bids(self.bids)  # what the engine would have written
        self.engine = FakeEngine(plan or PLAN, status or VALIDATED)
        self.engine.hooks["POST /viewer/session"] = lambda body: VIEWER
        self.answers = list(answers)
        self.prompts, self.out, self.opened, self.exits = [], [], [], []
        self.rec = {"datasets": None, "participants": 0, "files": None, "stops_at_upload": None}
        self.validate_result = lambda item: {"ok": True, "errors": [], "warnings": []}
        self.opts = dict(folder=self.input, project=PROJECT["_id"], work=self.work, keys=self.keys, yes=True,
                         upload=True, target="bids", deface="pydeface", tag=[])
        self.opts.update(opts)
        self.start_error = None

    def prompt(self, q):
        self.prompts.append(q)
        return self.answers.pop(0) if self.answers else ""

    def deps(self, **over):
        rec = self.rec

        def upload_datasets(headers, project, datasets, tags=(), api=None, log=None, chunk_map=None):
            rec["stops_at_upload"] = self.engine.stops
            rec.update(datasets=datasets, tags=tags, chunk_map=chunk_map, headers=headers)
            return [d["dataset"]["desc"] for d in datasets], []

        def update_participants(headers, project, bids, api=None, log=None):
            rec["participants"] += 1

        def upload_project_files(headers, project, output_dir, files, api=None):
            rec.update(files=files, output_dir=output_dir)

        def upload_tables(headers, project, bids_dir, api=None, log=None):
            rec.update(tables_dir=bids_dir)
            return 0

        d = dict(
            Engine=engine_class(self.engine, self.start_error), prompt=self.prompt,
            open_url=lambda u: self.opened.append(u), log=self.out.append, error=self.out.append,
            load_jwt=lambda: "a.b.c", api={"warehouse": "w", "amaretti": "a", "main": "https://brainlife.io"},
            find_project=lambda h, pid, api: PROJECT if pid == PROJECT["_id"] else None,
            all_datatypes=lambda h, api: DATATYPES,
            project_subjects=lambda h, pid, api: {"existing_subjects": ["07"], "existing_sessions": {"07": ["1"]}},
            validate=lambda item, dt: self.validate_result(item),
            upload_datasets=upload_datasets, update_participants=update_participants,
            upload_project_files=upload_project_files, upload_tables=upload_tables, exit=self.exits.append)
        d.update(over)
        return Deps(**d)

    def run(self, **over):
        return run(self.opts, self.deps(**over))

    def text(self):
        return "\n".join(self.out)


# --- the happy path -----------------------------------------------------------------------------

def test_scan_approve_execute_validate_and_upload(tmp_path):
    c = Case(tmp_path, deface="quickshear", tag=["x"])
    assert c.run() == 0, c.text()
    assert c.engine.keys() == ["POST /scan", "GET /plan", "POST /approve", "POST /execute", "GET /status", "GET /plan"]
    assert c.engine.calls[0][1] == {"project_id": PROJECT["_id"], "existing_subjects": ["07"],
                                    "existing_sessions": {"07": ["1"]}, "target": "bids"}
    assert c.engine.calls[2][1] == {"deface_method": "quickshear"}
    assert (c.engine.started["folder"], c.engine.started["work"], c.engine.started["keys"]) == (c.input, c.work, c.keys)
    assert c.engine.started["name"].startswith("bl-aimport-")
    assert len(c.rec["datasets"]) == 5 and c.rec["tags"] == ["x"]
    assert c.rec["headers"] == {"Authorization": "Bearer a.b.c"}
    assert c.rec["participants"] == 1 and c.rec["output_dir"] == c.bids and "README" in c.rec["files"]
    assert c.rec["tables_dir"] == c.bids
    assert "https://brainlife.io/project/" + PROJECT["_id"] in c.out
    assert c.engine.stops == 1 and c.prompts == []


def test_the_engine_is_stopped_after_its_last_request_and_before_any_upload(tmp_path):
    c = Case(tmp_path)
    assert c.run() == 0
    assert c.rec["stops_at_upload"] == 1 and c.engine.stops == 1


def test_the_size_report_comes_before_the_upload(tmp_path):
    c = Case(tmp_path)
    c.run()
    report = next(l for l in c.out if " objects, " in l)
    assert report.startswith("5 objects, 0.00 GB from local output, 0.00 GB streamed from sources")


def test_no_upload_stops_after_the_validators(tmp_path):
    c = Case(tmp_path, upload=False)
    seen = []
    c.validate_result = lambda item: seen.append(item) or {"ok": True, "errors": [], "warnings": []}
    assert c.run() == 0
    assert len(seen) == 5
    assert c.rec["datasets"] is None and c.rec["participants"] == 0 and c.rec["files"] is None
    assert any(l.startswith("--no-upload: stopping here. 5 object(s)") for l in c.out)


# --- review -------------------------------------------------------------------------------------

def test_n_at_the_approval_exits_0_with_nothing_approved(tmp_path):
    c = Case(tmp_path, answers=["n"], yes=False)
    assert c.run() == 0
    assert c.prompts == [APPROVE_PROMPT]
    assert c.engine.keys() == ["POST /scan", "GET /plan"]
    assert c.rec["datasets"] is None and c.engine.stops == 1


def test_the_approval_screen_shows_the_chosen_deface_method(tmp_path):
    c = Case(tmp_path, answers=[""], yes=False, deface="quickshear")
    c.run()
    assert "Deface method: quickshear" in c.text() and "Deface method: pydeface" not in c.text()


def test_e_explains_patch_plan_then_shows_the_plan_again(tmp_path):
    c = Case(tmp_path, answers=["e", "", "yes"], yes=False, upload=False)
    assert c.run() == 0
    t = c.text()
    assert "PATCH /plan" in t and "README.md" in t and c.engine.base in t
    assert "tok123 (valid only while this engine runs)" in t
    assert c.engine.keys()[:4] == ["POST /scan", "GET /plan", "GET /plan", "POST /approve"]
    assert c.prompts.count(APPROVE_PROMPT) == 2


# --- failures -----------------------------------------------------------------------------------

def test_a_failed_scan_exits_1(tmp_path):
    c = Case(tmp_path)
    c.engine.stages = ["failed"]
    assert c.run() == 1
    assert c.engine.keys() == ["POST /scan"]
    assert "aimport: the scan failed: boom" in c.out and c.engine.stops == 1


def test_an_invalid_output_exits_1_and_uploads_nothing(tmp_path):
    c = Case(tmp_path, status=dict(VALIDATED, stage="invalid", message="2 validation error(s)"))
    c.engine.stages = ["planned", "invalid"]
    assert c.run() == 1
    assert "aimport: the output is invalid (2 validation error(s)); nothing was uploaded" in c.out
    assert c.rec["datasets"] is None and c.rec["files"] is None and c.engine.stops == 1


def test_an_engine_without_a_manifest_is_too_old(tmp_path):
    status = {k: v for k, v in VALIDATED.items() if k != "manifest"}
    c = Case(tmp_path, status=status)
    assert c.run() == 1
    assert "aimport: the engine image is too old (its /status has no manifest); rebuild it" in c.out
    assert c.rec["datasets"] is None and c.rec["participants"] == 0


def test_an_engine_error_prints_its_message_without_a_traceback(tmp_path):
    c = Case(tmp_path)
    c.engine.errors["POST /approve"] = EngineError("the key is locked by another run", 409)
    assert c.run() == 1
    assert "aimport: the key is locked by another run" in c.out
    assert "Traceback" not in c.text() and c.engine.stops == 1


def test_an_engine_that_does_not_start_is_reported(tmp_path):
    c = Case(tmp_path)
    c.start_error = Exception("docker could not get the engine image: docker pull x failed (code 1)")
    assert c.run() == 1
    assert c.out[-1].startswith("aimport: docker could not get the engine image")
    assert c.engine.stops == 1  # stopped by name, in case the container came up


def test_a_validator_rejection_keeps_that_object_and_its_files_out(tmp_path):
    c = Case(tmp_path)
    c.validate_result = lambda item: ({"ok": False, "errors": ["bad header"], "warnings": []}
                                      if item["dataset"]["desc"] == "sub-01_T1w.nii.gz"
                                      else {"ok": True, "errors": [], "warnings": []})
    assert c.run() == 1
    assert len(c.rec["datasets"]) == 4
    assert "sub-01/anat/sub-01_T1w.nii.gz" not in c.rec["files"]
    assert "aimport: not uploading sub-01_T1w.nii.gz: bad header" in c.out
    assert "aimport: 1 object(s) failed validation and were not uploaded" in c.out


def test_a_skipped_validator_still_uploads_with_a_warning(tmp_path):
    c = Case(tmp_path)
    c.validate_result = lambda item: {"ok": True, "skipped": "datatype has no validator", "errors": [], "warnings": ["w1"]}
    assert c.run() == 0
    assert any("was not checked by a datatype validator (datatype has no validator)" in l for l in c.out)
    assert any(l.endswith(": w1") for l in c.out)


def test_a_key_file_in_the_output_stops_everything(tmp_path):
    c = Case(tmp_path)
    write(os.path.join(c.bids, "p.aimport-key.json"), "{}")
    assert c.run() == 1
    assert c.rec["datasets"] is None and c.rec["participants"] == 0 and c.rec["files"] is None
    assert any("aimport-key" in l for l in c.out)


# --- flags and folders --------------------------------------------------------------------------

@pytest.mark.parametrize("opts,message", [
    ({"ui": True}, "--ui needs the brainlife.io/aimport page, which is not available yet"),
    ({"target": "nifti"}, "--target must be bids or datatypes"),
    ({"deface": "allineate"}, "--deface must be pydeface or quickshear"),
    ({"image": "-v /:/host"}, "--image is not a docker image reference"),
    ({"image": "img; rm -rf /"}, "--image is not a docker image reference"),
    ({"project": None}, "please give the brainlife project id"),
    ({"project": "abc"}, "--project must be a brainlife project id"),
    ({"remote": ["http://example.org/a.zarr"]}, "--remote must be an https:// or s3:// URL"),
    ({"folder": None}, "please give the folder to import"),
])
def test_bad_flags_exit_2_before_docker(tmp_path, opts, message):
    c = Case(tmp_path, **opts)
    assert c.run() == 2
    assert any(l.startswith(message) for l in c.out), c.text()
    assert c.engine.started is None


def test_a_folder_that_does_not_exist_exits_2(tmp_path):
    c = Case(tmp_path)
    c.opts["folder"] = os.path.join(c.input, "nope")
    assert c.run() == 2 and c.engine.started is None


@pytest.mark.parametrize("which", ["work", "keys"])
def test_folder_paths_with_docker_mount_syntax_exit_2(tmp_path, which):
    c = Case(tmp_path)
    c.opts[which] = c.opts[which] + (":x" if which == "work" else ",ro")
    assert c.run() == 2 and c.engine.started is None


def test_overlapping_folders_exit_2_before_docker(tmp_path):
    c = Case(tmp_path)
    c.opts["work"] = os.path.join(c.input, "work")
    assert c.run() == 2 and c.engine.started is None
    c2 = Case(tmp_path / "b")
    c2.opts["keys"] = os.path.join(c2.work, "keys")
    assert c2.run() == 2 and c2.engine.started is None


def test_an_image_digest_is_accepted(tmp_path):
    c = Case(tmp_path, image="ghcr.io/brainlife/aimport:1.0@sha256:abc")
    c.engine.stages = ["failed"]
    c.run()
    assert c.engine.started["image"] == "ghcr.io/brainlife/aimport:1.0@sha256:abc"


def test_a_missing_project_exits_1_before_docker(tmp_path):
    c = Case(tmp_path, project="ffffffffffffffffffffffff")
    assert c.run() == 1
    assert "aimport: project ffffffffffffffffffffffff not found" in c.out and c.engine.started is None


def test_not_logged_in_exits_1_before_docker(tmp_path):
    c = Case(tmp_path)

    def nope():
        raise Exception("not logged in; run: bl login")
    assert c.run(load_jwt=nope) == 1
    assert "aimport: not logged in; run: bl login" in c.out and c.engine.started is None


def test_new_work_and_keys_folders_are_private(tmp_path):
    c = Case(tmp_path)
    import shutil
    shutil.rmtree(c.work)
    c.engine.stages = ["failed"]
    c.run()
    assert stat.S_IMODE(os.stat(c.work).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(c.keys).st_mode) == 0o700


def test_an_existing_keys_folder_others_can_read_is_refused(tmp_path):
    c = Case(tmp_path)
    os.makedirs(c.keys)
    os.chmod(c.keys, 0o755)
    assert c.run() == 2
    assert any("chmod 700 " + c.keys in l for l in c.out)
    assert c.engine.started is None and stat.S_IMODE(os.stat(c.keys).st_mode) == 0o755


def test_existing_work_and_private_keys_folders_keep_their_mode(tmp_path):
    c = Case(tmp_path)
    os.chmod(c.work, 0o755)
    os.makedirs(c.keys)
    os.chmod(c.keys, 0o700)
    c.engine.stages = ["failed"]
    c.run()
    assert c.engine.started is not None
    assert stat.S_IMODE(os.stat(c.work).st_mode) == 0o755


# --- --qa ---------------------------------------------------------------------------------------

def test_qa_y_opens_a_tokenless_viewer_link_and_uploads(tmp_path):
    c = Case(tmp_path, answers=["y"], qa=True)
    c.engine.hooks["POST /viewer/session"] = lambda body: (c.engine.stops == 0 or pytest.fail("engine stopped")) and VIEWER
    assert c.run() == 0, c.text()
    keys = c.engine.keys()
    assert keys.index("POST /viewer/session") > keys.index("POST /execute")
    url = "http://127.0.0.1:9999/viewer/open?code=abc"
    assert "QA viewer: " + url in c.out and c.opened == [url]
    assert "tok123" not in c.text()
    assert c.prompts == [QA_PROMPT] and len(c.rec["datasets"]) == 5 and c.engine.stops == 1


@pytest.mark.parametrize("answer", ["n", "", "no"])
def test_qa_anything_but_y_uploads_nothing(tmp_path, answer):
    c = Case(tmp_path, answers=[answer], qa=True)
    assert c.run() == 0
    assert c.rec["datasets"] is None and c.rec["participants"] == 0 and c.engine.stops == 1
    assert any(l.startswith("Not uploaded. The output stays in ") for l in c.out)


def test_qa_question_is_asked_even_with_yes(tmp_path):
    c = Case(tmp_path, answers=["n"], qa=True, yes=True)
    c.run()
    assert c.prompts == [QA_PROMPT] and c.rec["datasets"] is None


def test_qa_v_gives_a_fresh_one_time_link_each_time(tmp_path):
    c = Case(tmp_path, answers=["v", "V", "y"], qa=True)
    n = []

    def session(body):
        n.append(1)
        return {"code": "c%d" % len(n), "url": "/viewer/open?code=c%d" % len(n)}
    c.engine.hooks["POST /viewer/session"] = session
    assert c.run() == 0
    assert c.opened == ["http://127.0.0.1:9999/viewer/open?code=c%d" % i for i in (1, 2, 3)]
    assert c.prompts == [QA_PROMPT] * 3 and c.rec["datasets"]


def test_qa_a_failing_opener_only_prints(tmp_path):
    c = Case(tmp_path, answers=["y"], qa=True)

    def broken(url):
        raise OSError("no opener")
    assert c.run(open_url=broken) == 0
    assert any("could not open a browser" in l for l in c.out) and c.rec["datasets"]


def test_qa_with_no_upload_keeps_the_viewer_up_until_enter(tmp_path):
    c = Case(tmp_path, answers=[""], qa=True, upload=False)
    assert c.run() == 0
    assert c.prompts == [ENTER_PROMPT] and c.rec["datasets"] is None and c.engine.stops == 1


def test_qa_on_an_engine_without_a_viewer_is_refused(tmp_path):
    c = Case(tmp_path, answers=["y"], qa=True)
    c.engine.errors["POST /viewer/session"] = EngineError("Not Found", 404)
    assert c.run() == 1
    assert "aimport: the engine image is too old for --qa; rebuild it" in c.out
    assert c.prompts == [] and c.rec["datasets"] is None and c.engine.stops == 1


def test_qa_another_viewer_error_is_not_called_too_old(tmp_path):
    c = Case(tmp_path, qa=True)
    c.engine.errors["POST /viewer/session"] = EngineError("boom", 500)
    assert c.run() == 1
    assert "aimport: boom" in c.out and "too old" not in c.text()


def test_qa_an_invalid_output_still_opens_the_viewer_then_exits_1(tmp_path):
    c = Case(tmp_path, answers=[""], qa=True, status=dict(VALIDATED, stage="invalid", message="errors"))
    c.engine.stages = ["planned", "invalid"]
    assert c.run() == 1
    assert c.opened == ["http://127.0.0.1:9999/viewer/open?code=abc"] and c.prompts == [ENTER_PROMPT]
    assert c.rec["datasets"] is None and c.engine.stops == 1


def test_qa_a_failed_run_opens_no_viewer(tmp_path):
    c = Case(tmp_path, qa=True, status=dict(VALIDATED, stage="failed"))
    c.engine.stages = ["planned", "failed"]
    assert c.run() == 1
    assert "POST /viewer/session" not in c.engine.keys() and c.prompts == []


def test_qa_channel_marks_that_made_the_output_invalid_stop_the_upload(tmp_path):
    c = Case(tmp_path, answers=["y"], qa=True)
    c.engine.statuses = [dict(VALIDATED, stage="invalid", message="after marks")]
    assert c.run() == 1
    assert "aimport: after the QA review the output is invalid (after marks); nothing was uploaded" in c.out
    assert c.rec["datasets"] is None and c.engine.stops == 1


def test_qa_a_channel_save_still_running_is_waited_for(tmp_path):
    c = Case(tmp_path, answers=["y"], qa=True)
    c.engine.statuses = [dict(VALIDATED, stage="executing"), VALIDATED]
    c.engine.stages = ["planned", "validated", "validated"]
    assert c.run() == 0, c.text()
    assert c.engine.keys().count("GET /status") == 3 and c.engine.stages == []
    assert c.rec["datasets"]


def test_without_qa_there_is_no_viewer(tmp_path):
    c = Case(tmp_path)
    c.run()
    assert "POST /viewer/session" not in c.engine.keys() and c.opened == []


# --- signals ------------------------------------------------------------------------------------

def test_ctrl_c_stops_the_engine_and_exits_130(tmp_path):
    before = signal.getsignal(signal.SIGINT)
    c = Case(tmp_path, yes=False)

    def prompt(q):
        signal.raise_signal(signal.SIGINT)
        return "n"
    c.run(prompt=prompt)
    assert c.exits == [130] and c.engine.stops == 1
    assert "aimport: interrupted; stopping the engine" in c.out
    assert signal.getsignal(signal.SIGINT) is before


@pytest.mark.parametrize("sig,code", [("SIGTERM", 143), ("SIGHUP", 129)])
def test_a_signal_mid_request_stops_the_engine_and_hides_the_in_flight_error(tmp_path, sig, code):
    before = {s: signal.getsignal(getattr(signal, s)) for s in ("SIGINT", "SIGTERM", "SIGHUP")}
    c = Case(tmp_path)

    def execute(body):
        signal.raise_signal(getattr(signal, sig))
        raise ConnectionError("connection reset")
    c.engine.hooks["POST /execute"] = execute
    assert c.run() == 1
    assert c.exits == [code] and c.engine.stops == 1
    assert "connection reset" not in c.text()
    assert {s: signal.getsignal(getattr(signal, s)) for s in before} == before


def test_the_default_exit_raises_system_exit_with_the_code(tmp_path):
    c = Case(tmp_path, yes=False)

    def prompt(q):
        signal.raise_signal(signal.SIGTERM)
        return "n"
    import sys
    with pytest.raises(SystemExit) as info:
        c.run(prompt=prompt, exit=sys.exit)
    assert info.value.code == 143 and c.engine.stops == 1


# --- reference datasets -------------------------------------------------------------------------

ZARR = "sub-01/micr/sub-01_sample-01_OCT.ome.zarr"
MICR_PLAN = {"dataset_name": "x", "deface_method": "pydeface", "warnings": [], "ancillary": [], "entries": [
    {"id": "m1", "modality": "micr", "subject": "01", "session": None, "datatype": "micr", "suffix": "OCT",
     "entities": {"sample": "01"}, "deface": False, "status": "ok", "source": "heuristic", "confidence": 1,
     "brainlife_datatype": "neuro/ome-zarr", "brainlife_tags": ["OCT"]}]}
MICR_STATUS = {"stage": "validated", "message": None, "manifest": {"m1": [ZARR]}, "chunk_map": "output/bids.chunks.json",
               "validation": {"error_count": 0, "warning_count": 0, "errors": [], "warnings": []}}


def micr_case(tmp_path, source=None, **opts):
    c = Case(tmp_path, plan=MICR_PLAN, status=MICR_STATUS, **opts)
    import shutil
    shutil.rmtree(c.bids)
    write(os.path.join(c.bids, "dataset_description.json"), "{}")
    write(os.path.join(c.bids, ZARR, "zarr.json"), "{}")
    write(os.path.join(c.bids, ZARR, "0", "zarr.json"), "{}")
    write(os.path.join(c.bids, "sub-01", "micr", "sub-01_sample-01_OCT.json"), "{}")
    for key in ("c/0/0", "c/0/1", "c/1/0"):
        write(os.path.join(c.input, "store.zarr", "0", *key.split("/")), "chunk " + key)
    meta = {"source": source or {"input": "store.zarr/0"}, "zarr_format": 3, "shape": [4, 4], "chunk_grid": [2, 2],
            "separator": "/", "codec_bytes_hint": 16}
    write(os.path.join(c.work, "output", "bids.chunks.json"), json.dumps({"version": 1, "arrays": {ZARR + "/0": meta}}))
    return c


def test_remote_sources_go_to_the_scan_and_are_never_printed(tmp_path):
    url = "https://bucket.s3.amazonaws.com/donor-4711/a.zarr"
    c = micr_case(tmp_path, remote=[url, "s3://bucket/b.zarr"])
    assert c.run() == 0, c.text()
    assert c.engine.calls[0][1]["remote"] == [url, "s3://bucket/b.zarr"]
    assert "donor-4711" not in c.text()


def test_a_micr_object_is_uploaded_with_its_chunk_map(tmp_path):
    c = micr_case(tmp_path)
    assert c.run() == 0, c.text()
    assert [(d["dataset"]["datatype"], d["dataset"]["datatype_tags"]) for d in c.rec["datasets"]] == [("neuro/ome-zarr", ["OCT"])]
    assert list(c.rec["chunk_map"]["arrays"]) == [ZARR + "/0"]
    assert c.rec["files"] == ["dataset_description.json", "sub-01/micr/sub-01_sample-01_OCT.json"]
    assert "1 objects, 0.00 GB from local output, 0.00 GB streamed from sources" in c.out
    assert c.input not in c.text()


def test_remote_chunk_sizes_are_reported_as_an_upper_bound(tmp_path):
    c = micr_case(tmp_path, source={"url": "https://bucket.s3.amazonaws.com/a.zarr/0"}, upload=False)
    assert c.run() == 0, c.text()
    assert any(l.endswith("(at most: remote chunk sizes are known only when they are read)") for l in c.out)


def test_streaming_asks_before_the_upload_without_yes(tmp_path):
    c = micr_case(tmp_path, answers=["y", "n"], yes=False)
    assert c.run() == 0
    assert c.prompts == [APPROVE_PROMPT, "Upload? [y/N] "] and c.rec["datasets"] is None


def test_a_qa_yes_counts_as_the_streaming_question(tmp_path):
    c = micr_case(tmp_path, answers=["y", "y"], yes=False, qa=True)
    assert c.run() == 0, c.text()
    assert c.prompts == [APPROVE_PROMPT, QA_PROMPT] and c.rec["datasets"]


def test_a_chunk_map_escaping_the_input_stops_before_any_upload(tmp_path):
    c = micr_case(tmp_path, source={"input": "../work"})
    assert c.run() == 1
    assert any("leaves the input folder" in l for l in c.out) and c.rec["datasets"] is None


def test_a_run_without_a_chunk_map_sends_no_remote_and_asks_nothing_more(tmp_path):
    c = Case(tmp_path, answers=["y"], yes=False)
    assert c.run() == 0
    assert "remote" not in c.engine.calls[0][1]
    assert c.rec["chunk_map"] is None and c.prompts == [APPROVE_PROMPT]


# --- brainlife.io lookups -----------------------------------------------------------------------

def test_project_subjects_pages_through_the_project(tmp_path):
    rows = [{"meta": {"subject": "01", "session": "1"}}, {"meta": {"subject": "01", "session": "2"}},
            {"meta": {"subject": "01", "session": "1"}}, {"meta": {"subject": 2}}, {"meta": {}}]

    def handler(req):
        q = req["query"]
        skip, limit = int(q["skip"]), int(q["limit"])
        return 200, {}, {"datasets": rows[skip:skip + limit], "count": len(rows)}
    with Stub(handler) as s:
        r = bl.project_subjects({"Authorization": "Bearer a.b.c"}, "p1", {"warehouse": s.base + "/w"}, limit=2)
    assert r == {"existing_subjects": ["01", "2"], "existing_sessions": {"01": ["1", "2"]}}
    q = [c["query"] for c in s.calls]
    assert [x["skip"] for x in q] == ["0", "2", "4"]
    assert json.loads(q[0]["find"]) == {"project": "p1", "removed": False}
    assert q[0]["select"] == "meta.subject meta.session project" and q[0]["sort"] == "_id"
    assert s.calls[0]["path"] == "/w/dataset" and s.calls[0]["headers"]["authorization"] == "Bearer a.b.c"


def test_project_lookup_finds_only_an_existing_project():
    def handler(req):
        find = json.loads(req["query"]["find"])
        return 200, {}, {"projects": [PROJECT] if find["_id"] == PROJECT["_id"] and find["removed"] is False else []}
    with Stub(handler) as s:
        api = {"warehouse": s.base}
        assert bl.project_by_id({}, PROJECT["_id"], api) == PROJECT
        assert bl.project_by_id({}, "f" * 24, api) is None
