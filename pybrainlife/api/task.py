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
        res = requests.get(
            services["amaretti"] + "/task",
            params={
                "find": json.dumps({"_id": id}),
            },
            headers={**auth_header(auth)},
        )
        tasks = Task.normalize(res.json()["tasks"])
        if len(tasks) == 1:
            task = tasks[0]

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
