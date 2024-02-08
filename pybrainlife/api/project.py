import json
import requests
from typing import List

from .utils import nested_dataclass, is_id, hydrate, api_error
from .api import auth_header, services


def get_project_by_id(project_id):
    projects = project_query(id=project_id)
    if not projects:
        raise Exception(f"Project {project_id} not found")
    return projects[0]


@hydrate(get_project_by_id)
@nested_dataclass
class Project:
    id: str
    name: str
    description: str
    group: int

    admins: List[str]
    members: List[str]
    guests: List[str]
    removed: bool = False
    has_public_resource: bool = False

    @staticmethod
    def normalize(data):
        if isinstance(data, list):
            return [Project.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["group"] = data["group_id"]
        data["description"] = data["desc"]
        data["has_public_resource"] = not data.get("noPublicResource", False)
        return Project(**data)


def project_query(id=None, name=None, search=None, skip=0, limit=100):
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

    url = services["warehouse"] + "/project"
    res = requests.get(
        url,
        params={
            "find": json.dumps(query),
            "sort": "name",
            "skip": skip,
            "limit": limit,
        },
        headers={**auth_header()},
    )

    api_error(res)

    return Project.normalize(res.json()["projects"])


def project_create(name, description=None, group=None):
    data = {
        "name": name,
        "desc": description,
    }
    if group is not None:
        data["group_id"] = group

    url = services["warehouse"] + "/project"
    res = requests.post(
        url,
        json=data,
        headers={**auth_header()},
    )

    api_error(res)

    return Project.normalize(res.json())


def project_delete(id):
    url = services["warehouse"] + "/project/" + id
    res = requests.delete(
        url,
        headers={**auth_header()},
    )
    api_error(res)
