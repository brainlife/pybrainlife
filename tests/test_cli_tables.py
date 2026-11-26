"""Project tables (brainlife.cli.tables): which BIDS files are tables, sidecar inheritance,
merging per-subject sessions/scans files, and the /table API calls (local stub, no network)."""

import json
import os

from brainlife.cli import tables
from tests.aimport_support import PROJECT, Stub


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def bids_tables(tmp_path):
    root = str(tmp_path / "bids")
    write(root, "participants.tsv", "participant_id\tage\nsub-01\t30\n")
    write(root, "phenotype/bdi.tsv", "participant_id\tscore\nsub-01\t12\n")
    write(root, "phenotype/bdi.json", json.dumps({"score": {"Description": "BDI total"}, "MeasurementToolMetadata": {}}))
    write(root, "sessions.json", json.dumps({"weight": {"Units": "kg"}}))
    write(root, "sub-01/sub-01_sessions.tsv", "session_id\tweight\nses-pre\t70\n")
    write(root, "sub-02/sub-02_sessions.tsv", "session_id\tweight\theight\nses-pre\t60\t170\n")
    write(root, "sub-01/ses-pre/sub-01_ses-pre_scans.tsv", "filename\tacq_time\nanat/sub-01_ses-pre_T1w.nii.gz\t10:00\n")
    write(root, "sub-01/ses-pre/func/sub-01_ses-pre_task-rest_events.tsv", "onset\n0\n")
    return root


def test_classify_matches_the_warehouse():
    assert tables.classify("phenotype/bdi.tsv") == {"kind": "phenotype", "name": "phenotype/bdi"}
    assert tables.classify("sub-01/ses-pre/sub-01_ses-pre_scans.tsv") == {
        "kind": "scans", "name": "scans", "subject": "01", "session": "pre"}
    assert tables.classify("sub-01/func/sub-01_task-rest_events.tsv") is None
    assert tables.classify("sub-01/sub-02_sessions.tsv") is None


def test_sidecar_candidates_follow_bids_inheritance():
    assert tables.sidecar_candidates("sub-01/sub-01_sessions.tsv") == [
        "sessions.json", "sub-01_sessions.json", "sub-01/sessions.json", "sub-01/sub-01_sessions.json"]
    assert tables.sidecar_candidates("phenotype/bdi.tsv") == ["phenotype/bdi.json"]


def test_collect_tables_merges_per_subject_files_and_adds_id_columns(tmp_path):
    root = bids_tables(tmp_path)
    found, warnings = tables.collect_tables(root)
    assert warnings == []
    by_name = {t["name"]: t for t in found}
    assert sorted(by_name) == ["phenotype/bdi", "scans", "sessions"]  # participants has its own API

    assert json.loads(by_name["phenotype/bdi"]["json"]) == {"score": {"Description": "BDI total"}}
    assert by_name["sessions"]["tsv"] == (
        "participant_id\tsession_id\tweight\theight\n"
        "sub-01\tses-pre\t70\t\n"
        "sub-02\tses-pre\t60\t170\n")
    assert json.loads(by_name["sessions"]["json"]) == {"weight": {"Units": "kg"}}
    assert by_name["scans"]["tsv"] == (
        "participant_id\tsession_id\tfilename\tacq_time\n"
        "sub-01\tses-pre\tanat/sub-01_ses-pre_T1w.nii.gz\t10:00\n")
    assert by_name["scans"]["json"] is None


def test_unreadable_tables_and_bad_sidecars_are_reported(tmp_path):
    root = bids_tables(tmp_path)
    os.symlink(str(tmp_path / "annex" / "missing"), os.path.join(root, "phenotype", "stai.tsv"))
    write(root, "samples.tsv", "sample_id\tparticipant_id\ns1\tsub-01\n")
    write(root, "samples.json", "{bad")
    found, warnings = tables.collect_tables(root)
    assert "samples" in [t["name"] for t in found]
    assert sorted(warnings) == ["phenotype/stai.tsv: can not be read (No such file or directory)",
                                "samples.json: sidecar json could not be parsed"]


