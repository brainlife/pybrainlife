"""bl aimport: the upload to brainlife.io (a local stand-in for amaretti and warehouse)."""

import io
import os
import tracemalloc

import pytest

from brainlife.cli.aimport import brainlife_api as bl
from brainlife.cli.aimport.bids_walker import walk
from brainlife.cli.aimport.chunks import Chunk
from brainlife.cli.aimport.upload import (item_key, stream_archive, update_participants, upload_datasets,
                                          upload_project_files, write_archive)

from .aimport_support import DATATYPES, PROJECT, Stub, make_bids, tar_members, write

HEADERS = {"Authorization": "Bearer a.b.c"}
ZARR = "sub-01/micr/sub-01_sample-01_OCT.ome.zarr"
ARRAY = ZARR + "/0"


def brainlife(count=0, upload_status=200, keep=True):
    """amaretti + warehouse + an S3 presigned endpoint on one local server."""
    rec = {"upload": b"", "upload_size": 0, "registered": [], "puts": {}}

    def handler(req):
        r = req["method"] + " " + req["path"]
        if r == "GET /amaretti/instance":
            return 200, {}, {"instances": [{"_id": "i1", "name": "upload.7"}]}
        if r == "GET /warehouse/datatype":
            return 200, {}, {"datatypes": DATATYPES}
        if r == "GET /warehouse/dataset":
            return 200, {}, {"count": count}
        if r == "POST /amaretti/task":
            return 200, {}, {"task": {"_id": "t1", "name": "upload.7"}}
        if r == "GET /amaretti/task":
            return 200, {}, {"tasks": [{"_id": "t1", "status": "finished"}]}
        if r == "POST /amaretti/task/upload/t1":
            if keep:
                rec["upload"] = req["body"]
            rec["upload_size"] = req["size"]
            return upload_status, {}, {}
        if r == "POST /warehouse/dataset":
            rec["registered"].append(req["json"])
            return 200, {}, {"_id": "d1"}
        if r == "PUT /warehouse/participant/" + PROJECT["_id"]:
            return 200, {}, {}
        if r == "POST /warehouse/files/%s/upload/presigned" % PROJECT["_id"]:
            body = req["json"]
            return 200, {}, {"presignedUrl": stub.base + "/s3/" + body["prefix"] + body["fileName"]}
        if req["method"] == "PUT" and req["path"].startswith("/s3/"):
            rec["puts"][req["path"]] = (req["body"], req["headers"])
            return (403, {}, "") if req["path"].endswith("/README") else (200, {}, "")
        return None

    stub = Stub(handler, keep_bodies=keep)
    api = {"warehouse": stub.base + "/warehouse", "amaretti": stub.base + "/amaretti", "main": "https://brainlife.io"}
    return stub, api, rec


@pytest.fixture
def bids(tmp_path):
    return make_bids(str(tmp_path / "bids"))


def t1_item(bids):
    return next(d for d in walk(bids)["datasets"] if d["dataset"]["desc"] == "sub-01_T1w.nii.gz")


def test_a_new_object_is_uploaded_as_tar_gz_and_registered_with_the_tags(bids):
    stub, api, rec = brainlife()
    lines = []
    with stub:
        up, skipped = upload_datasets(HEADERS, PROJECT, [t1_item(bids)], tags=["aimport"], api=api, log=lines.append)
    assert (up, skipped) == (["sub-01_T1w.nii.gz"], [])
    task = next(c for c in stub.calls if c["method"] == "POST" and c["path"] == "/amaretti/task")
    assert task["json"]["service"] == "brainlife/app-noop"
    assert task["json"]["config"]["_outputs"][0]["datatype"] == "dt-t1w"
    assert task["headers"]["authorization"] == "Bearer a.b.c"
    upload = next(c for c in stub.calls if c["path"] == "/amaretti/task/upload/t1")
    assert upload["query"] == {"p": "upload.tar.gz", "untar": "true"}
    assert tar_members(rec["upload"]) == {"t1.nii.gz": b"t1"}
    assert rec["registered"] == [{"project": PROJECT["_id"], "task_id": "t1", "output_id": "output",
                                  "meta": {"EchoTime": 0.003, "subject": "01"}, "desc": "sub-01_T1w.nii.gz",
                                  "tags": ["aimport"]}]


