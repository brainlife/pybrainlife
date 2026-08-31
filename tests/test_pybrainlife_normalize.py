"""Offline unit tests for the *.normalize() dataclass builders in api/*.py.

These use hand-built dicts shaped like the raw warehouse/amaretti API
responses -- no network access, no auth, unlike most of this package's
existing tests. They cover three real bugs found while dogfooding pybrainlife
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
3. app_run() overwrote its own `config` parameter (the caller's override
   dict) with `app.config` (the app's config *schema*) before ever using it,
   so _prepare_app_config() always received the schema instead of the
   caller's overrides and every submission silently used only the app's
   built-in defaults, no matter what `config=` was passed to app_run().
4. _prepare_outputs()/_prepare_config() used `.id` (the field's own internal
   database id, set by AppField.normalize()/DataTypeFile.normalize()'s rename
   of the raw API's "id" -> "_id"/"id") where they meant `.field` (the app's
   semantic slot name, e.g. "acpc", "t1") -- ported literally from the Node
   CLI, whose *raw, unrenamed* JSON has no such distinction. This sent the
   archiver a subdir/output id the running container never produces (every
   app_run() submission failed within under a second, before any real work
   started) and silently dropped every input-type config value (e.g. the
   file path fsl-anat's own script reads its T1 from) with no error at all.
5. _validate_datatype_tags() built `set(dataset.datatype_tags)` -- a set of
   DataTypeTag objects, which have no __hash__ (a plain, unfrozen dataclass)
   -- raising TypeError on any dataset that actually carries a datatype tag
   (only missed by earlier testing because the first dataset tried had none).
6. app_run()'s resource_id handling assigned the *whole list* resource_query()
   returns to `preferred_resource_id`, instead of a single resource id string
   -- confirmed wrong against the Node `bl` CLI's own bl-app-run.js, which
   extracts a single id (`resource = userResource._id`) before submitting.
"""

from unittest import mock

from pybrainlife.api.project import Project
from pybrainlife.api.app import (
    AppInputField,
    AppOutputField,
    _prepare_app_config,
    _prepare_config,
    _resolve_preferred_resource_id,
    _validate_datatype_tags,
)
from pybrainlife.api.datatype import DataTypeTag
from pybrainlife.api.resource import Resource


