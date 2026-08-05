"""Offline tests for classify_task_failure() and recover_failed_dataset().

Built after discovering, against a real stuck task, that a task can genuinely
succeed on rerun while the dataset it was supposed to produce stays stuck at
status="failed" -- dataset finalization is an internal amaretti->warehouse
callback gated behind a service-only secret, not something a normal user's
JWT can trigger directly. recover_failed_dataset() always re-checks the
dataset itself, never just the task's own "finished" status, and gives up
after `max_retries` rather than looping forever on something retries cannot
fix (see the "exhausted" result -- the caller/skill is responsible for then
proposing a full fresh resubmission, not this function).

Also covers two real gaps found while building this: pybrainlife's Dataset
never exposed `prov`/`status_msg` at all (every prior use of provenance in
this codebase had to fall back to a raw HTTP request instead), and the
Node CLI has no equivalent of PUT /task/rerun/:id either.
"""

from unittest import mock

from pybrainlife.api.dataset import Dataset
from pybrainlife.api.task import classify_task_failure, task_rerun, TaskProductArchiveFailed
from pybrainlife.api.compound.recovery import recover_failed_dataset


def test_task_rerun_puts_to_the_right_endpoint():
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"message": "Task successfully re-requested", "task": {"_id": "t1"}}

    captured = {}

    def fake_put(url, json=None, headers=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    with mock.patch("pybrainlife.api.task.requests.put", side_effect=fake_put):
        result = task_rerun("t1")

    assert captured["url"].endswith("/task/rerun/t1")
    assert result["message"] == "Task successfully re-requested"


# --- classify_task_failure -------------------------------------------------


def test_classify_task_failure_recognizes_known_transient_patterns():
    transient_messages = [
        "No resource currently available to run this task.. waiting.. ",
        "code 1 running timeout 60 mkdir -p /mnt/scratch/brlife/prod-archive/...",
        "connection reset by peer",
        "ENOSPC: no space left on device",
    ]
    for msg in transient_messages:
        assert classify_task_failure(msg) is True, msg


def test_classify_task_failure_rejects_unknown_messages():
    assert classify_task_failure("AssertionError: input file has 0 volumes") is False
    assert classify_task_failure("") is False
    assert classify_task_failure(None) is False


# --- Dataset.normalize(): prov/status_msg were missing entirely -----------


def test_dataset_normalize_exposes_prov_and_status_msg():
    data = {
        "_id": "6a7231adf2db7cfbc0691dd5",
        "project": "6a71322789d3cd2a98c8527e",
        "datatype": "58c33c5fe13a50849b25879b",
        "datatype_tags": [],
        "tags": [],
        "status": "failed",
        "status_msg": "code 1 running timeout 60 mkdir -p ...",
        "create_date": "2026-08-04T18:38:37.804Z",
        "removed": False,
        "meta": {},
        "prov": {"task_id": "6a722ceb1b568a365469dd30"},
    }

    dataset = Dataset.normalize(data)

    assert dataset.prov == {"task_id": "6a722ceb1b568a365469dd30"}
    assert dataset.status_msg == "code 1 running timeout 60 mkdir -p ..."


def test_dataset_normalize_defaults_missing_prov_and_status_msg():
    data = {
        "_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
        # project/datatype must look like real 24-hex ids -- nested_dataclass
        # tries to lazy-hydrate them (Project(value)/DataType(value)), and a
        # non-id-shaped placeholder string breaks that construction with a
        # confusing unrelated TypeError, not a real bug in Dataset itself.
        "project": "bbbbbbbbbbbbbbbbbbbbbbbb",
        "datatype": "cccccccccccccccccccccccc",
        "datatype_tags": [],
        "tags": [],
        "status": "stored",
        "create_date": "2026-08-04T18:38:37.804Z",
        "removed": False,
        "meta": {},
        # no "prov", no "status_msg"
    }

    dataset = Dataset.normalize(data)

    assert dataset.prov == {}
    assert dataset.status_msg is None


# --- recover_failed_dataset() ----------------------------------------------


class _FakeDataset:
    def __init__(self, id, status, status_msg=None, prov=None):
        self.id = id
        self.status = status
        self.status_msg = status_msg
        self.prov = prov or {}


def test_recover_failed_dataset_already_stored_short_circuits():
    with mock.patch(
        "pybrainlife.api.compound.recovery.dataset_query",
        return_value=[_FakeDataset("d1", "stored")],
    ) as dq, mock.patch("pybrainlife.api.compound.recovery.task_rerun") as rerun:
        result = recover_failed_dataset("d1")

    assert result.status == "already_stored"
    rerun.assert_not_called()
    dq.assert_called_once()


def test_recover_failed_dataset_not_transient_never_retries():
    failed = _FakeDataset("d1", "failed", status_msg="AssertionError: bad input", prov={"task_id": "t1"})
    with mock.patch("pybrainlife.api.compound.recovery.dataset_query", return_value=[failed]), \
         mock.patch("pybrainlife.api.compound.recovery.task_rerun") as rerun:
        result = recover_failed_dataset("d1")

    assert result.status == "not_transient"
    assert result.task_id == "t1"
    rerun.assert_not_called()


def test_recover_failed_dataset_recovers_on_first_retry():
    initial = _FakeDataset("d1", "failed", status_msg="mkdir timeout", prov={"task_id": "t1"})
    after_retry = _FakeDataset("d1", "stored")

    query_results = [[initial], [after_retry]]

    def fake_query(*args, **kwargs):
        return query_results.pop(0)

    with mock.patch("pybrainlife.api.compound.recovery.dataset_query", side_effect=fake_query), \
         mock.patch("pybrainlife.api.compound.recovery.task_rerun") as rerun, \
         mock.patch("pybrainlife.api.compound.recovery.task_wait") as wait, \
         mock.patch("pybrainlife.api.compound.recovery.time.sleep"):
        result = recover_failed_dataset("d1", max_retries=2, poll_wait=0)

    assert result.status == "recovered"
    assert result.attempts == 1
    rerun.assert_called_once_with("t1", auth=None)
    wait.assert_called_once()


def test_recover_failed_dataset_exhausts_retries_and_reports_fallback_needed():
    still_failed = _FakeDataset("d1", "failed", status_msg="mkdir timeout", prov={"task_id": "t1"})

    with mock.patch("pybrainlife.api.compound.recovery.dataset_query", return_value=[still_failed]), \
         mock.patch("pybrainlife.api.compound.recovery.task_rerun") as rerun, \
         mock.patch("pybrainlife.api.compound.recovery.task_wait"), \
         mock.patch("pybrainlife.api.compound.recovery.time.sleep"):
        result = recover_failed_dataset("d1", max_retries=2, poll_wait=0)

    assert result.status == "exhausted"
    assert result.attempts == 2
    assert rerun.call_count == 2


def test_recover_failed_dataset_catches_task_product_archive_failed():
    """Regression test for a real bug hit live: task_wait() -> task_wait_dataset()
    raises TaskProductArchiveFailed exactly when a task finishes but its own
    output dataset comes back failed -- precisely this function's scenario.
    The first version of recover_failed_dataset() only caught
    (TaskFailed, TaskInvalidState) and let this one escape uncaught."""
    initial = _FakeDataset("d1", "failed", status_msg="mkdir timeout", prov={"task_id": "t1"})
    after_retry = _FakeDataset("d1", "stored")
    query_results = [[initial], [after_retry]]

    def fake_query(*args, **kwargs):
        return query_results.pop(0)

    with mock.patch("pybrainlife.api.compound.recovery.dataset_query", side_effect=fake_query), \
         mock.patch("pybrainlife.api.compound.recovery.task_rerun"), \
         mock.patch("pybrainlife.api.compound.recovery.task_wait", side_effect=TaskProductArchiveFailed()), \
         mock.patch("pybrainlife.api.compound.recovery.time.sleep"):
        result = recover_failed_dataset("d1", max_retries=2, poll_wait=0)

    assert result.status == "recovered"