def test_an_object_already_in_the_project_is_skipped(bids):
    stub, api, rec = brainlife(count=1)
    with stub:
        assert upload_datasets(HEADERS, PROJECT, [t1_item(bids)], api=api, log=lambda m: None) == ([], ["sub-01_T1w.nii.gz"])
    assert not any(c["method"] == "POST" for c in stub.calls)


def test_the_lookup_key_uses_subject_session_and_entities():
    key = item_key("p", "dt", {"desc": "d", "meta": {"subject": "01", "session": "2", "run": "1", "task": "rest",
                                                      "EchoTime": 1}})
    assert key == {"project": "p", "removed": False, "datatype": "dt", "desc": "d", "meta.subject": "01",
                   "meta.session": "2", "meta.task": "rest", "meta.run": "1"}


def test_a_failed_upload_raises_and_registers_nothing(bids):
    stub, api, rec = brainlife(upload_status=500)
    with stub, pytest.raises(bl.ApiError, match="status 500"):
        upload_datasets(HEADERS, PROJECT, [t1_item(bids)], api=api, log=lambda m: None)
    assert rec["registered"] == []


def test_a_folder_object_goes_up_with_every_file_and_no_local_user_name(tmp_path):
    root = str(tmp_path)
    write(os.path.join(root, "store", "zarr.json"), "{}")
    write(os.path.join(root, "store", "0", "zarr.json"), "[]")
    out = io.BytesIO()
    write_archive({"files": {"data.ome.zarr": os.path.join(root, "store")}}, out, log=lambda m: None)
    assert tar_members(out.getvalue()) == {"data.ome.zarr/0/zarr.json": b"[]", "data.ome.zarr/zarr.json": b"{}"}
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(out.getvalue())) as tar:
        assert all(m.uname == "" and m.uid == 0 for m in tar)


# --- reference datasets: chunks streamed from the chunk map -------------------------------------

def micr(tmp_path, chunk_bytes=None):
    root = os.path.realpath(str(tmp_path))
    bids = os.path.join(root, "bids")
    inp = os.path.join(root, "input")
    write(os.path.join(bids, ZARR, "zarr.json"), "{}")
    write(os.path.join(bids, ARRAY, "zarr.json"), "{}")
    if chunk_bytes is None:
        for key in ("c/0/0", "c/0/1", "c/1/0"):
            write(os.path.join(inp, "store.zarr", "0", *key.split("/")), "chunk " + key)
        meta = {"shape": [4, 4], "chunk_grid": [2, 2]}
    else:
        write(os.path.join(inp, "store.zarr", "0", "c", "0", "0"), chunk_bytes)
        meta = {"shape": [8, 8], "chunk_grid": [8, 8]}
    meta.update({"source": {"input": "store.zarr/0"}, "zarr_format": 3, "separator": "/"})
    item = {"dataset": {"datatype": "neuro/ome-zarr", "desc": "sub-01_sample-01_OCT.ome.zarr", "datatype_tags": ["OCT"],
                        "tags": [], "meta": {"subject": "01", "sample": "01"}},
            "files": {"data.ome.zarr": os.path.join(bids, ZARR)}}
    return item, {"bids_dir": bids, "input_dir": inp, "arrays": {ARRAY: meta}}


