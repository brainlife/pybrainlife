import json
from typing import Dict, Optional
import requests

host = None
services = {}
auth = None


def get_host() -> str:
    return host or "brainlife.io"


def set_host(new_host: str):
    global host, services
    host = new_host
    services = {
        "auth": f"https://{new_host}/api/auth",
        "amaretti": f"https://{new_host}/api/amaretti",
        "warehouse": f"https://{new_host}/api/warehouse",
        "events": f"wss://{new_host}/api/event",
        "main": f"https://{new_host}",
    }


set_host("brainlife.io")


def set_service(service: str, uri: str):
    global services
    services[service] = uri


def get_auth() -> Optional[str]:
    return auth


def set_auth(token: Optional[str]):
    global auth
    auth = token


def auth_header() -> Dict[str, str]:
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
    if res.status_code != 200:
        raise Exception(res.json()["message"])

    jwt = res.json()["jwt"]
    return jwt
