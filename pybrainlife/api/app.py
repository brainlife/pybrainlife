from dataclasses import field, fields, dataclass
import json
import math
import requests
from typing import List

from pybrainlife.api.resource import resource_query

from ..cli.utils import check_missing_inputs, collect_unique_dataset_ids, compile_metadata, fetch_and_map_datatypes, find_or_create_instance, map_app_inputs, parse_file_id_and_dataset_query_id, prepare_app_config, prepare_config, prepare_inputs_and_subdirs, prepare_outputs, validate_datatype_tags
from .utils import nested_dataclass, is_id
from .datatype import datatype_query, DataType, DataTypeTag
from .api import auth_header, services
from .project import get_project_by_id
from .task import instance_query, instance_create, stage_datasets, task_run_app
from .utils import validate_branch
from .dataset import dataset_query
import math
import uuid


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

    print(res.json()["apps"])
    return res.json()["apps"] #solve in pair programming session

    # return App.normalize(res.json()["apps"])


def app_run(app_id, project_id, inputs, config, resource_id=None, tags=None,instance_id=None):
    #use default config and get that from app
    #get project
    project = get_project_by_id(project_id)
    if not project:
        raise Exception(f"Project {project_id} not found")
    
    #get app
    app = get_app_by_id(id=app_id)
    if not app:
        raise Exception(f"App {app_id} not found")

    #get config
    config = app.get("config",{})

    appBranch = app.get("github_branch", "master")
    validate_branch(app.get("github"),appBranch) #will show error if branch is not valid

    group_ids = project["group_id"]
    if(project.noPublicResource == False or project.noPublicResource == None):
        group_ids.append(1)
    
    #get datatypes 
    datatype_table = fetch_and_map_datatypes()
    id_to_app_input_table = map_app_inputs(app.inputs)

    all_dataset_ids = []    

    resolvedInputs = {}
    #process the inputs 
    for input in inputs:
        file_id, dataset_query_id = parse_file_id_and_dataset_query_id(input)
        datasets = dataset_query(id=dataset_query_id, limit=1) #limit not needed ?

        if len(datasets) == 0:
            raise Exception(f"No data object matching '{dataset_query_id}'")  
        if len(datasets) > 1:
            return Exception(f"Multiple data objects matching '{dataset_query_id}'")
        if datasets[0]['_id'] not in all_dataset_ids:
            all_dataset_ids.append(datasets[0]['_id']) #whats the need of it? 

        dataset = datasets[0]
        if dataset['status'] != "stored":
            raise ValueError(f"Input data object {input} has storage status '{dataset['status']}' and cannot be used until it has been successfully stored.")
    
        if dataset.get('removed', False) == True:
            raise ValueError(f"Input data object {input} has been removed and cannot be used.")
    
        app_input = id_to_app_input_table[file_id]
        if not app_input:
            raise Exception("This app's config does not include key '" + file_id + "'")
        if not app_input['datatype']:
            raise Exception("Given input of datatype " + datatype_table[dataset.datatype].name + " but expected " + datatype_table[app_input.datatype].name + " when checking " + input)
        
        validate_datatype_tags(file_id, input, dataset, app_input)

        resolvedInputs[file_id] = resolvedInputs.get(file_id, [])
        resolvedInputs[file_id].append(dataset)

    #check if required inputs are set 
    check_missing_inputs(app['inputs'], resolvedInputs)

    #validate instance
    instance = find_or_create_instance(app, project, instance_id)   

    config_values = prepare_app_config(app, config)

    unique_dataset_ids = collect_unique_dataset_ids(app, inputs)
    
    task = stage_datasets(instance['id'], 
                          unique_dataset_ids)

    appInputforTask, appSubDirforTask = prepare_inputs_and_subdirs(app, resolvedInputs, task)

    meta = compile_metadata(appInputforTask)
    
    app_outputs = prepare_outputs(app, tags, resolvedInputs, project_id, meta)

    prepared_config = prepare_config(config_values,task, resolvedInputs,datatype_table=datatype_table,app=app)
    # Extending the prepared_config with additional properties
    prepared_config.update({
        "_app": app["_id"],
        "_tid": task["config"]["_tid"] + 1,
        "_inputs": appInputforTask,  # Assuming app_inputs is prepared earlier
        "_outputs": app_outputs,  # Assuming app_outputs is prepared earlier
    })

    submissionParams = {
        "instance_id": instance.id,
        "gids": group_ids,
        "name": app.name.strip(),
        "service": app.github,
        "service_branch": appBranch,
        "config": prepared_config,
        "deps_config": [{
            "task": task._id,
            "subdirs": appSubDirforTask,
        }],
    }

    if resource_id:
        resource = resource_query(id=resource_id)
        if not resource:
            raise Exception(f"Resource {resource_id} not found")
        submissionParams["preferred_resource_id"] = resource
    

    task_run_app(submissionParams)
    print("Task submitted successfully")

def get_app_by_id(id):
    app = app_query(id=id)
    if not app:
        raise Exception(f"App {id} not found")
    return app[0]