def test_chunks_are_streamed_into_the_object_and_a_missing_one_is_skipped(tmp_path):
    item, cmap = micr(tmp_path)
    stub, api, rec = brainlife()
    lines = []
    with stub:
        assert upload_datasets(HEADERS, PROJECT, [item], api=api, log=lines.append, chunk_map=cmap)[0] == [item["dataset"]["desc"]]
    members = tar_members(rec["upload"])
    assert sorted(members) == ["data.ome.zarr/0/c/0/0", "data.ome.zarr/0/c/0/1", "data.ome.zarr/0/c/1/0",
                               "data.ome.zarr/0/zarr.json", "data.ome.zarr/zarr.json"]
    assert members["data.ome.zarr/0/c/1/0"] == b"chunk c/1/0"
    assert any("streamed 3 chunk(s) of data.ome.zarr/0 (1 missing at the source: fill value)" in l for l in lines)
    assert not any(cmap["input_dir"] in l for l in lines)  # the source is never printed


def test_without_a_chunk_map_only_the_written_files_go_up(tmp_path):
    item, _ = micr(tmp_path)
    out = io.BytesIO()
    write_archive(item, out, log=lambda m: None)
    assert sorted(tar_members(out.getvalue())) == ["data.ome.zarr/0/zarr.json", "data.ome.zarr/zarr.json"]


def test_a_short_chunk_fails_the_upload_instead_of_sending_a_short_object(tmp_path):
    item, cmap = micr(tmp_path)

    def lying(source, key, input_dir=None):
        return Chunk(io.BytesIO(b"abc"), 999, 0)

    stub, api, rec = brainlife()
    with stub, pytest.raises(Exception):
        upload_datasets(HEADERS, PROJECT, [item], api=api, log=lambda m: None, chunk_map=cmap, open_source=lying)
    assert rec["registered"] == []


def test_cancel_stops_the_archive_thread(tmp_path):
    item, cmap = micr(tmp_path)
    blocks, cancel = stream_archive(item, cmap, log=lambda m: None)
    cancel()  # nothing read: the producer must not hang on a full queue


def test_a_64_mib_chunk_streams_with_little_memory(tmp_path):
    size = 64 * 2 ** 20
    data = bytearray(size)
    for i in range(0, size, 4096):  # not compressible to nothing
        data[i:i + 8] = i.to_bytes(8, "little")
    item, cmap = micr(tmp_path, bytes(data))
    del data
    stub, api, rec = brainlife(keep=False)
    with stub:
        tracemalloc.start()
        try:
            upload_datasets(HEADERS, PROJECT, [item], api=api, log=lambda m: None, chunk_map=cmap)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    assert rec["upload_size"] > 0
    assert peak < 16 * 2 ** 20, "peak %.1f MiB" % (peak / 2 ** 20)


# --- participants and project files -------------------------------------------------------------

def test_participants_go_to_the_participants_api(bids):
    stub, api, _ = brainlife()
    with stub:
        update_participants(HEADERS, PROJECT, walk(bids), api=api, log=lambda m: None)
    put = next(c for c in stub.calls if c["method"] == "PUT")
    assert put["json"] == {"subjects": [{"subject": "01", "age": "30"}, {"subject": "02", "age": "40"}],
                           "columns": {"age": {"Description": "age in years"}}}


def test_project_files_go_to_a_presigned_url_without_the_login(bids):
    stub, api, rec = brainlife()
    with stub:
        upload_project_files(HEADERS, PROJECT, bids, ["phenotype/moca.tsv"], api=api)
        with pytest.raises(bl.ApiError, match="403"):
            upload_project_files(HEADERS, PROJECT, bids, ["README"], api=api)
    post = next(c for c in stub.calls if c["path"].endswith("/upload/presigned"))
    with open(os.path.join(bids, "phenotype", "moca.tsv"), "rb") as f:
        expected = f.read()
    assert post["json"] == {"fileName": "phenotype/moca.tsv", "fileSize": len(expected),
                            "contentType": "application/octet-stream", "prefix": "bids/"}
    body, headers = rec["puts"]["/s3/bids/phenotype/moca.tsv"]
    assert body == expected and "authorization" not in headers
