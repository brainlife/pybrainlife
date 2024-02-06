import json
from typing import List, Optional
from dataclasses import field
import requests
from datetime import datetime

from .api import auth_header, services
from .utils import is_id, nested_dataclass, hydrate

from typing import List
from .project import Project
from .datatype import DataType, DataTypeTag


def dataset_query(
    id=None, datatype=None, datatype_tags=None, tags=None,
    project=None, publication=None, metadata=None,
    search=None, task=None, skip=0, limit=100
) -> List['Dataset']:

    query = {}

    if search:
        if is_id(search):
            query["_id"] = search
        else:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "ig"}},
                {"desc": {"$regex": search, "$options": "ig"}},
            ]
    else:
        if id:
            query["_id"] = id

    if datatype:
        query["datatype"] = datatype.id

    if tags:
        pos_tags = [t.name for t in tags if not t.negate]
        neg_tags = [t.name for t in tags if t.negate]

        query["tags"] = {}

        if pos_tags:
          query["tags"]["$all"] = pos_tags
        if neg_tags:
          query["tags"]["$nin"] = neg_tags

    if datatype_tags:
        pos_tags = [t.name for t in datatype_tags if not t.negate]
        neg_tags = [t.name for t in datatype_tags if t.negate]

        query["datatype_tags"] = {}

        if pos_tags:
          query["datatype_tags"]["$all"] = pos_tags
        if neg_tags:
          query["datatype_tags"]["$nin"] = neg_tags

    if project:
        query["project"] = project.id

    if publication:
        query["publications"] = publication

    if task:
        query['prov.task_id'] = task

    if metadata:
        for k, v in metadata.items():
            query["meta." + k] = v

    url = services["warehouse"] + "/dataset"
    res = requests.get(
        url,
        params={
            "find": json.dumps(query),
            "skip": skip,
            "limit": limit,
        },
        headers={**auth_header()},
    )

    if res.status_code == 404:
        return []

    if res.status_code != 200:
        raise Exception(res.json()["message"])

    return Dataset.normalize(res.json()["datasets"])


def dataset_fetch(id) -> Optional['Dataset']:
    datasets = dataset_query(id=id, limit=1)
    if len(datasets) == 0:
        return None
    return datasets[0]


@hydrate(dataset_fetch)
@nested_dataclass
class Dataset:
    id: str
    project: Project
    datatype: DataType

    datatype_tags: List[DataTypeTag]
    tags: List[DataTypeTag]

    description: str
    storage: str
    size: Optional[int]

    status: str
    created_at: datetime
    removed: bool

    metadata: dict = field(default_factory=dict)

    @staticmethod
    def normalize(data):
        if isinstance(data, list):
            return [Dataset.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["description"] = data["desc"]
        data["metadata"] = data["meta"]
        data["datatype"] = DataType.normalize(data["datatype"])
        data["datatype_tags"] = DataTypeTag.normalize(data["datatype_tags"])
        data["tags"] = DataTypeTag.normalize(data["tags"])
        data["created_at"] = data["create_date"]
        data["size"] = data.get("size", None)
        return Dataset(**data)
