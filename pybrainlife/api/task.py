import uuid
import time
import json
import requests
from dataclasses import field
from typing import List, Dict, Union, Optional, overload


from .utils import is_id, nested_dataclass, api_error
from .api import auth_header, services


@nested_dataclass
class Instance:
    id: str
    status: str
    name: Optional[str] = None
    desc: Optional[str] = None
    config: Dict = field(default_factory=dict)

    @overload
    @staticmethod
    def normalize(data: List[Dict]) -> List["Instance"]: ...

    @overload
    @staticmethod
    def normalize(data: Dict) -> "Instance": ...

    @staticmethod
    def normalize(data: Union[Dict, List[Dict]]) -> Union["Instance", List["Instance"]]:
        if isinstance(data, list):
            return [Instance.normalize(d) for d in data]
        data["id"] = data["_id"]
        return Instance(**data)


@nested_dataclass
class Task:
    id: str
    name: str
    status: str
    status_text: Optional[str] = None
    config: Dict = field(default_factory=dict)

    @overload
    @staticmethod
    def normalize(data: List[Dict]) -> List["Task"]: ...

    @overload
    @staticmethod
    def normalize(data: Dict) -> "Task": ...

    @staticmethod
    def normalize(data: Union[Dict, List[Dict]]) -> Union["Task", List["Task"]]:
        if isinstance(data, list):
            return [Task.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["status_text"] = data.pop("status_msg", None)
        return Task(**data)


def instance_query(
    id=None, name=None, group=None, search=None, skip=0, limit=100, auth=None
) -> List[Instance]:
    query = {}
    if search:
        if is_id(search):
            query["_id"] = search
        else:
            query["name"] = search
    else:
        if id:
            query["_id"] = id
        if name:
            query["name"] = {"$regex": name, "$options": "ig"}

    if group is not None:
        query["group_id"] = group

    res = requests.get(
        services["amaretti"] + "/instance",
        params={
            "find": json.dumps(query),
            "sort": "id",
            "skip": skip,
            "limit": limit,
        },
        headers={**auth_header(auth)},
    )

    api_error(res)

    return Instance.normalize(res.json()["instances"])


def instance_create(name, description=None, project=None, auth=None) -> Instance:
    data = {
        "name": name,
        "desc": description,
    }
    if project:
        data["config"] = {"brainlife": True}
        data["group_id"] = project.group

    res = requests.post(
        f'{services["amaretti"]}/instance',
        json=data,
        headers={**auth_header(auth)},
    )

    api_error(res)

    instance = res.json()
    return Instance.normalize(instance)


def task_run(instance, name, service, config, auth=None) -> Task:
    url = services["amaretti"] + "/task"
    res = requests.post(
        url,
        json={
            "instance_id": instance,
            "name": name,
            "service": service,
            "config": config,
        },
        headers={**auth_header(auth)},
    )

    api_error(res)

    task = res.json()["task"]
    return Task.normalize(task)


def task_run_app(config, auth=None):
    """
    Submits a task based on the provided configuration.

    Args:
        config (dict): The configuration for the task submission.
        services (dict): A dictionary containing service URLs.
        auth_header (dict): The authentication headers for the request.

    Returns:
        Task: A normalized Task object representing the submitted task.

    Raises:
        Exception: If the request fails or the API returns a non-200 status code.
    """
    url = services["amaretti"] + "/task"
    res = requests.post(
        url,
        json=config,
        headers={**auth_header(auth)},
    )

    api_error(res)

    task = res.json().get("task")
    return Task.normalize(task)


def task_fetch(id, auth=None) -> Optional[Task]:
    res = requests.get(
        services["amaretti"] + "/task",
        params={
            "find": json.dumps({"_id": id}),
            "limit": 1,
        },
        headers={**auth_header(auth)},
    )

    api_error(res)

    tasks = Task.normalize(res.json()["tasks"])
    if len(tasks) == 0:
        return None
    return tasks[0]


def task_wait_dataset(id, auth=None):
    while True:
        url = services["warehouse"] + "/dataset"
        res = requests.get(
            url,
            params={
                "find": json.dumps({"prov.task_id": id}),
            },
            headers={**auth_header(auth)},
        )
        datasets = res.json()["datasets"]
        if len(datasets) == 0:
            return []

        archived = [d for d in datasets if d["status"] == "stored"]
        if len(archived) == len(datasets):
            return datasets

        failed = [d for d in datasets if d["status"] == "failed"]
        if len(failed) > 0:
            raise TaskProductArchiveFailed()

        time.sleep(3)


class TaskInvalidState(Exception):
    def __init__(self, task=None):
        self.task = task


class TaskFailed(Exception):
    def __init__(self, task=None):
        self.task = task


class TaskProductArchiveFailed(Exception):
    def __init__(self, task=None):
        self.task = task


def task_wait(id, wait=3, auth=None):
    while True:
        task = task_fetch(id, auth=auth)
        if task is not None:
            if task.status == "finished":
                if "_outputs" in task.config:
                    datasets_archive = len(
                        [
                            output
                            for output in task.config["_outputs"]
                            if output["archive"]
                        ]
                    )
                    if datasets_archive == 0:
                        return []

                    if task.name == "__dtv":
                        products = task_product_query(task.id)
                        if len(products) == 0:
                            raise TaskProductArchiveFailed(task)

                        for product in products:
                            if product["product"]["errors"]:
                                raise TaskProductArchiveFailed(task)

                    return task_wait_dataset(id)

                return []

            if task.status == "failed":
                raise TaskFailed(task)
        else:
            raise TaskInvalidState()

        time.sleep(wait)


def task_rerun(task_id, remove_date=None, auth=None):
    """Reset a task's status back to "requested" so amaretti's scheduler
    re-executes it -- `PUT /task/rerun/:task_id`. No client (neither this
    library nor the Node `bl` CLI) exposed this before; found by reading
    amaretti's actual server source (api/controllers/task.js), the same way
    every other undocumented endpoint in this library was found.

    Retrying the *specific* task that actually failed (often a validator/
    archiver sub-task, found via a failed dataset's own `prov.task_id` --
    see dataset_query(task=...)) is far cheaper than resubmitting an entire
    app_run() from scratch, since it skips re-running whatever already
    finished successfully upstream.

    Known gap this does NOT solve: dataset finalization on a task rerun is
    an internal amaretti->warehouse callback (POST/PUT /dataset, gated behind
    a service-only secret, not a normal user JWT) -- if a dataset object
    already exists in a "failed" state for this task, a successful rerun can
    complete without ever updating that dataset to "stored". Always verify
    the dataset itself reached "stored" after a rerun, not just that the task
    reports "finished" -- see classify_task_failure() and the
    braise-task-recover skill's retry-then-fallback-to-full-resubmission
    logic, which exists specifically because of this gap.
    """
    data = {}
    if remove_date is not None:
        data["remove_date"] = remove_date

    res = requests.put(
        services["amaretti"] + f"/task/rerun/{task_id}",
        json=data,
        headers=auth_header(auth),
    )
    api_error(res)
    return res.json()


TRANSIENT_FAILURE_PATTERNS = (
    "no resource currently available",
    "mkdir",
    "timeout",
    "timed out",
    "econnreset",
    "econnrefused",
    "enospc",
    "no space left",
    "disk",
    "connection reset",
    "connection refused",
    # rsync/SSH connection drops mid-transfer -- confirmed live, twice,
    # independently, both during a reported Jetstream (brainlife.io's compute
    # resource) instability window. Narrowly targets connection loss, not
    # rsync failures in general -- a real rsync error (bad permissions, quota
    # exceeded) produces different text than these and is correctly left
    # unclassified as transient.
    "rsync error",
    "connection unexpectedly closed",
    "broken pipe",
    "connection closed by",
)


def classify_task_failure(status_msg: str) -> bool:
    """Best-effort classification of a task's status_msg: does this look like
    a transient infrastructure hiccup (storage/network/scheduling), worth
    retrying, or something else (a real bug, bad input, a genuine computation
    error) that a retry cannot fix and should be surfaced immediately instead?
    Deliberately conservative -- an unrecognized message is treated as NOT
    transient, since retrying a real failure wastes time and risks masking
    an actual problem rather than fixing a fluke.
    """
    if not status_msg:
        return False
    lowered = status_msg.lower()
    return any(pattern in lowered for pattern in TRANSIENT_FAILURE_PATTERNS)


def task_product_query(id, auth=None):
    res = requests.get(
        services["amaretti"] + "/task/product",
        params={
            "ids": [id],
        },
        headers={**auth_header(auth)},
    )
    return res.json()


def stage_datasets(instance_id, dataset_ids, auth=None):
    res = requests.post(
        services["warehouse"] + "/dataset/stage",
        json={
            "instance_id": instance_id,
            "dataset_ids": dataset_ids,
        },
        headers={**auth_header(auth)},
    )

    api_error(res)

    return Task.normalize(res.json()["task"])


def find_or_create_instance(app, project, instance_id=None, auth=None) -> Instance:
    if instance_id:
        instances = instance_query(id=instance_id, auth=auth)
        if not instances:
            raise Exception(f"Instance {instance_id} not found")
        if instances[0].config.get("removing") == True:
            raise Exception(
                f"Instance {instance_id} is being removed and cannot be used"
            )
        return instances[0]
    else:
        base_tag = ", ".join(app.tags) if app.tags else "CLI Process"
        new_instance_name = base_tag + "." + str(uuid.uuid4())
        instance = instance_create(new_instance_name, "(CLI)" + app.name, project, auth=auth)
        return instance
