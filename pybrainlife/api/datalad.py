from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
from .utils import is_id, nested_dataclass, hydrate
from .api import auth_header, services
import requests
import json


def dl_dataset_query(
    id: Optional[str] = None,
    path: Optional[str] = None,
    commit_id: Optional[str] = None,
    version: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    datatype: Optional[str] = None,
    datatype_tags: Optional[List[str]] = None,
    project: Optional[str] = None,
    publication: Optional[str] = None,
    metadata: Optional[str] = None,
    search: Optional[str] = None,
    task: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> List["DLItem"]:
    query = {}

    if search:
        if is_id(search):
            query["_id"] = search
        else:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "ig"}},
                {"desc": {"$regex": search, "$options": "ig"}},
            ]
    else:
        if id:
            query["_id"] = id

    if path:
        query["path"] = path

    if commit_id:
        query["commit_id"] = commit_id

    if version:
        query["version"] = version

    if name:
        query["name"] = name

    if description:
        query["description"] = description

    if tags:
        query["tags"] = {"$all": tags}

    if datatype:
        query["datatype"] = datatype

    if datatype_tags:
        query["datatype_tags"] = {"$all": datatype_tags}

    if project:
        query["project"] = project

    if publication:
        query["publication"] = publication

    if metadata:
        query["metadata"] = metadata

    if task:
        query["task"] = task

    url = services['warehouse'] + '/datalad/datasets'

    res = requests.get(url, params={"find": json.dumps(query), "skip": skip, "limit": limit},
                       headers={**auth_header()})
    
    if res.status_code == 404:
        raise []
    
    if res.status_code != 200:
        raise Exception(res.json()["message"])
    
    return DLDataset.normalize(res.json())    



class DatasetDescription:
    Name: str
    BIDSVersion: str
    License: str
    Authors: List[str]
    Acknowledgements: List[str]
    HowToAcknowledge: str
    Funding: List[str]
    ReferencesAndLinks: List[str]
    DatasetDOI: str

    @staticmethod
    def normalize(data: Dict[str, Any]) -> 'DatasetDescription':
        description = DatasetDescription()
        description.Name = data["Name"] if "Name" in data else ""
        description.BIDSVersion = data["BIDSVersion"] if "BIDSVersion" in data else ""
        description.License = data["License"] if "License" in data else ""
        description.Authors = data["Authors"] if "Authors" in data else []
        description.Acknowledgements = data["Acknowledgements"] if "Acknowledgements" in data else []
        description.HowToAcknowledge = data["HowToAcknowledge"] if "HowToAcknowledge" in data else ""
        description.Funding = data["Funding"] if "Funding" in data else []
        description.ReferencesAndLinks = data["ReferencesAndLinks"] if "ReferencesAndLinks" in data else []
        description.DatasetDOI = data["DatasetDOI"] if "DatasetDOI" in data else ""
        return description

class Stats:
    subjects: int
    sessions: int
    datatypes: Dict[str, Any]

    @staticmethod
    def normalize(data: Dict[str, Any]) -> 'Stats':
        stats = Stats()
        stats.subjects = data["subjects"]
        stats.sessions = data["sessions"]
        stats.datatypes = data["datatypes"]
        return stats

class DLDataset:
    id: str
    path: str
    commit_id: str
    version: str
    README: str
    CHANGES: str
    dataset_description: DatasetDescription
    participants: List[Dict[str, Any]]
    participants_info: Dict[str, Any]
    stats: Stats
    import_count: int
    create_date: datetime
    removed: bool

    @staticmethod
    def normalize(data):
        if isinstance(data, list):
            return [DLDataset.normalize(d) for d in data]
        print("Data received for normalization:", data)  # Add this print statement
        dataset = DLDataset()
        dataset.id = data["_id"]
        dataset.path = data["path"]
        dataset.commit_id = data["commit_id"]
        dataset.version = data["__v"]
        dataset.README = data["README"] if "README" in data else ""
        dataset.CHANGES = data["CHANGES"] if "CHANGES" in data else ""
        dataset.dataset_description = DatasetDescription.normalize(data["dataset_description"])
        dataset.participants = data["participants"]
        dataset.participants_info = data["participants_info"] if "participants_info" in data else {}
        dataset.stats = Stats.normalize(data["stats"])
        dataset.import_count = data["import_count"]
        dataset.create_date = data["create_date"]
        dataset.removed = data["removed"]
        return dataset

class DLItem:
    dldataset: DLDataset
    dataset: Dict[str, Any]
    create_date: datetime
    update_date: datetime

    @staticmethod
    def normalize(data: Dict[str, Any]) -> 'DLItem':
        item = DLItem()
        item.dldataset = DLDataset.normalize(data.get("dldataset", {}))
        item.dataset = data["dataset"]
        item.create_date = data["create_date"]
        item.update_date = data["update_date"]
        return item