def _serve(handler):
    stub = Stub(handler)
    return stub, {"warehouse": stub.base + "/warehouse"}


def test_upload_tables_sends_each_table(tmp_path):
    root = bids_tables(tmp_path)
    stub, api = _serve(lambda req: (200, {}, {"table": {"_id": "x"}}) if req["method"] == "PUT" else None)
    with stub:
        logs = []
        sent = tables.upload_tables({"Authorization": "Bearer t"}, PROJECT, root, api, log=logs.append)
    assert sent == 3 and logs == []
    puts = [c for c in stub.calls if c["method"] == "PUT"]
    assert {c["path"] for c in puts} == {"/warehouse/table/" + PROJECT["_id"]}
    assert sorted(c["json"]["name"] for c in puts) == ["phenotype/bdi", "scans", "sessions"]
    assert all(c["headers"]["authorization"] == "Bearer t" for c in puts)
    assert all(c["json"]["kind"] in ("phenotype", "sessions", "scans") for c in puts)
    assert "json" not in next(c["json"] for c in puts if c["json"]["name"] == "scans")


def test_a_server_without_the_table_api_is_reported_once(tmp_path):
    root = bids_tables(tmp_path)
    stub, api = _serve(lambda req: (404, {"Content-Type": "text/html"}, "<pre>Cannot PUT /table/x</pre>"))
    with stub:
        logs = []
        sent = tables.upload_tables({}, PROJECT, root, api, log=logs.append)
    assert sent == 0
    assert logs == ["! this brainlife.io has no table API yet; the tables stay project files only"]
    assert len(stub.calls) == 1


def test_a_failing_table_does_not_stop_the_others(tmp_path):
    root = bids_tables(tmp_path)

    def handler(req):
        if req["json"]["name"] == "sessions":
            return 400, {}, {"message": "bad table"}
        return 200, {}, {"table": {}}

    stub, api = _serve(handler)
    with stub:
        logs = []
        sent = tables.upload_tables({}, PROJECT, root, api, log=logs.append)
    assert sent == 2
    assert logs == ["! table sessions was not uploaded: uploading table sessions failed (HTTP 400): bad table"]


def test_too_large_tables_stay_project_files(tmp_path, monkeypatch):
    root = bids_tables(tmp_path)
    monkeypatch.setattr(tables, "MAX_BODY", 10)
    stub, api = _serve(lambda req: (200, {}, {}))
    with stub:
        logs = []
        assert tables.upload_tables({}, PROJECT, root, api, log=logs.append) == 0
    assert len(logs) == 3 and all("too large" in line for line in logs)
    assert stub.calls == []


def test_get_table_pages_and_writes_tsv():
    rows = [{"subject_key": str(i), "values": {"participant_id": "sub-%d" % i, "score": str(i)}} for i in range(5)]

    def handler(req):
        skip, limit = int(req["query"]["skip"]), int(req["query"]["limit"])
        return 200, {}, {"table": {"_id": "t1", "name": "phenotype/bdi", "column_order": ["participant_id", "score"]},
                         "rows": rows[skip:skip + limit]}

    stub, api = _serve(handler)
    with stub:
        table, got = tables.get_table({}, PROJECT["_id"], "t1", api["warehouse"], page=2)
    assert len(got) == 5 and len(stub.calls) == 3
    assert tables.rows_to_tsv(table, got).splitlines()[:2] == ["participant_id\tscore", "sub-0\t0"]


def test_list_and_remove():
    def handler(req):
        if req["method"] == "GET":
            return 200, {}, [{"_id": "participants", "name": "participants"}]
        if req["method"] == "DELETE" and req["path"].endswith("/t1"):
            return 200, {}, {"status": "removed"}
        return None

    stub, api = _serve(handler)
    with stub:
        assert tables.list_tables({}, PROJECT["_id"], api["warehouse"])[0]["name"] == "participants"
        assert tables.remove_table({}, PROJECT["_id"], "t1", api["warehouse"]) == {"status": "removed"}
