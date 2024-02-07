from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import json
import requests

from .utils import nested_dataclass
from .api import auth_header, services


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

    @staticmethod
    def normalize(data):
        if isinstance(data, list):
            return [Resource.normalize(d) for d in data]
        data["id"] = data["_id"]
        return Resource(**data)


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

    if res.status_code != 200:
        raise Exception(res.json()["message"])

    return Resource.normalize(res.json()["resources"])


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

    if res.status_code != 200:
        raise Exception(res.json()["message"])

    return Resource.normalize(res.json())


def resource_update(
    id,
    config: Dict[str, Any] = None,
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

    if res.status_code != 200:
        raise Exception(res)  # we only have error codes in the response
    return res.json()


def resource_delete(id):
    url = services["amaretti"] + "/resource/" + id
    res = requests.delete(url, headers={**auth_header()})

    if res.status_code != 200:
        raise Exception(res.json()["message"])
    return res.json()  # response is a message


def find_best_resource(service: str, groupIDs: List[int]) -> Dict[str, Any]:
    """
    Finds the best resource to run a specified service.

    :param service: Name of the service to run (like "soichih/sca-service-life").
    :param groupIDs: List of group IDs to query resources.
    :return: A dictionary containing details of the best resource.
    """
    url = services["amaretti"] + "/resource/best"
    headers = {**auth_header()}

    params = {"service": service, "gids": groupIDs}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        raise Exception(f"API request failed: {response.text}")

    resource_data = response.json()
    print(resource_data)
    resource_data["resource"] = Resource.normalize(resource_data["resource"])
    return resource_data


# Example usage
# best_resource_info = find_best_resource("your_jwt_token", "soichih/sca-service-life")
# print(best_resource_info)


def test_resource_connectivity(resource_id: str, jwt_token: str) -> str:
    """
    Tests the connectivity and availability of a specific resource.

    :param resource_id: The ID of the resource to test.
    :param jwt_token: A valid JWT token for authorization (not used here as we use auth_header()).
    :return: The status of the resource after testing.
    """
    url = services["amaretti"] + f"/resource/test/{resource_id}"
    headers = {**auth_header()}

    response = requests.put(url, headers=headers)

    if response.status_code == 200:
        return response.json().get("status", "Unknown status")
    else:
        error_message = response.json().get("message", "Error : API request failed")
        raise Exception(f"Resource test failed: {error_message}")
