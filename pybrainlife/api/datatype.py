import json
from typing import List, Dict, Union, Optional, overload
import requests

from .api import auth_header, services
from .utils import is_id, nested_dataclass, hydrate, api_error


def datatype_query(
    id=None, ids=None, name=None, search=None, skip=0, limit=100, auth=None
) -> List["DataType"]:
    query = {}

    if search:
        if is_id(search):
            query["_id"] = search
        else:
            query["name"] = search
    else:
        if id:
            query["_id"] = id
        if ids:
            query["_id"] = {"$in": ids}
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
        headers={**auth_header(auth)},
    )

    api_error(res)

    return DataType.normalize(res.json()["datatypes"])


def datatype_fetch(id, auth=None) -> Optional["DataType"]:
    datatypes = datatype_query(id=id, limit=1, auth=auth)
    if len(datatypes) == 0:
        return None
    return datatypes[0]


@nested_dataclass
class DataTypeFile:
    id: str
    field: str
    name: str
    type: str
    required: bool
    ext: str = ""

    @staticmethod
    def normalize(data):
        if isinstance(data, list):
            return [DataTypeFile.normalize(d) for d in data]
        data["field"] = data["id"]
        data["id"] = data["_id"]

        if "dirname" in data:
            data["name"] = data["dirname"]
            data["type"] = "d"
        else:
            data["name"] = data["filename"]
            data["type"] = "f"

        return data


@hydrate(datatype_fetch)
@nested_dataclass
class DataType:
    id: str
    name: str
    description: str
    files: List[DataTypeFile]
    validator: Optional[str]

    @overload
    @staticmethod
    def normalize(data: List[Dict]) -> List["DataType"]: ...

    @overload
    @staticmethod
    def normalize(data: Dict) -> "DataType": ...

    @staticmethod
    def normalize(data: Union[Dict, List[Dict]]) -> Union["DataType", List["DataType"]]:
        if isinstance(data, list):
            return [DataType.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["description"] = data["desc"]
        data["files"] = [DataTypeFile.normalize(file) for file in data["files"]]
        data["validator"] = data.get("validator")
        return DataType(**data)


@nested_dataclass
class DataTypeTag:
    name: str
    negate: bool

    @overload
    @staticmethod
    def normalize(data: List[Dict]) -> List["DataTypeTag"]: ...

    @overload
    @staticmethod
    def normalize(data: Dict) -> "DataTypeTag": ...

    @staticmethod
    def normalize(
        data: Union[Dict, List[Dict]]
    ) -> Union["DataTypeTag", List["DataTypeTag"]]:
        if isinstance(data, list):
            return [DataTypeTag.normalize(d) for d in data]
        if isinstance(data, str):
            new_data = {"name": data, "negate": False}
            if data.startswith("!"):
                new_data["name"] = data[1:]
                new_data["negate"] = True
            data = new_data
        return DataTypeTag(**data)

    def __repr__(self):
        return ("!" if self.negate else "") + self.name
