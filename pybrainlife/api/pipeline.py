import json
import requests
from typing import List, Dict, Union, overload, Optional

from dataclasses import dataclass, field as dcfield

from .app import App
from .project import Project
from .utils import nested_dataclass, api_error
from .api import auth_header, get_service

@dataclass
class RuleArchive:
    do: bool = False
    desc: str = ""

    @staticmethod
    def normalize(data: Union[Dict, "RuleArchive"]) -> "RuleArchive":
        if isinstance(data, RuleArchive):
            return data
        return RuleArchive(
            do=data.get("do", False),
            desc=data.get("desc", ""),
        )


@nested_dataclass
class Rule:
    id: str
    project: Project
    app: App
    name: str = ""
    branch: str = ""
    active: bool = False

    config: Dict = dcfield(default_factory=dict)
    stats: Dict = dcfield(default_factory=dict)

    subject_match: str = ""
    session_match: str = ""

    extra_datatype_tags: Dict = dcfield(default_factory=dict)
    input_selection: Dict = dcfield(default_factory=dict)
    input_multicount: Dict = dcfield(default_factory=dict)
    input_project_override: Dict = dcfield(default_factory=dict)
    input_subject: Dict = dcfield(default_factory=dict)
    input_session: Dict = dcfield(default_factory=dict)
    input_tags: Dict = dcfield(default_factory=dict)
    output_tags: Dict = dcfield(default_factory=dict)

    archive: Dict[str, RuleArchive] = dcfield(default_factory=dict)

    created: Optional[str] = None
    updated: Optional[str] = None

    @overload
    @staticmethod
    def normalize(data: List[Dict]) -> List["Rule"]: ...

    @overload
    @staticmethod
    def normalize(data: Dict) -> "Rule": ...

    @staticmethod
    def normalize(data: Union[Dict, List[Dict]]) -> Union["Rule", List["Rule"]]:
        if isinstance(data, list):
            return [Rule.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["project"] = Project.normalize(data["project"]) if isinstance(data.get("project"), dict) else Project(data["project"])
        data["app"] = App.normalize(data["app"]) if isinstance(data.get("app"), dict) else data.get("app")
        data["archive"] = {
            k: RuleArchive.normalize(v)
            for k, v in data.get("archive", {}).items()
        }
        data["created"] = data.get("create_date")
        data["updated"] = data.get("update_date")
        return Rule(**data)


def pipeline_query(project=None, id=None, name=None, active=None, skip=0, limit=100, auth=None) -> List[Rule]:
    query = {}
    if id:
        query["_id"] = id
    if name:
        query["name"] = {"$regex": name, "$options": "ig"}
    if project:
        query["project"] = project
    if active is not None:
        query["active"] = active

    url = get_service("warehouse") + "/rule"
    res = requests.get(
        url,
        params={
            "find": json.dumps(query),
            "populate": "app",
            "sort": "create_date",
            "skip": skip,
            "limit": limit,
        },
        headers={**auth_header(auth)},
    )

    api_error(res)

    return Rule.normalize(res.json()["rules"])


def pipeline_fetch(id, auth=None) -> Rule:
    rules = pipeline_query(id=id, auth=auth)
    if not rules:
        raise Exception(f"Rule {id} not found")
    return rules[0]
