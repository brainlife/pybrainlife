"""Offline tests for pipeline.py -- brainlife's real "Pipeline" feature,
internally called `Rules` (POST/GET /rule, PUT /rule/order/:projectId).

Built while adding braise-pipeline-export: fixed a real bug found by reading
pipeline_create()'s actual payload construction (an `input_dataset_tags`
parameter that doesn't exist anywhere in warehouse's real `Rules` mongoose
schema -- confirmed by reading warehouse's actual api/models.js -- dead/
mistaken code, since `input_tags` already exists and is the correct field),
and added pipeline_set_order() (PUT /rule/order/:projectId), which did not
exist in this library before.
"""

from unittest import mock

from pybrainlife.api.pipeline import (
    build_pipeline_group,
    pipeline_create,
    pipeline_set_order,
)


class _FakeInputField:
    def __init__(self, field):
        self.field = field


# nested_dataclass's @hydrate lazily resolves any id-shaped string via a
# network fetch -- a non-24-hex placeholder like "app1" breaks construction
# with a confusing unrelated TypeError, not a real bug in the code under
# test (same gotcha documented in test_pybrainlife_recovery.py). Use
# realistic 24-hex placeholders for anything typed as Project/App.
class _FakeApp:
    def __init__(self, id="aaaaaaaaaaaaaaaaaaaaaaaa", github_branch="main", config=None, inputs=None, outputs=None):
        self.id = id
        self.name = "Test App"
        self.github_branch = github_branch
        self.config = config or {}
        self.inputs = [_FakeInputField(f) for f in (inputs or [])]
        self.outputs = [_FakeInputField(f) for f in (outputs or [])]


class _FakeProject:
    def __init__(self, id="bbbbbbbbbbbbbbbbbbbbbbbb", pipelines=None):
        self.id = id
        self.pipelines = pipelines


class _FakeRule:
    def __init__(self, id):
        self.id = id


def _fake_post_capturing(captured):
    class FakeResponse:
        status_code = 200

        def json(self):
            # project/app stay plain id strings (not dicts) here -- Rule.normalize()
            # only normalizes them as full objects when the server embeds a dict
            # (populate=app); a bare id string is left as-is, which is what a
            # non-populated create response actually looks like.
            captured["payload"]["_id"] = "ruleaaaaaaaaaaaaaaaaaaaa"
            return captured["payload"]

    def fake_post(url, json=None, headers=None):
        captured["url"] = url
        captured["payload"] = json
        return FakeResponse()

    return fake_post


def test_pipeline_create_never_sends_input_dataset_tags():
    # Regression test: input_dataset_tags isn't a real Rules schema field --
    # confirmed against warehouse's actual mongoose schema -- so it must never
    # appear in the POST /rule payload.
    #
    # A real (un-populated) POST /rule response embeds project/app as bare
    # ObjectId strings, which Rule.normalize() lazily re-fetches via
    # nested_dataclass's @hydrate -- a real network call in production. These
    # two tests only care about the request payload, not the parsed return
    # value, so Rule.normalize() is bypassed rather than faking that fetch.
    app = _FakeApp(config={"crop": {"type": "boolean", "default": True}}, inputs=["dwi"], outputs=["output"])
    project = _FakeProject()
    captured = {}
    with mock.patch("pybrainlife.api.pipeline.requests.post", side_effect=_fake_post_capturing(captured)), \
         mock.patch("pybrainlife.api.pipeline.Rule.normalize", side_effect=lambda data: data):
        pipeline_create(project, app, input_tags={"dwi": ["preprocessed"]})

    assert "input_dataset_tags" not in captured["payload"]
    assert captured["payload"]["input_tags"] == {"dwi": ["preprocessed"]}


def test_pipeline_create_defaults_active_true_unless_overridden():
    app = _FakeApp()
    project = _FakeProject()
    captured = {}
    with mock.patch("pybrainlife.api.pipeline.requests.post", side_effect=_fake_post_capturing(captured)), \
         mock.patch("pybrainlife.api.pipeline.Rule.normalize", side_effect=lambda data: data):
        pipeline_create(project, app)
    assert captured["payload"]["active"] is True

    with mock.patch("pybrainlife.api.pipeline.requests.post", side_effect=_fake_post_capturing(captured)), \
         mock.patch("pybrainlife.api.pipeline.Rule.normalize", side_effect=lambda data: data):
        pipeline_create(project, app, active=False)
    assert captured["payload"]["active"] is False


def test_pipeline_create_rejects_unknown_output_tag_field():
    app = _FakeApp(outputs=["output"])
    project = _FakeProject()
    try:
        pipeline_create(project, app, output_tags={"nonexistent_field": ["x"]})
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_build_pipeline_group_shape():
    rules = [_FakeRule("r1"), _FakeRule("r2")]
    group = build_pipeline_group("My Pipeline", rules)
    assert group == {
        "type": "group",
        "name": "My Pipeline",
        "items": [{"type": "rule", "ruleId": "r1"}, {"type": "rule", "ruleId": "r2"}],
    }


def test_pipeline_set_order_appends_to_existing_root_rather_than_overwriting():
    # A project that already has an unrelated existing group must keep it --
    # PUT /rule/order/:projectId replaces the whole field server-side, so the
    # client must merge, not overwrite.
    existing_root = {"type": "group", "items": [{"type": "rule", "ruleId": "old_rule"}]}
    project = _FakeProject(pipelines=existing_root)
    new_group = build_pipeline_group("New Pipeline", [_FakeRule("r1")])

    captured = {}

    def fake_put(url, json=None, headers=None):
        captured["url"] = url
        captured["payload"] = json
        class FakeResponse:
            status_code = 200
            def json(self):
                return {"status": "ok"}
        return FakeResponse()

    with mock.patch("pybrainlife.api.pipeline.project_fetch", return_value=project), \
         mock.patch("pybrainlife.api.pipeline.requests.put", side_effect=fake_put):
        pipeline_set_order(project, new_group)

    assert captured["url"].endswith("/rule/order/bbbbbbbbbbbbbbbbbbbbbbbb")
    items = captured["payload"]["items"]
    assert {"type": "rule", "ruleId": "old_rule"} in items
    assert new_group in items


def test_pipeline_set_order_starts_fresh_when_no_existing_pipelines():
    project = _FakeProject(pipelines=None)
    new_group = build_pipeline_group("New Pipeline", [_FakeRule("r1")])

    captured = {}

    def fake_put(url, json=None, headers=None):
        captured["payload"] = json
        class FakeResponse:
            status_code = 200
            def json(self):
                return {"status": "ok"}
        return FakeResponse()

    with mock.patch("pybrainlife.api.pipeline.project_fetch", return_value=project), \
         mock.patch("pybrainlife.api.pipeline.requests.put", side_effect=fake_put):
        pipeline_set_order(project, new_group)

    assert captured["payload"]["items"] == [new_group]
