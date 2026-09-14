"""Recover a failed dataset by retrying the specific task that produced it.

Built after discovering (the hard way, dogfooding against a real stuck task)
that a task can genuinely succeed on rerun while the dataset it was supposed
to produce stays stuck at status="failed" -- dataset finalization is an
internal amaretti->warehouse callback gated behind a service-only secret, not
something a normal user's JWT can trigger directly. So this always verifies
the dataset itself reaches "stored", never just that the task reports
"finished", and gives up on retrying the same task/dataset after a bounded
number of attempts rather than looping forever on something retries cannot
fix.
"""

import time
from dataclasses import dataclass
from typing import Optional

from ..dataset import dataset_query
from ..task import (
    classify_task_failure,
    task_rerun,
    task_wait,
    TaskFailed,
    TaskInvalidState,
    TaskProductArchiveFailed,
)


@dataclass
class RecoveryResult:
    status: str  # "already_stored" | "recovered" | "not_transient" | "exhausted"
    dataset_id: str
    task_id: Optional[str] = None
    status_msg: Optional[str] = None
    attempts: int = 0


def recover_failed_dataset(
    dataset_id: str,
    max_retries: int = 2,
    poll_wait: int = 5,
    auth=None,
) -> RecoveryResult:
    """Attempt to recover a dataset stuck at status="failed" by retrying the
    specific task that produced it (traced via the dataset's own
    `prov.task_id` -- often a validator/archiver sub-task, not the parent
    compute task), verifying after each attempt that the dataset itself
    reaches "stored", not just that the task reports "finished".

    Returns a RecoveryResult, never raises for the "this needs a human"
    outcomes -- only network/auth-level errors propagate:
      - "already_stored": nothing to do, the dataset was fine all along.
      - "recovered": a retry succeeded and the dataset is now "stored".
      - "not_transient": the failure doesn't match known transient-infra
        patterns (see classify_task_failure()) -- retrying is unlikely to
        help and risks masking a real problem. Never auto-retried.
      - "exhausted": `max_retries` transient-looking retries did not get the
        dataset to "stored". This is the fallback-layer signal: continuing to
        retry the same task is not the fix -- a full fresh resubmission of
        the parent app (a brand-new task+dataset lineage) is. That decision
        belongs to the caller (surface it and ask), not this function.
    """
    dataset = dataset_query(id=dataset_id, limit=1, auth=auth)
    if not dataset:
        raise Exception(f"no dataset found with id {dataset_id}")
    dataset = dataset[0]

    if dataset.status == "stored":
        return RecoveryResult(status="already_stored", dataset_id=dataset_id)

    task_id = dataset.prov.get("task_id")
    if not task_id:
        raise Exception(f"dataset {dataset_id} has no prov.task_id -- cannot trace its producing task")

    status_msg = dataset.status_msg
    if not classify_task_failure(status_msg or ""):
        return RecoveryResult(
            status="not_transient", dataset_id=dataset_id, task_id=task_id, status_msg=status_msg
        )

    for attempt in range(1, max_retries + 1):
        task_rerun(task_id, auth=auth)
        try:
            task_wait(task_id, wait=poll_wait, auth=auth)
        except (TaskFailed, TaskInvalidState, TaskProductArchiveFailed):
            # TaskProductArchiveFailed is exactly our scenario surfacing
            # through a different code path: task_wait() -> task_wait_dataset()
            # raises this when the task itself finished but its own output
            # dataset comes back "failed" -- precisely what this function
            # exists to detect and retry. Fall through to our own re-check
            # either way rather than letting this escape as an exception.
            pass

        time.sleep(poll_wait)  # give the finalization callback a moment even after the task itself reports done
        refreshed = dataset_query(id=dataset_id, limit=1, auth=auth)
        if refreshed and refreshed[0].status == "stored":
            return RecoveryResult(
                status="recovered", dataset_id=dataset_id, task_id=task_id, attempts=attempt
            )

    final = dataset_query(id=dataset_id, limit=1, auth=auth)
    final_msg = final[0].status_msg if final else status_msg
    return RecoveryResult(
        status="exhausted",
        dataset_id=dataset_id,
        task_id=task_id,
        status_msg=final_msg,
        attempts=max_retries,
    )
