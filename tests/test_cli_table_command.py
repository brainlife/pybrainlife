"""bl table: subcommands against a local stub (no network)."""

import argparse
import json

import pytest

from brainlife.cli import table as table_cmd
from brainlife.api import api as bl_api
from tests.aimport_support import PROJECT, Stub
from tests.test_cli_tables import bids_tables


@pytest.fixture
def server(monkeypatch):
    stored = {}

    def handler(req):
        base = "/warehouse/table/" + PROJECT["_id"]
        if req["method"] == "GET" and req["path"] == base:
            return 200, {}, [{"_id": "participants", "kind": "participants", "name": "participants", "row_count": 1}]
        if req["method"] == "GET" and req["path"] == base + "/participants":
            return 200, {}, {"table": {"column_order": ["participant_id", "age"]},
                             "rows": [{"values": {"participant_id": "sub-01", "age": "30"}}]}
        if req["method"] == "PUT" and req["path"] == base:
            stored[req["json"]["name"]] = req["json"]
            return 200, {}, {"table": {"_id": "new-id"}}
        if req["method"] == "DELETE" and req["path"] == base + "/t1":
            return 200, {}, {"status": "removed"}
        return None

    stub = Stub(handler)
    monkeypatch.setitem(bl_api.services, "warehouse", stub.base + "/warehouse")
    monkeypatch.setattr(bl_api, "auth", "tok")
    monkeypatch.setattr(table_cmd, "ensure_auth", lambda: None)
    yield stub, stored
    stub.close()


def run(**kw):
    return table_cmd.run(argparse.Namespace(**kw))


def test_list_get_upload_import_remove(server, tmp_path, capsys):
    stub, stored = server
    assert run(subcommand="list", project=PROJECT["_id"], json=False) == 0
    assert capsys.readouterr().out == "participants\tparticipants\tparticipants\t1 rows\n"

    out = tmp_path / "participants.tsv"
    assert run(subcommand="get", project=PROJECT["_id"], table="participants", output=str(out), json=False) == 0
    assert out.read_text() == "participant_id\tage\nsub-01\t30\n"

    tsv = tmp_path / "site.tsv"
    tsv.write_text("participant_id\tsite\nsub-01\tA\n")
    side = tmp_path / "site.json"
    side.write_text(json.dumps({"site": {"Description": "scan site"}}))
    assert run(subcommand="upload", project=PROJECT["_id"], name="site-info", kind="acquisition",
               json_sidecar=str(side), tsv=str(tsv)) == 0
    assert capsys.readouterr().out == "new-id\n"
    assert stored["site-info"] == {"name": "site-info", "kind": "acquisition", "tsv": tsv.read_text(),
                                   "json": side.read_text()}

    assert run(subcommand="import", project=PROJECT["_id"], directory=bids_tables(tmp_path)) == 0
    assert capsys.readouterr().out == "3 table(s) uploaded\n"
    assert sorted(stored) == ["phenotype/bdi", "scans", "sessions", "site-info"]

    assert run(subcommand="remove", project=PROJECT["_id"], table="t1") == 0
    assert all(c["headers"]["authorization"] == "Bearer tok" for c in stub.calls)


def test_errors_exit_1(server, tmp_path):
    assert run(subcommand="get", project=PROJECT["_id"], table="missing", output=None, json=False) == 1
    assert run(subcommand="upload", project=PROJECT["_id"], name="x", kind=None, json_sidecar=None,
               tsv=str(tmp_path / "nope.tsv")) == 1
