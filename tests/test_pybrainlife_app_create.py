from unittest import mock

import pytest

from pybrainlife.api.app import app_create


def _fake_post_capturing(captured):
    """Mongoose auto-assigns each input/output subdocument its own `_id` on
    save -- a real create response has these even though the request payload
    doesn't. Fabricate them here rather than just echoing the raw payload
    back, or AppField.normalize()'s own `data["id"] = data["_id"]` rename
    crashes on entries that never got one."""

    def with_fake_ids(entries):
        return [{**entry, "_id": f"fake_id_{i}"} for i, entry in enumerate(entries)]

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
                "name": captured["payload"]["name"],
                "github": captured["payload"]["github"],
                "github_branch": captured["payload"]["github_branch"],
                "desc": "",
                "inputs": with_fake_ids(captured["payload"]["inputs"]),
                "outputs": with_fake_ids(captured["payload"]["outputs"]),
                "config": captured["payload"]["config"],
                "tags": [],
            }

    def fake_post(url, json=None, headers=None):
        captured["url"] = url
        captured["payload"] = json
        return FakeResponse()

    return fake_post


def test_app_create_defaults_and_normalizes_without_crashing():
    captured = {}
    with mock.patch("pybrainlife.api.app.requests.post", side_effect=_fake_post_capturing(captured)):
        app = app_create(name="Test App", github="myorg/app-test")

    assert captured["payload"]["github_branch"] == "main"
    assert captured["payload"]["config"] == {}
    assert captured["payload"]["inputs"] == []
    assert captured["payload"]["outputs"] == []
    assert app.name == "Test App"
    assert app.github == "myorg/app-test"


def test_app_create_rejects_bad_github_before_any_network_call():
    with mock.patch("pybrainlife.api.app.requests.post") as post:
        with pytest.raises(ValueError):
            app_create(name="Test App", github="https://github.com/myorg/app-test")
        post.assert_not_called()


def test_app_create_passes_through_explicit_values():
    captured = {}
    with mock.patch("pybrainlife.api.app.requests.post", side_effect=_fake_post_capturing(captured)):
        app_create(
            name="Test App",
            github="myorg/app-test",
            github_branch="1.0",
            config={"crop": {"type": "boolean", "default": True}},
            inputs=[{"id": "t1", "datatype": "58c33bcee13a50849b25879a", "datatype_tags": []}],
            outputs=[{"id": "output", "datatype": "58c33bcee13a50849b25879a", "datatype_tags": ["preprocessed"]}],
        )

    assert captured["payload"]["github_branch"] == "1.0"
    assert captured["payload"]["config"] == {"crop": {"type": "boolean", "default": True}}
    assert captured["payload"]["inputs"][0]["id"] == "t1"
    assert captured["payload"]["outputs"][0]["id"] == "output"
