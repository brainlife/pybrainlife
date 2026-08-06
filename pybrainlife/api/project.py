import json
import requests
from typing import List, Dict, Union, overload

from dataclasses import dataclass

from .utils import nested_dataclass, is_id, hydrate, api_error
from .api import auth_header, get_service, refresh


def project_query(id=None, ids=None, name=None, search=None, skip=0, limit=100, auth=None):
    query = {}
    if search:
        if is_id(search):
            query["_id"] = search
        else:
            query["name"] = {"$regex": search, "$options": "ig"}
    else:
        if id:
            query["_id"] = id
        if ids:
            query["_id"] = {"$in": ids}
        if name:
            query["name"] = {"$regex": name, "$options": "ig"}

    query["removed"] = False

    url = get_service("warehouse") + "/project"
    res = requests.get(
        url,
        params={
            "find": json.dumps(query),
            "sort": "name",
            "skip": skip,
            "limit": limit,
        },
        headers={**auth_header(auth)},
    )

    api_error(res)

    return Project.normalize(res.json()["projects"])


def project_fetch(project_id, auth=None):
    projects = project_query(id=project_id, auth=auth)
    if not projects:
        raise Exception(f"Project {project_id} not found")
    return projects[0]


def project_nfetch(ids, auth=None):
    projects = project_query(ids=ids, auth=auth)
    if not projects:
        raise Exception(f"Projects {ids} not found")
    return {
        project.id: project for project in projects
    }


@dataclass
class ProjectStatsDatasets:
    participants: int = 0
    objects: int = 0
    size: float = 0

    @staticmethod
    def normalize(data: Union[Dict, List[Dict]]) -> Union["ProjectStatsDatasets", List["ProjectStatsDatasets"]]:
        if isinstance(data, list):
            return [ProjectStatsDatasets.normalize(d) for d in data]
        data = {
            "participants": data.get("subject_count", 0),
            "objects": data.get("count", 0),
            "size": data.get("size", 0),
        }
        return ProjectStatsDatasets(**data)


@dataclass
class ProjectStats:
    datasets: ProjectStatsDatasets

    @staticmethod
    def normalize(data: Union[Dict, List[Dict]]) -> Union["ProjectStats", List["ProjectStats"]]:
        if isinstance(data, list):
            return [ProjectStats.normalize(d) for d in data]
        data = {
            "datasets": ProjectStatsDatasets.normalize(data["datasets"]),
        }
        return ProjectStats(**data)


@hydrate(project_fetch, project_nfetch)
@nested_dataclass
class Project:
    id: str
    name: str
    description: str
    group: int

    stats: ProjectStats

    creator: str
    admins: List[str]
    members: List[str]
    guests: List[str]
    removed: bool = False
    has_public_resource: bool = False

    @overload
    @staticmethod
    def normalize(data: List[Dict]) -> List["Project"]: ...

    @overload
    @staticmethod
    def normalize(data: Dict) -> "Project": ...

    @staticmethod
    def normalize(data: Union[Dict, List[Dict]]) -> Union["Project", List["Project"]]:
        if isinstance(data, list):
            return [Project.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["group"] = data["group_id"]
        data["description"] = data.get("desc", "")
        data["has_public_resource"] = not data.get("noPublicResource", False)
        data["stats"] = ProjectStats.normalize(data["stats"])
        data["creator"] = data["user_id"]
        return Project(**data)


def project_create(name, description=None, group=None, auth=None):
    data = {
        "name": name,
        "desc": description,
    }
    if group is not None:
        data["group_id"] = group

    url = get_service("warehouse") + "/project"
    res = requests.post(
        url,
        json=data,
        headers={**auth_header(auth)},
    )

    api_error(res)

    project = Project.normalize(res.json())

    # Project creation adds the caller to a new group; that membership only
    # shows up in a freshly issued JWT. Refresh now so this project's group is
    # usable immediately in a following call (e.g. creating a task instance
    # to upload into it) -- see api.refresh()'s docstring for why.
    refresh(auth=auth)

    return project


def project_delete(id, auth=None):
    url = get_service("warehouse") + "/project/" + id
    res = requests.delete(
        url,
        headers={**auth_header(auth)},
    )
    api_error(res)
