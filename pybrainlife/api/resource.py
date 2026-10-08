from dataclasses import field
from typing import List, Dict, Union, Any, Optional, overload
import json
import requests

from .utils import nested_dataclass, hydrate, api_error
from .api import auth_header, services


def resource_query(id=None, name=None, skip=0, limit=100, auth=None):
    query = {}
    if id:
        query["_id"] = id
    if name:
        query["name"] = {"$regex": name, "$options": "ig"}

    url = services["amaretti"] + "/resource"
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

    return Resource.normalize(res.json()["resources"])


def resource_fetch(id, auth=None) -> Optional["Resource"]:
    resources = resource_query(id=id, limit=1, auth=auth)
    if len(resources) == 0:
        return None
    return resources[0]


@hydrate(resource_fetch)
@nested_dataclass
class Resource:
    id: str
    user_id: str
    name: str
    # Optional (not just List[str] as a type -- needs an actual default): a
    # real resource document can come back with no `admins` key at all, and
    # normalize() used to require it outright via Resource(**data), the same
    # missing-field crash already found and fixed for storage/desc elsewhere.
    admins: List[str] = field(default_factory=list)
    active: bool = True
    avatar: Optional[str] = None
    citation: Optional[str] = None
    config: dict = field(default_factory=dict)
    envs: dict = field(default_factory=dict)
    gids: List[int] = field(default_factory=list)
    status: Optional[str] = None
    status_msg: Optional[str] = None
    status_update: Optional[str] = None
    lastok_date: Optional[str] = None
    stats: dict = field(default_factory=dict)
    create_date: Optional[str] = None
    update_date: Optional[str] = None

    @overload
    @staticmethod
    def normalize(data: List[Dict]) -> List["Resource"]: ...

    @overload
    @staticmethod
    def normalize(data: Dict) -> "Resource": ...

    @staticmethod
    def normalize(data: Union[Dict, List[Dict]]) -> Union["Resource", List["Resource"]]:
        if isinstance(data, list):
            return [Resource.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["admins"] = data.get("admins", [])
        return Resource(**data)


def resource_create(
    name: str,
    config: Dict[str, Any],
    envs: Optional[Dict[str, Any]] = None,
    avatar: Optional[str] = None,
    hostname: Optional[str] = None,
    resource_services: Optional[List[Dict[str, Any]]] = None,
    gids: Optional[List[int]] = None,
    active: Optional[bool] = True,
    auth=None,
) -> Resource:
    """
    Create a new resource in Brainlife.

    :param config: Configuration for the resource.
    :param envs: Optional key values for service execution.
    :param name: Optional name for the resource instance.
    :param avatar: Optional avatar URL.
    :param hostname: Optional hostname (stored under config.hostname --
        confirmed against amaretti-next's real resourceSchema, which has no
        top-level `hostname` field at all).
    :param resource_services: Optional array of {name, score} to enable on
        this resource (stored under config.services -- same reason as
        hostname; prefer resource_set_service() to add/update one app on an
        *existing* resource without re-sending the rest of `config`).
    :param gids: Optional list of group IDs that can use this resource.
    :param active: Optional flag to set the resource as active or inactive.
    :return: A normalized Resource object.
    """
    config = dict(config)
    if hostname:
        config["hostname"] = hostname
    if resource_services:
        config["services"] = resource_services

    data = {"config": config, "active": active}
    if envs:
        data["envs"] = envs
    if name:
        data["name"] = name
    if avatar:
        data["avatar"] = avatar
    if gids:
        data["gids"] = gids

    url = services["amaretti"] + "/resource"
    res = requests.post(url, json=data, headers={**auth_header(auth)})

    api_error(res)

    return Resource.normalize(res.json())


def resource_update(
    id,
    config: Optional[Dict[str, Any]] = None,
    envs: Optional[Dict[str, Any]] = None,
    avatar: Optional[str] = None,
    hostname: Optional[str] = None,
    resource_services: Optional[List[Dict[str, Any]]] = None,
    gids: Optional[List[int]] = None,
    name: Optional[str] = None,
    active: Optional[bool] = None,
    auth=None,
):
    """Update a resource -- PUT /resource/:id.

    amaretti-next's real handler does `db.Resource.update({_id}, {$set:
    req.body})`: a key *absent* from the body is left completely untouched
    server-side, but `$set` on `config` itself replaces that whole
    sub-document wholesale (config is `Schema.Types.Mixed`, no deep merge).
    So passing `config` here always overwrites every other key already
    living under the resource's `config` (hostname, ssh_public, services,
    aws creds, ...) with whatever this call's `config` (plus `hostname`/
    `resource_services` merged into it) contains -- there is no partial
    merge. To add or update a single app's score without touching anything
    else in `config`, use `resource_set_service()` instead, which always
    fetches the resource's current `config` first.

    `active` defaults to `None` (omitted from the request) rather than
    `True`, unlike resource_create() -- an update call for an unrelated
    field must never silently reactivate a resource an admin deliberately
    deactivated.
    """
    data: Dict[str, Any] = {}
    if config is not None or hostname or resource_services:
        config = dict(config or {})
        if hostname:
            config["hostname"] = hostname
        if resource_services:
            config["services"] = resource_services
        data["config"] = config
    if active is not None:
        data["active"] = active
    if envs:
        data["envs"] = envs
    if name:
        data["name"] = name
    if avatar:
        data["avatar"] = avatar
    if gids:
        data["gids"] = gids

    url = services["amaretti"] + "/resource/" + id
    res = requests.put(url, json=data, headers={**auth_header(auth)})

    api_error(res)

    return res.json()


def resource_set_service(id, name: str, score: int = 10, auth=None) -> Resource:
    """Enable (or update the score of) exactly one app on a resource,
    touching nothing else -- the safe way to do what brainlife.io's own
    "Resource > Available Service" UI does, without re-sending the entire
    resource document (ssh keys, aws_config, admins, gids, stats, ...) the
    way the browser's own edit form does on every save.

    Always fetches the resource's *current* `config` first and only replaces
    its `services` list (adding a new `{name, score}` entry, or updating the
    score of an existing one by exact name match) -- since PUT /resource/:id
    replaces the whole `config` sub-document wholesale (see resource_update()'s
    docstring), sending anything less than the full current config here would
    silently drop every other config key (ssh_public, hostname, username,
    workdir, aws creds, ...).

    A freshly fetched config's `enc_*` fields (and `aws_config.enc_credentials`)
    always come back masked as the literal `True` -- confirmed against
    amaretti-next's own mask_enc(), which every GET /resource response goes
    through. PUT's handler special-cases exactly that sentinel to mean "keep
    the real stored value" (see amaretti-next's real router.put('/:id')), so
    round-tripping a masked config here never touches or exposes any real
    secret.

    A resource's score for a given app (`config.services[].score`) is read
    by amaretti's own resource-selection algorithm (resource.js's
    score_resource()): no entry at all means this resource can't run that
    app; `score == 0` means the entry exists but is disabled ("score is set
    to 0.. not running here"); any positive score means enabled, with higher
    scores preferred when more than one resource can run the same app.

    :param id: resource id.
    :param name: the app's exact `github` field, "org/reponame" (the same
        string amaretti matches a task's service against -- see App.github
        in api/app.py).
    :param score: 0 to register the app but leave it disabled, otherwise a
        positive integer (10 is brainlife.io's own convention for "enabled,
        default preference").
    """
    resource = resource_fetch(id, auth=auth)
    if resource is None:
        raise Exception(f"Resource {id} not found")

    new_config = dict(resource.config)
    service_list = [dict(entry) for entry in (new_config.get("services") or [])]

    updated = False
    for entry in service_list:
        if entry.get("name") == name:
            entry["score"] = score
            updated = True
            break
    if not updated:
        service_list.append({"name": name, "score": score})
    new_config["services"] = service_list

    url = services["amaretti"] + "/resource/" + id
    res = requests.put(url, json={"config": new_config}, headers={**auth_header(auth)})

    api_error(res)

    return Resource.normalize(res.json())


def resource_delete(id, auth=None):
    url = services["amaretti"] + "/resource/" + id
    res = requests.delete(url, headers={**auth_header(auth)})

    api_error(res)

    return res.json()


def find_best_resource(service: str, group_ids: List[int], auth=None) -> Optional[Resource]:
    """
    Finds the best resource to run a specified service.

    :param service: Name of the service to run (like "soichih/sca-service-life").
    :param group_ids: List of group IDs to query resources.
    :return: A dictionary containing details of the best resource.
    """
    url = services["amaretti"] + "/resource/best"
    headers = {**auth_header(auth)}
    params = {"service": service, "gids": group_ids}
    res = requests.get(url, headers=headers, params=params)

    api_error(res)

    resource_data = res.json()
    if not resource_data["resource"]:
        return None

    return Resource.normalize(resource_data["resource"])


def test_resource_connectivity(resource_id: str, auth=None) -> str:
    """
    Tests the connectivity and availability of a specific resource.

    :param resource_id: The ID of the resource to test.
    :return: The status of the resource after testing.
    """
    url = services["amaretti"] + f"/resource/test/{resource_id}"
    headers = {**auth_header(auth)}
    res = requests.put(url, headers=headers)

    api_error(res)

    return res.json().get("status", "Unknown status")