def test_project_normalize_missing_desc_does_not_raise():
    data = {
        "_id": "6a6d2494c8fb994d870651c0",
        "name": "DWI-pilot",
        "group_id": 26042,
        "user_id": "1662",
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


class _FakeApp:
    """Minimal stand-in for App -- _prepare_app_config only reads .config."""

    def __init__(self, config):
        self.config = config


def test_prepare_app_config_respects_user_override():
    app = _FakeApp(
        config={
            "crop": {"type": "boolean", "default": False},
            "reorient": {"type": "boolean", "default": False},
        }
    )

    values = _prepare_app_config(app, {"crop": True, "reorient": True})

    assert values["crop"] is True
    assert values["reorient"] is True


def test_prepare_app_config_falls_back_to_schema_default_when_no_override():
    app = _FakeApp(config={"crop": {"type": "boolean", "default": False}})

    values = _prepare_app_config(app, {})

    assert values["crop"] is False


def test_prepare_app_config_skips_input_type_keys():
    app = _FakeApp(
        config={
            "t1": {"type": "input", "input_id": "t1"},
            "crop": {"type": "boolean", "default": True},
        }
    )

    values = _prepare_app_config(app, {"t1": "should-be-ignored"})

    assert "t1" not in values
    assert values["crop"] is True


class _FakeDataTypeFile:
    def __init__(self, field, name):
        self.field = field
        self.name = name


class _FakeDataType:
    def __init__(self, id, files):
        self.id = id
        self.files = files


class _FakeDataset:
    def __init__(self, id, datatype):
        self.id = id
        self.datatype = datatype


class _FakeTask:
    def __init__(self, id):
        self.id = id


class _FakeAppInputField:
    def __init__(self, field, multi=False):
        self.field = field
        self.multi = multi


class _FakeAppWithInputs:
    def __init__(self, config, inputs):
        self.config = config
        self.inputs = inputs


def test_prepare_config_builds_input_filepath():
    """DataTypeFile.normalize() renames the same way AppField.normalize()
    does (semantic name -> .field, internal db id -> .id) -- a config spec's
    file_id ("t1") is a semantic name, so looking it up in a dict keyed by
    .id (as _prepare_config used to) never matches, and the whole input-type
    config key silently vanishes with no error."""
    dt_file = _FakeDataTypeFile(field="t1", name="t1.nii.gz")
    datatype = _FakeDataType(id="dt1", files=[dt_file])
    dataset = _FakeDataset(id="ds1", datatype=datatype)
    task = _FakeTask(id="task1")
    app = _FakeAppWithInputs(
        config={"input": {"type": "input", "input_id": "t1", "file_id": "t1"}},
        inputs=[_FakeAppInputField(field="t1")],
    )

    result = _prepare_config({}, task, {"t1": [dataset]}, datatypes={"dt1": datatype}, app=app)

    assert result["input"] == "../task1/ds1/t1.nii.gz"


def test_prepare_config_multi_input_builds_filepath_list():
    dt_file = _FakeDataTypeFile(field="dwi", name="dwi.nii.gz")
    datatype = _FakeDataType(id="dt2", files=[dt_file])
    dataset_a = _FakeDataset(id="ds-a", datatype=datatype)
    dataset_b = _FakeDataset(id="ds-b", datatype=datatype)
    task = _FakeTask(id="task2")
    app = _FakeAppWithInputs(
        config={"dwis": {"type": "input", "input_id": "dwi", "file_id": "dwi"}},
        inputs=[_FakeAppInputField(field="dwi", multi=True)],
    )

    result = _prepare_config(
        {}, task, {"dwi": [dataset_a, dataset_b]}, datatypes={"dt2": datatype}, app=app
    )

    assert result["dwis"] == ["../task2/ds-a/dwi.nii.gz", "../task2/ds-b/dwi.nii.gz"]


class _FakeDatasetWithTags:
    def __init__(self, id, datatype_tags):
        self.id = id
        self.datatype_tags = datatype_tags


class _FakeAppInputWithTags:
    def __init__(self, datatype_tags):
        self.datatype_tags = datatype_tags


def test_validate_datatype_tags_does_not_crash_on_real_tags():
    dataset = _FakeDatasetWithTags(
        id="ds1",
        datatype_tags=[
            DataTypeTag(name="acpc_aligned", negate=False),
            DataTypeTag(name="preprocessed", negate=False),
        ],
    )
    app_input = _FakeAppInputWithTags(datatype_tags=[DataTypeTag(name="preprocessed", negate=False)])

    _validate_datatype_tags("anat", dataset, app_input)  # should not raise


def test_validate_datatype_tags_rejects_missing_required_tag():
    dataset = _FakeDatasetWithTags(id="ds1", datatype_tags=[DataTypeTag(name="preprocessed", negate=False)])
    app_input = _FakeAppInputWithTags(datatype_tags=[DataTypeTag(name="acpc_aligned", negate=False)])

    try:
        _validate_datatype_tags("anat", dataset, app_input)
        assert False, "expected ValueError for missing required tag"
    except ValueError:
        pass


def test_validate_datatype_tags_rejects_forbidden_tag_present():
    dataset = _FakeDatasetWithTags(id="ds1", datatype_tags=[DataTypeTag(name="preprocessed", negate=False)])
    app_input = _FakeAppInputWithTags(datatype_tags=[DataTypeTag(name="preprocessed", negate=True)])

    try:
        _validate_datatype_tags("dwi", dataset, app_input)
        assert False, "expected ValueError for forbidden tag present"
    except ValueError:
        pass


class _FakeResource:
    def __init__(self, id):
        self.id = id


def test_resolve_preferred_resource_id_returns_single_string():
    with mock.patch(
        "pybrainlife.api.app.resource_query",
        return_value=[_FakeResource("671078f56c9e5e0a511d9d09")],
    ):
        result = _resolve_preferred_resource_id("671078f56c9e5e0a511d9d09")

    assert result == "671078f56c9e5e0a511d9d09"
    assert isinstance(result, str)


def test_resolve_preferred_resource_id_raises_on_no_match():
    with mock.patch("pybrainlife.api.app.resource_query", return_value=[]):
        try:
            _resolve_preferred_resource_id("nonexistent")
            assert False, "expected Exception for no matching resource"
        except Exception:
            pass


def test_resource_normalize_missing_admins_does_not_raise():
    """A real resource document can come back with no `admins` key at all --
    Resource.normalize() used to require it outright via Resource(**data),
    the same missing-field crash already found and fixed for storage/desc
    elsewhere. Confirmed against a live resource_query() call after fixing."""
    data = {
        "_id": "67d20dcab28568ddad17d1d1",
        "user_id": "1662",
        "name": "Lonestar6-gpu-h100-gamorosino",
        # no "admins" key
    }

    resource = Resource.normalize(data)

    assert resource.admins == []
    assert resource.name == "Lonestar6-gpu-h100-gamorosino"
