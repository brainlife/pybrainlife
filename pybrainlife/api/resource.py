from dataclasses import field
from typing import List, Dict, Union, Any, Optional, overload
import json
import requests

from .utils import nested_dataclass, hydrate, api_error
from .api import auth_header, services


def resource_query(id=None, name=None, skip=0, limit=100):
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
        headers={**auth_header()},
    )

    api_error(res)

    return Resource.normalize(res.json()["resources"])


def resource_fetch(id) -> Optional["Resource"]:
    resources = resource_query(id=id, limit=1)
    if len(resources) == 0:
        return None
    return resources[0]


@hydrate(resource_fetch)
@nested_dataclass
class Resource:
    id: str
    user_id: str
    name: str
    admins: List[str]
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
) -> Resource:
    """
    Create a new resource in Brainlife.

    :param config: Configuration for the resource.
    :param envs: Optional key values for service execution.
    :param name: Optional name for the resource instance.
    :param avatar: Optional avatar URL.
    :param hostname: Optional hostname.
    :param services: Optional array of services with name and score.
    :param gids: Optional list of group IDs that can use this resource.
    :param active: Optional flag to set the resource as active or inactive.
    :return: A normalized Resource object.
    """
    data = {"config": config, "active": active}
    if envs:
        data["envs"] = envs
    if name:
        data["name"] = name
    if avatar:
        data["avatar"] = avatar
    if hostname:
        data["hostname"] = hostname
    if resource_services:
        data["services"] = services
    if gids:
        data["gids"] = gids

    url = services["amaretti"] + "/resource"
    res = requests.post(url, json=data, headers={**auth_header()})

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
    active: Optional[bool] = True,
):
    data = {"config": config, "active": active}
    if envs:
        data["envs"] = envs
    if name:
        data["name"] = name
    if avatar:
        data["avatar"] = avatar
    if hostname:
        data["hostname"] = hostname
    if resource_services:
        data["services"] = services
    if gids:
        data["gids"] = gids

    url = services["amaretti"] + "/resource/" + id
    res = requests.put(url, json=data, headers={**auth_header()})

    api_error(res)

    return res.json()


def resource_delete(id):
    url = services["amaretti"] + "/resource/" + id
    res = requests.delete(url, headers={**auth_header()})

    api_error(res)

    return res.json()


def find_best_resource(service: str, group_ids: List[int]) -> Optional[Resource]:
    """
    Finds the best resource to run a specified service.

    :param service: Name of the service to run (like "soichih/sca-service-life").
    :param group_ids: List of group IDs to query resources.
    :return: A dictionary containing details of the best resource.
    """
    url = services["amaretti"] + "/resource/best"
    headers = {**auth_header()}
    params = {"service": service, "gids": group_ids}
    res = requests.get(url, headers=headers, params=params)

    api_error(res)

    resource_data = res.json()
    if not resource_data["resource"]:
        return None

    return Resource.normalize(resource_data["resource"])


def test_resource_connectivity(resource_id: str) -> str:
    """
    Tests the connectivity and availability of a specific resource.

    :param resource_id: The ID of the resource to test.
    :return: The status of the resource after testing.
    """
    url = services["amaretti"] + f"/resource/test/{resource_id}"
    headers = {**auth_header()}
    res = requests.put(url, headers=headers)

    api_error(res)

    return res.json().get("status", "Unknown status")
