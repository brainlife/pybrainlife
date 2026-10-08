"""Offline tests for datatype.py's datatype_create() -- added for
braise-datatype-create. POST /datatype's payload shape and validation rules
below were confirmed by reading warehouse-next's real
api/controllers/datatype.js (the only server-side gate is the
`datatype.create` scope -- no schema validation at all) and
ui/src/datatypeedit.vue (the client-side rules the real "new datatype" form
enforces: file id must not contain '.', and each file needs exactly one of
filename/dirname, never both, never neither).
"""

import copy
from unittest import mock

from pybrainlife.api.datatype import datatype_create


def _fake_post_capturing(captured):
    # DataType.normalize() mutates the dict it's given in place (adds
    # "id"/"description" on top of "_id"/"desc") -- request_payload is a
    # snapshot taken before that mutation, so assertions on what was actually
    # *sent* aren't clobbered by what normalize() does to the *response*.
    class FakeResponse:
        status_code = 200

        def json(self):
            response = copy.deepcopy(captured["payload"])
            response["_id"] = "dtypeaaaaaaaaaaaaaaaaaaa"
            response["files"] = [
                {**f, "_id": f"fileid{i}"} for i, f in enumerate(response["files"])
            ]
            return response

    def fake_post(url, json=None, headers=None):
        captured["url"] = url
        captured["payload"] = json
        captured["request_payload"] = copy.deepcopy(json)
        return FakeResponse()

    return fake_post


def test_datatype_create_sends_expected_payload_shape():
    captured = {}
    with mock.patch("pybrainlife.api.datatype.requests.post", side_effect=_fake_post_capturing(captured)):
        dt = datatype_create(
            name="neuro/test_datatype",
            desc="test datatype creation",
            admins=["1662"],
            uis=["5be75b31e15a02914a4be8f0"],
        )

    assert captured["url"].endswith("/datatype")
    assert captured["request_payload"]["_id"] is None
    assert captured["request_payload"]["name"] == "neuro/test_datatype"
    assert captured["request_payload"]["admins"] == ["1662"]
    assert captured["request_payload"]["uis"] == ["5be75b31e15a02914a4be8f0"]
    assert captured["request_payload"]["groupAnalysis"] is False
    assert dt.name == "neuro/test_datatype"


def test_datatype_create_rejects_file_id_with_dot():
    try:
        datatype_create(
            name="neuro/test", desc="d",
            files=[{"id": "t1.nii", "filename": "t1.nii.gz"}],
        )
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_datatype_create_rejects_file_with_both_filename_and_dirname():
    try:
        datatype_create(
            name="neuro/test", desc="d",
            files=[{"id": "t1", "filename": "t1.nii.gz", "dirname": "t1dir"}],
        )
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_datatype_create_rejects_file_with_neither_filename_nor_dirname():
    try:
        datatype_create(name="neuro/test", desc="d", files=[{"id": "t1"}])
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_datatype_create_rejects_validator_missing_prefix():
    try:
        datatype_create(name="neuro/test", desc="d", validator="myorg/myvalidator")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_datatype_create_accepts_valid_file_and_validator():
    captured = {}
    with mock.patch("pybrainlife.api.datatype.requests.post", side_effect=_fake_post_capturing(captured)):
        datatype_create(
            name="neuro/test", desc="d",
            files=[{"id": "t1", "filename": "t1.nii.gz", "required": True}],
            validator="brainlife/validator-neuro-test",
        )
    assert captured["request_payload"]["files"] == [{"id": "t1", "filename": "t1.nii.gz", "required": True}]
    assert captured["request_payload"]["validator"] == "brainlife/validator-neuro-test"
