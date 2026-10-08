"""Offline tests for dataset.py's dataset_provenance() -- GET /dataset/prov/:id,
the same endpoint warehouse's web UI hits for its "download provenance"
button. Added alongside braise's fetch-metadata/fetch-provenance skills,
which needed this wrapped (previously only reachable via a raw requests call)."""

from unittest import mock

from pybrainlife.api.dataset import dataset_provenance


def _fake_get_returning(payload):
    class FakeResponse:
        status_code = 200

        def json(self):
            return payload

    def fake_get(url, headers=None):
        fake_get.last_url = url
        return FakeResponse()

    return fake_get


def test_dataset_provenance_hits_the_real_endpoint_and_returns_the_raw_shape():
    payload = {"nodes": [{"id": "task.aaaa"}], "edges": [{"from": "task.aaaa", "to": "dataset.bbbb"}]}
    fake_get = _fake_get_returning(payload)
    with mock.patch("pybrainlife.api.dataset.requests.get", side_effect=fake_get):
        result = dataset_provenance("bbbbbbbbbbbbbbbbbbbbbbbb")

    assert fake_get.last_url.endswith("/dataset/prov/bbbbbbbbbbbbbbbbbbbbbbbb")
    # Returned as-is (a plain dict), not wrapped in a dataclass -- this is the
    # exact shape import_pipeline_from_provenance.py expects when loading a
    # provenance.json from disk, so the two must stay interchangeable.
    assert result == payload
