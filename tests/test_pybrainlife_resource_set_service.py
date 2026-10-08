"""Offline tests for resource_set_service() -- added for
braise-resource-enable-app. Confirmed against amaretti-next's real
api/controllers/resource.js: `services` (the {name, score} list an app is
enabled with on a resource) lives under `config.services`, never top-level
-- resource_create()/resource_update() previously wrote it (and `hostname`)
to a top-level key that doesn't exist anywhere in the real resourceSchema, a
dead no-op mongoose silently drops. `config` itself is `Schema.Types.Mixed`
and PUT /resource/:id does `$set: req.body` -- $set replaces `config`
wholesale, no deep merge -- so resource_set_service() always fetches the
resource's current config first and only ever touches the one matching
`services` entry, to avoid the exact failure mode a browser-scraped "edit
resource" PUT risks: silently dropping every config key the caller didn't
happen to re-send (ssh_public, hostname, aws creds, ...).
"""

from unittest import mock

from pybrainlife.api.resource import resource_set_service


class _FakeResource:
    def __init__(self, id="aaaaaaaaaaaaaaaaaaaaaaaa", config=None):
        self.id = id
        self.config = config or {}


def _fake_put_capturing(captured, response_config):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"_id": "aaaaaaaaaaaaaaaaaaaaaaaa", "user_id": "1", "name": "r", "config": response_config}

    def fake_put(url, json=None, headers=None):
        captured["url"] = url
        captured["payload"] = json
        return FakeResponse()

    return fake_put


def test_resource_set_service_appends_new_entry_without_touching_other_config_keys():
    existing_config = {
        "hostname": "slurm24.brainlife.io",
        "ssh_public": "ssh-rsa AAAA...",
        "enc_ssh_private": True,  # masked sentinel from a real GET -- must round-trip unchanged
        "services": [{"name": "brainlife/app-fsl-anat", "score": 10}],
    }
    resource = _FakeResource(config=existing_config)
    captured = {}

    with mock.patch("pybrainlife.api.resource.resource_fetch", return_value=resource), \
         mock.patch("pybrainlife.api.resource.requests.put",
                     side_effect=_fake_put_capturing(captured, existing_config)):
        resource_set_service(resource.id, "gamorosino/app-ac-segmentation", score=10)

    assert captured["url"].endswith("/resource/" + resource.id)
    # only "config" is sent -- no admins/gids/name/aws_config/etc, so those
    # top-level fields are left completely untouched server-side.
    assert set(captured["payload"]) == {"config"}
    sent_config = captured["payload"]["config"]
    assert sent_config["hostname"] == "slurm24.brainlife.io"
    assert sent_config["ssh_public"] == "ssh-rsa AAAA..."
    assert sent_config["enc_ssh_private"] is True
    assert {"name": "brainlife/app-fsl-anat", "score": 10} in sent_config["services"]
    assert {"name": "gamorosino/app-ac-segmentation", "score": 10} in sent_config["services"]
    assert len(sent_config["services"]) == 2


def test_resource_set_service_updates_score_of_existing_entry_in_place():
    existing_config = {
        "services": [
            {"name": "gamorosino/app-ac-segmentation", "score": 0},
            {"name": "brainlife/app-fsl-anat", "score": 10},
        ],
    }
    resource = _FakeResource(config=existing_config)
    captured = {}

    with mock.patch("pybrainlife.api.resource.resource_fetch", return_value=resource), \
         mock.patch("pybrainlife.api.resource.requests.put",
                     side_effect=_fake_put_capturing(captured, existing_config)):
        resource_set_service(resource.id, "gamorosino/app-ac-segmentation", score=10)

    sent_services = captured["payload"]["config"]["services"]
    assert len(sent_services) == 2  # updated in place, never appended a duplicate
    assert {"name": "gamorosino/app-ac-segmentation", "score": 10} in sent_services
    assert {"name": "brainlife/app-fsl-anat", "score": 10} in sent_services


def test_resource_set_service_raises_for_unknown_resource():
    with mock.patch("pybrainlife.api.resource.resource_fetch", return_value=None):
        try:
            resource_set_service("deadbeefdeadbeefdeadbeef", "org/app", score=10)
            raised = False
        except Exception:
            raised = True
    assert raised
