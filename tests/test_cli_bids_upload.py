"""bl bids upload (the ezBIDS "Send to brainlife" import): real BIDS walker, fake brainlife calls."""

import argparse

from brainlife.cli import bids
from tests.aimport_support import PROJECT, make_bids, write


def case(tmp_path, **over):
    root = make_bids(str(tmp_path / "bids"))
    write(root + "/phenotype/bdi.tsv", "participant_id\tscore\nsub-01\t12\n")
    rec = {"participants": 0, "logs": [], "errors": []}

    def update_participants(headers, project, b, api=None, log=None):
        rec["participants"] += 1
        rec["participant_rows"] = b["participants"]

    def upload_datasets(headers, project, datasets, tags=(), api=None, log=None):
        rec.update(datasets=datasets, tags=tags, headers=headers)
        return [d["dataset"]["desc"] for d in datasets[1:]], [datasets[0]["dataset"]["desc"]]

    def upload_tables(headers, project, root_dir, api=None, log=None):
        rec["tables_dir"] = root_dir
        return 1

    d = dict(load_jwt=lambda: "a.b.c", api={"warehouse": "w", "main": "https://brainlife.io"},
             find_project=lambda h, pid, api: PROJECT if pid == PROJECT["_id"] else None,
             update_participants=update_participants, upload_datasets=upload_datasets, upload_tables=upload_tables,
             log=rec["logs"].append, error=rec["errors"].append)
    d.update(over)
    return root, rec, bids.Deps(**d)


def ns(**kw):
    base = dict(subcommand="upload", project=PROJECT["_id"], directory=None, folder=None, tag=[])
    base.update(kw)
    return argparse.Namespace(**base)


def test_uploads_objects_participants_and_tables(tmp_path):
    root, rec, deps = case(tmp_path)
    assert bids.run(ns(folder=root, tag=["ezbids"]), deps) == 0, rec["errors"]
    assert rec["headers"] == {"Authorization": "Bearer a.b.c"}
    assert rec["participants"] == 1 and rec["participant_rows"]
    assert len(rec["datasets"]) == 5 and rec["tags"] == ["ezbids"]
    assert all(item["dataset"]["datatype"].startswith("neuro/") for item in rec["datasets"])
    assert rec["tables_dir"] == root
    assert rec["logs"][-2] == "Uploaded 4 object(s), skipped 1 already in the project, 1 table(s)"
    assert rec["logs"][-1] == "https://brainlife.io/project/" + PROJECT["_id"]


def test_directory_flag_works_like_the_folder_argument(tmp_path):
    root, rec, deps = case(tmp_path)
    assert bids.run(ns(directory=root), deps) == 0


def test_not_a_bids_folder_exits_2(tmp_path):
    _, rec, deps = case(tmp_path)
    assert bids.run(ns(folder=str(tmp_path)), deps) == 2
    assert "no dataset_description.json" in rec["errors"][0]


def test_unknown_project_exits_1(tmp_path):
    root, rec, deps = case(tmp_path)
    assert bids.run(ns(folder=root, project="0" * 24), deps) == 1
    assert rec["errors"] == ["bids upload: project %s not found" % ("0" * 24)]


def test_a_failure_is_reported_without_a_traceback(tmp_path):
    def broken(*a, **k):
        raise RuntimeError("warehouse is down")

    root, rec, deps = case(tmp_path)
    deps.upload_datasets = broken
    assert bids.run(ns(folder=root), deps) == 1
    assert rec["errors"] == ["bids upload: warehouse is down"]
