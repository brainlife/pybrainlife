"""Offline unit tests for the *.normalize() dataclass builders in api/*.py.

These use hand-built dicts shaped like the raw warehouse/amaretti API
responses -- no network access, no auth, unlike most of this package's
existing tests. They cover two real bugs found while dogfooding pybrainlife
against a live brainlife.io project:

1. Several normalize() methods assumed "desc" is always present
   (`data["desc"]`), which KeyErrors on any real project/dataset/datatype/app
   that has no description set.
2. AppInputField.normalize()/AppOutputField.normalize() built an AppField
   first (whose dataclass has no optional/multi/advanced/archive/
   output_on_root fields) and then tried to read those flags back out of
   that already-built object's __dict__ -- they were never there to begin
   with, so every input's `optional` (and every output's `archive`) silently
   came back False regardless of the real app schema.
"""

from pybrainlife.api.project import Project
from pybrainlife.api.app import AppInputField, AppOutputField


def test_project_normalize_missing_desc_does_not_raise():
    data = {
        "_id": "6a6d2494c8fb994d870651c0",
        "name": "DWI-pilot",
        "group_id": 26042,
        "admins": ["gamorosino"],
        "members": [],
        "guests": [],
        "stats": {"datasets": {"subject_count": 1, "count": 14, "size": 0}},
        # no "desc" key -- this is what a project created without --desc looks like
    }

    project = Project.normalize(data)

    assert project.description == ""
    assert project.name == "DWI-pilot"


def test_app_input_field_normalize_preserves_optional():
    data = {
        "_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
        "id": "reverse",
        "datatype": "58c33c5fe13a50849b25879b",
        "datatype_tags": [],
        "optional": True,
    }

    field = AppInputField.normalize(data)

    assert field.optional is True


def test_app_input_field_normalize_defaults_required_to_false():
    data = {
        "_id": "bbbbbbbbbbbbbbbbbbbbbbbb",
        "id": "dwi",
        "datatype": "58c33c5fe13a50849b25879b",
        "datatype_tags": [],
        "optional": False,
    }

    field = AppInputField.normalize(data)

    assert field.optional is False


def test_app_output_field_normalize_preserves_archive():
    data = {
        "_id": "cccccccccccccccccccccccc",
        "id": "acpc",
        "datatype": "58c33bcee13a50849b25879a",
        "datatype_tags": [],
        "archive": True,
    }

    field = AppOutputField.normalize(data)

    assert field.archive is True


def test_app_output_field_normalize_preserves_archive_false():
    data = {
        "_id": "dddddddddddddddddddddddd",
        "id": "bias",
        "datatype": "58c33bcee13a50849b25879a",
        "datatype_tags": [],
        "archive": False,
    }

    field = AppOutputField.normalize(data)

    assert field.archive is False
