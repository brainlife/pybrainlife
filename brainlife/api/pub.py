from typing import List, Dict, Union, Optional, overload
import requests

from .api import auth_header, services
from .utils import nested_dataclass, api_error


def pub_query(search=None, skip=0, limit=100, auth=None) -> List["Pub"]:
    url = services["warehouse"] + "/pub/query"
    res = requests.get(
        url,
        params={
            "q": search or "",
            "select": "-readme",
            "skip": skip,
            "limit": limit,
        },
        headers={**auth_header(auth)},
    )

    api_error(res)

    return Pub.normalize(res.json()["pubs"])


def pub_fetch(id, auth=None) -> Optional["Pub"]:
    # ponytail: /pub/query is text-search only, filter client-side (~60 pubs total)
    pubs = [p for p in pub_query(auth=auth) if p.id == id or p.doi == id]
    return pubs[0] if pubs else None


@nested_dataclass
class PubVideo:
    title: str
    url: str


@nested_dataclass
class PubGroup:
    id: str
    name: str
    description: str
    videoPlaylist: List[PubVideo]
    # TODO incorporate other fields from the pub group schema (e.g. authors, tags, etc.)

    @staticmethod
    def normalize(data):
        if isinstance(data, list):
            return [PubGroup.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["description"] = data.get("desc", "")
        data["videoPlaylist"] = data.get("videoPlaylist", [])
        return PubGroup(**data)


@nested_dataclass
class Pub:
    id: str
    name: str
    description: str
    doi: Optional[str]
    license: str
    tags: List[str]
    authors: List[str]
    project: Optional[str]
    publish_date: Optional[str]
    groups: List[PubGroup]

    @overload
    @staticmethod
    def normalize(data: List[Dict]) -> List["Pub"]: ...

    @overload
    @staticmethod
    def normalize(data: Dict) -> "Pub": ...

    @staticmethod
    def normalize(data: Union[Dict, List[Dict]]) -> Union["Pub", List["Pub"]]:
        if isinstance(data, list):
            return [Pub.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["description"] = data.get("desc", "")
        data["doi"] = data.get("doi")
        data["tags"] = data.get("tags", [])
        data["authors"] = [
            a.get("fullname") or a.get("username") or a.get("_id", "")
            if isinstance(a, dict)
            else str(a)
            for a in data.get("authors", [])
        ]
        project = data.get("project")
        data["project"] = project["_id"] if isinstance(project, dict) else project
        data["publish_date"] = data.get("publish_date")
        data["groups"] = PubGroup.normalize(data.get("groups", []))
        return Pub(**data)
