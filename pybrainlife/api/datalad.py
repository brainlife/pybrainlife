from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

from .utils import is_id, nested_dataclass, hydrate
from .api import auth_header, services
import requests
import json

def dl_dataset_fetch(id: str) -> Optional["DLDataset"]:
    dataset = dl_datasets_query(id=id)
    if len(dataset) == 0:
        return None
    return dataset[0]


def dl_datasets_query(
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
) -> List["DLDataset"]:
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


def dl_import_dataset(
    id: str,
    project: str,
    datatypes: List[str]
):
    url = services['warehouse'] + '/datalad/import/' + id

    res = requests.post(url, json={"project": project, "datatypes": datatypes}, headers={**auth_header()})

    if res.status_code != 200:
        raise Exception(res.json()["message"])

    return res.json()

def dl_dataset_query_item(id: str) -> "DLItem":
    url = services['warehouse'] + '/datalad/items/'
    find = json.dumps({"dldataset": id})
    select = 'dataset.meta.subject dataset.meta.session dataset.desc dataset.datatype dataset.datatype_tags dataset.tags',
    res = requests.get(url, params={"find": find,
                                    "select": select,
                                    "limit": 1,
                                    
    }, headers={**auth_header()})

# [
#     {
#         "_id": "6515f5bf257c5492c2828c56",
#         "dataset": {
#             "datatype": "594c0325fa1d2e5a1f0beda5",
#             "datatype_tags": [],
#             "meta": {
#                 "subject": "M2001",
#                 "session": "a1236"
#             },
#             "desc": "sub-M2001_ses-a1236_T2w.nii",
#             "tags": []
#         }

    if res.status_code != 200:
        raise Exception(res.json()["message"])
    return DLItem.normalize(res.json())


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

@hydrate(dl_dataset_fetch)
@nested_dataclass
class DLDataset:
    id: str
    path: str
    commit_id: str
    version: str
    dataset_description: DatasetDescription
    participants: List[Dict[str, Any]]
    stats: Stats
    import_count: int
    create_date: datetime
    removed: bool

    @staticmethod
    def normalize(data):
        if isinstance(data, list):
            return [DLDataset.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["version"] = data["__v"]
        data["dataset_description"] = DatasetDescription.normalize(data["dataset_description"])
        data["stats"] = Stats.normalize(data["stats"])
        data["create_date"] = data["create_date"]
        return DLDataset(**data)

@dataclass
class DatasetMeta:
    subject: str
    session: str


@dataclass
class Dataset:
    datatype: str
    datatype_tags: List[str]
    meta: DatasetMeta
    desc: str
    tags: List[str]


@dataclass
class DLItem:
    id: str
    dataset: Dataset

    @staticmethod
    def normalize(data: Dict[str, Any]) -> "DLItem":
        if isinstance(data, list):
            return [DLItem.normalize(d) for d in data]
        
        dataset = data['dataset']
        meta = dataset['meta']
        
        return DLItem(
            id=data['_id'],
            dataset=Dataset(
                datatype=dataset['datatype'],
                datatype_tags=dataset.get('datatype_tags', []),
                meta=DatasetMeta(subject=meta['subject'], session=meta['session']),
                desc=dataset['desc'],
                tags=dataset.get('tags', [])
            )
        )