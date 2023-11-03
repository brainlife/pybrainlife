from dataclasses import dataclass

import re
import json
from typing import List
import requests

from .api import auth_header, services
from .utils import is_id, nested_dataclass


@nested_dataclass
class DataTypeFile:
    id: str
    field: str
    name: str
    type: str
    required: bool
    ext: str = ''

    @staticmethod
    def normalize(data):
        if isinstance(data, list):
            return [DataType.normalize(d) for d in data]
        data["field"] = data["id"]
        data["id"] = data["_id"]

        if "dirname" in data:
            data["name"] = data["dirname"]
            data["type"] = "d"
        else:
            data["name"] = data["filename"]
            data["type"] = "f"

        return data


@nested_dataclass
class DataType:
    id: str
    name: str
    description: str
    files: List[DataTypeFile]
    validator: str

    @staticmethod
    def normalize(data):
        if isinstance(data, list):
            return [DataType.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["description"] = data["desc"]
        data["files"] = [
            DataTypeFile.normalize(file)
            for file in data["files"]
        ]
        return DataType(**data)


@nested_dataclass
class DataTypeTag:
    name: str
    negate: bool

    @staticmethod
    def normalize(data):
        if isinstance(data, str):
            new_data = {"name": data, "negate": False}
            if data.startswith("!"):
                new_data["name"] = data[1:]
                new_data["negate"] = True
            return new_data
        return data

    def __repr__(self):
        return ("!" if self.negate else "") + self.name


def datatype_query(id=None, name=None, search=None, skip=0, limit=100) -> List[DataType]:

    query = {}

    if search:
        if is_id(search):
            query["_id"] = search
        else:
            query["name"] = search
    else:
        if id:
            query["_id"] = id
        if name:
            query["name"] = name

    url = services["warehouse"] + "/datatype"
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

    if res.status_code == 404:
        return []

    if res.status_code != 200:
        raise Exception(res.json()["message"])
    
    return DataType.normalize(res.json()["datatypes"])

