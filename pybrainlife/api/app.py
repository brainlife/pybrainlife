from dataclasses import field, fields, dataclass
import json
import requests
from typing import List

from .utils import nested_dataclass
from .datatype import datatype_query, DataType, DataTypeTag
from .api import auth_header, services


@nested_dataclass
class AppField:
    id: str
    field: str
    datatype: DataType
    datatype_tags: List[DataTypeTag]

    @staticmethod
    def normalize(data):
        if isinstance(data, list):
            return [AppOutputField.normalize(d) for d in data]
        data["field"] = data["id"]
        data["id"] = data["_id"]
        data["datatype_tags"] = [
            DataTypeTag.normalize(datatype_tag)
            for datatype_tag in data["datatype_tags"]
        ]
        return data


class AppInputField(AppField):
    optional: bool
    multi: bool
    advanced: bool


class AppOutputField(AppField):
    output_on_root: bool
    archive: bool


@nested_dataclass
class App:
    id: str
    name: str
    description: str

    inputs: List[AppInputField]
    outputs: List[AppOutputField]

    @staticmethod
    def normalize(data):
        if isinstance(data, list):
            return [App.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["description"] = data["desc"]
        data["inputs"] = AppInputField.normalize(data["inputs"])
        data["outputs"] = AppInputField.normalize(data["outputs"])
        return App(**data)


def app_query(
    id=None, name=None, inputs=None, outputs=None, doi=None, skip=0, limit=100
):
    query = {}
    if id:
        query["_id"] = id
    if name:
        query["name"] = {"$regex": name, "$options": "ig"}

    and_queries = []

    if inputs:
        input_datatypes = [datatype_query(name=datatype) for datatype in inputs]
        input_datatypes = [
            datatype[0].id if len(datatype) > 0 else None
            for datatype in input_datatypes
        ]

        if len(input_datatypes) != len(inputs):
            invalid_datatypes = [
                datatype
                for datatype, input_datatype in zip(inputs, input_datatypes)
                if input_datatype is None
            ]
            raise Exception(f"Invalid input datatypes: {invalid_datatypes}")

        and_queries += [
            {
                "inputs": {"$elemMatch": {"datatype": datatype}}
                for datatype in input_datatypes
            }
        ]

    if outputs:
        output_datatypes = [datatype_query(name=datatype) for datatype in outputs]
        output_datatypes = [
            datatype[0].id if len(datatype) > 0 else None
            for datatype in output_datatypes
        ]

        if len(output_datatypes) != len(outputs):
            invalid_datatypes = [
                datatype
                for datatype, output_datatype in zip(outputs, output_datatypes)
                if output_datatype is None
            ]
            raise Exception(f"Invalid output datatypes: {invalid_datatypes}")

        and_queries += [
            {
                "outputs": {"$elemMatch": {"datatype": datatype}}
                for datatype in output_datatypes
            }
        ]

    if and_queries:
        query["$and"] = and_queries

    if doi:
        query["doi"] = doi

    url = services["warehouse"] + "/app"
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
        return None

    if res.status_code != 200:
        raise Exception(res.json()["message"])

    return App.normalize(res.json()["apps"])


def app_run():
    pass
