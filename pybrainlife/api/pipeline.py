import json
import requests
from typing import List, Dict, Union, overload, Optional

from dataclasses import dataclass, field as dcfield

from .app import App
from .project import Project, project_fetch
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
        data["project"] = Project.normalize(data["project"]) if isinstance(data.get("project"), dict) else data["project"]
        data["app"] = App.normalize(data["app"]) if isinstance(data.get("app"), dict) else data["app"]
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


def pipeline_create(
    project: Project,
    app: App,
    name: str = "",
    config: Optional[Dict] = None,
    branch: Optional[str] = None,
    active: bool = True,
    subject_match: str = "",
    session_match: str = "",
    extra_datatype_tags: Optional[Dict] = None,
    input_selection: Optional[Dict] = None,
    input_multicount: Optional[Dict] = None,
    input_project_override: Optional[Dict] = None,
    input_subject: Optional[Dict] = None,
    input_session: Optional[Dict] = None,
    input_tags: Optional[Dict] = None,
    output_tags: Optional[Dict] = None,
    archive: Optional[Dict[str, Union[RuleArchive, Dict]]] = None,
    auth=None,
) -> Rule:
    config = config or {}

    app_config_keys = {
        key for key, spec in app.config.items() if spec.get("type") != "input"
    }
    unknown_config = set(config) - app_config_keys
    if unknown_config:
        raise ValueError(
            f"Unknown config keys for app {app.name}: {sorted(unknown_config)}. "
            f"Expected one of: {sorted(app_config_keys)}"
        )

    app_input_fields = {inp.field for inp in app.inputs}
    app_output_fields = {out.field for out in app.outputs}

    input_keyed = {
        "extra_datatype_tags": extra_datatype_tags,
        "input_selection": input_selection,
        "input_multicount": input_multicount,
        "input_tags": input_tags,
    }
    for param_name, value in input_keyed.items():
        if not value:
            continue
        unknown = set(value) - app_input_fields
        if unknown:
            raise ValueError(
                f"Unknown input fields in {param_name} for app {app.name}: "
                f"{sorted(unknown)}. Expected one of: {sorted(app_input_fields)}"
            )

    output_keyed = {
        "output_tags": output_tags,
        "archive": archive,
    }
    for param_name, value in output_keyed.items():
        if not value:
            continue
        unknown = set(value) - app_output_fields
        if unknown:
            raise ValueError(
                f"Unknown output fields in {param_name} for app {app.name}: "
                f"{sorted(unknown)}. Expected one of: {sorted(app_output_fields)}"
            )

    merged_config = {
        key: spec.get("default")
        for key, spec in app.config.items()
        if spec.get("type") != "input"
    }
    merged_config.update(config)

    normalized_archive = {
        key: {"do": ra.do, "desc": ra.desc}
        for key, ra in (
            (k, RuleArchive.normalize(v)) for k, v in (archive or {}).items()
        )
    }

    payload = {
        "project": project.id,
        "app": app.id,
        "name": name,
        "branch": branch if branch is not None else app.github_branch,
        "active": active,
        "config": merged_config,
        "subject_match": subject_match,
        "session_match": session_match,
        "extra_datatype_tags": extra_datatype_tags or {},
        "input_selection": input_selection or {},
        "input_multicount": input_multicount or {},
        "input_project_override": input_project_override or {},
        "input_subject": input_subject or {},
        "input_session": input_session or {},
        "input_tags": input_tags or {},
        "output_tags": output_tags or {},
        "archive": normalized_archive,
    }

    url = get_service("warehouse") + "/rule"
    res = requests.post(url, json=payload, headers={**auth_header(auth)})
    api_error(res)

    return Rule.normalize(res.json())


def pipeline_set_order(project: Project, group: Dict, auth=None) -> Dict:
    """PUT /rule/order/:projectId -- persists the UI's cosmetic grouping/
    ordering of rules onto `project.pipelines` (a schema-less blob server-side,
    not a dependency graph -- see build_pipeline_group()). Re-fetches the
    project first and appends `group` alongside whatever's already there,
    rather than overwriting `project.pipelines` outright: any existing
    groups/rules not touched by this call would otherwise be silently
    destroyed, since the server just replaces the whole field with whatever
    is PUT here."""
    current = project_fetch(project.id, auth=auth)
    existing = current.pipelines
    if not existing or not isinstance(existing, dict):
        root = {"type": "group", "items": []}
    else:
        root = existing
        root.setdefault("items", [])
    root["items"].append(group)

    url = get_service("warehouse") + f"/rule/order/{project.id}"
    res = requests.put(url, json=root, headers={**auth_header(auth)})
    api_error(res)
    return res.json()


def build_pipeline_group(name: str, rules: List[Rule]) -> Dict:
    """A named group of rules, in stage order, for pipeline_set_order() --
    matches the shape warehouse's own UI writes when a user manually
    reorders/groups rules (see api/controllers/rule.js's `PUT /order/:projectId`
    and the `Projects.pipelines` schema comment in warehouse's models.js)."""
    return {
        "type": "group",
        "name": name,
        "items": [{"type": "rule", "ruleId": rule.id} for rule in rules],
    }
