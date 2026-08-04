import os
from typing import Dict, Optional
import requests

from .utils import api_error


host = None
services = {}
auth = None


def get_host() -> str:
    return host or "brainlife.io"


def set_host(new_host: str):
    global host, services
    host = new_host
    services.update({
        "auth": f"https://{new_host}/api/auth",
        "amaretti": f"https://{new_host}/api/amaretti",
        "warehouse": f"https://{new_host}/api/warehouse",
        "events": f"wss://{new_host}/api/event",
        "main": f"https://{new_host}",
    })


set_host("brainlife.io")


def get_service(service: str) -> str:
    global services
    return services[service]


def set_service(service: str, uri: str):
    global services
    services[service] = uri


def get_auth() -> Optional[str]:
    return auth


def set_auth(token: Optional[str]):
    global auth
    auth = token


def auth_header(ephemeral_auth=None) -> Dict[str, str]:
    if ephemeral_auth:
        return {"Authorization": "Bearer " + ephemeral_auth}
    return {"Authorization": "Bearer " + auth} if auth else {}


def login(username, password, ldap=False, ttl=7) -> str:
    """Login to brainlife.io

    Parameters
    ----------
    username : str
        Username
    password : str
        Password
    ldap : bool, optional
        Use LDAP authentication, by default False
    ttl : int, optional
        Token time to live in days, by default 7
    """
    url = services["auth"]
    if ldap:
        url += "/ldap/auth"
    else:
        url += "/local/auth"

    res = requests.post(
        url,
        json={
            "username": username,
            "password": password,
            "ttl": 1000 * 60 * 60 * 24 * ttl,
        },
    )
    api_error(res)

    jwt = res.json()["jwt"]
    return jwt


def refresh(ttl=1, auth=None) -> str:
    """Refresh the current JWT.

    Brainlife issues group-membership claims into the JWT at login/refresh
    time, not live -- so an operation that depends on a just-added group
    (e.g. creating a task instance in a project you just created via
    project_create()) fails with "not member of the group you have
    specified" until a fresh token is obtained. The Node `bl` CLI calls its
    own equivalent (util.refresh()) right after `bl project create` for
    exactly this reason; this mirrors that, including persisting the new
    token to the same ~/.config/<host>/.jwt file the Node CLI uses, so both
    stay in sync.

    When `auth` is an explicit ephemeral token (not the global session set via
    set_auth()), only that caller's in-memory token is refreshed and
    returned -- the shared on-disk file and global auth are left untouched.
    """
    url = services["auth"] + "/refresh"
    res = requests.post(
        url,
        json={"ttl": 1000 * 60 * 60 * 24 * ttl},
        headers=auth_header(auth),
    )
    api_error(res)
    new_jwt = res.json()["jwt"]

    if auth is None:
        set_auth(new_jwt)
        jwt_path = os.path.expanduser(f"~/.config/{get_host()}/.jwt")
        os.makedirs(os.path.dirname(jwt_path), mode=0o700, exist_ok=True)
        with open(jwt_path, "w") as f:
            f.write(new_jwt)
        os.chmod(jwt_path, 0o600)

    return new_jwt
