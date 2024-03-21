from dataclasses import field as dcfield
import json
import requests
from typing import List, Dict, Union, overload

from .utils import nested_dataclass, api_error
from .resource import resource_query
from .datatype import datatype_query, DataType, DataTypeTag
from .dataset import Dataset
from .api import auth_header, services
from .project import project_fetch
from .task import (
    find_or_create_instance,
    stage_datasets,
    task_run_app,
)
from .utils import validate_branch, hydrate
from .dataset import dataset_query
from typing import List


PUBLIC_RESOURCES_GID = 1


def _prepare_config(values, download_task, inputs, datatypes, app):
    id_to_app_input_table = {input.field: input for input in app.inputs}
    result = {}

    for key, config in app.config.items():
        if config["type"] == "input":
            input_id = config["input_id"]
            user_inputs = inputs.get(input_id, [])
            if not user_inputs:
                continue
            app_input = id_to_app_input_table[input_id]
            if getattr(app_input, "multi", False):
                result[key] = result.get(key, [])
                for u_input in user_inputs:
                    dtype = datatypes[u_input.datatype]
                    id_to_file = {file.id: file for file in dtype.files}
                    input_dtype_file = id_to_file.get(config["file_id"])
                    if input_dtype_file:
                        filepath = f"../{download_task['_id']}/{u_input['_id']}/{input_dtype_file.filename or input_dtype_file.dirname}"
                        result[key].append(filepath)
            else:
                dtype = datatypes[user_inputs[0].datatype.id]
                id_to_file = {file.id: file for file in dtype.files}
                input_dtype_file = id_to_file.get(config["file_id"])
                if input_dtype_file:
                    filepath = f"../{download_task['_id']}/{user_inputs[0]['_id']}/{input_dtype_file.filename or input_dtype_file.dirname}"
                    result[key] = filepath
        else:
            result[key] = values.get(key, config.get("default", None))

    return result


def _prepare_outputs(app, opt_tags, inputs, project_id, meta):
    app_outputs = []
    for output in app.outputs:
        output_req = {
            "id": output.id,
            "datatype": output.datatype.id,
            "desc": getattr(output, "desc", app.name),
            "tags": opt_tags,
            "meta": meta,
            "archive": {"project": project_id, "desc": f"{output.id} from {app.name}"},
        }

        if hasattr(output, "output_on_root") and output.output_on_root:
            output_req["files"] = getattr(output, "files", [])
        else:
            output_req["subdir"] = output.id

        tags = []
        if hasattr(output, "datatype_tags_pass"):
            input_datasets = inputs.get(getattr(output, "datatype_tags_pass", ""), [])
            for dataset in input_datasets:
                if dataset and hasattr(dataset, "datatype_tags"):
                    tags.extend([repr(t) for t in dataset.datatype_tags])
                if dataset:
                    output_req["meta"].update(dataset.meta)

        tags.extend([repr(t) for t in output.datatype_tags])

        output_req["datatype_tags"] = list(set(tags))

        app_outputs.append(output_req)
    return app_outputs


def _compile_metadata(app_inputs):
    meta = {}
    for dataset in app_inputs:
        for k in ["subject", "session", "run"]:
            if k not in meta and k in dataset.get("meta", {}):
                meta[k] = dataset["meta"][k]
    return meta


def _validate_datatype_tags(field: str, dataset: Dataset, app_input: "AppInputField"):
    user_input_tags = set(dataset.datatype_tags)

    for tag in app_input.datatype_tags:
        tag = str(tag).strip()
        if tag.startswith("!"):
            required_absent_tag = tag[1:]
            if required_absent_tag in user_input_tags:
                raise ValueError(
                    f'This app requires that the input data object for "{field}" should NOT have datatype tag "{required_absent_tag}" but found it in "{dataset.id}".'
                )
        else:
            if tag not in user_input_tags:
                raise ValueError(
                    f'This app requires that the input data object for "{field}" have datatype tag "{tag}", but it is not set on "{dataset.id}".'
                )


def _check_missing_inputs(app_inputs, resolved_inputs):
    """
    Check for any required inputs that are missing.

    Parameters:
    - app_inputs: A list of app input objects.
    - provided_inputs: A dictionary of inputs provided, keyed by input id.

    Raises:
    - ValueError: If any required inputs are missing.
    """

    missing_inputs = [
        input_field.id
        for input_field in app_inputs
        if not input_field.optional and input_field.field not in resolved_inputs
    ]
    if missing_inputs:
        missing_input_ids = ", ".join(input for input in missing_inputs)
        raise ValueError(f"some required inputs are missing: {missing_input_ids}")


def _prepare_app_config(app, user_options):
    values = {}
    for key in app.config:
        app_param = app.config[key]
        user_param = user_options.get("config", {}).get(key)

        if app_param["type"] != "input":
            if user_param is None:
                user_param = app_param.get("default")
            values[key] = user_param

    return values


def _collect_unique_dataset_ids(app, inputs):
    dataset_ids = []
    if isinstance(inputs, set):
        inputs_dict = {}
        for item in inputs:
            key, value = item.split(":")
            inputs_dict[key.strip()] = value.strip()
    else:
        inputs_dict = inputs

    for input_field in app.inputs:
        if input_field.field in inputs_dict:
            dataset_id = inputs_dict[input_field.field]
            dataset_ids.append(dataset_id)

    dataset_ids = list(set(dataset_ids))
    return dataset_ids


def _prepare_inputs_and_subdirs(app, inputs, task):
    subdirs = []
    app_inputs = []

    for input in app.inputs:
        keys = [
            key
            for key, value in app.config.items()
            if value.get("input_id") == input.id
        ]

        if input.id in inputs:
            for user_input in inputs[input["id"]]:
                dataset = next(
                    (
                        output
                        for output in task["config"]["_outputs"]
                        if output["dataset_id"] == user_input["_id"]
                    ),
                    None,
                )
                if dataset:
                    app_inputs.append(
                        {
                            **dataset,
                            "id": input["id"],
                            "task_id": task["_id"],
                            "keys": keys,
                        }
                    )

                    if "includes" in input:
                        for include in input["includes"].split("\n"):
                            subdirs.append(f"include:{dataset['id']}/{include}")
                    else:
                        subdirs.append(dataset["id"])

    return app_inputs, subdirs


def app_query(
    id=None, name=None, inputs=None, outputs=None, doi=None, skip=0, limit=100,
    auth=None
) -> List["App"]:
    query = {}
    if id:
        query["_id"] = id
    if name:
        query["name"] = {"$regex": name, "$options": "ig"}

    and_queries = []

    if inputs:
        input_datatypes = [datatype_query(name=datatype, auth=auth) for datatype in inputs]
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
        output_datatypes = [datatype_query(name=datatype, auth=auth) for datatype in outputs]
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
        headers={**auth_header(auth)},
    )

    api_error(res)

    return App.normalize(res.json()["apps"])


def app_fetch(id, auth=None) -> "App":
    apps = app_query(id=id, auth=auth)
    if not apps or len(apps) == 0:
        raise Exception(f"App {id} not found")
    app = apps[0]
    return app


@nested_dataclass
class AppField:
    id: str
    field: str
    datatype: DataType
    datatype_tags: List[DataTypeTag] = dcfield(default_factory=list)

    @overload
    @staticmethod
    def normalize(data: List[Dict]) -> List["AppField"]: ...

    @overload
    @staticmethod
    def normalize(data: Dict) -> "AppField": ...

    @staticmethod
    def normalize(data: Union[Dict, List[Dict]]) -> Union["AppField", List["AppField"]]:
        if isinstance(data, list):
            return [AppField.normalize(d) for d in data]
        data["field"] = data["id"]
        data["id"] = data["_id"]
        data["datatype_tags"] = [
            DataTypeTag.normalize(datatype_tag)
            for datatype_tag in data["datatype_tags"]
        ]
        return AppField(**data)


@nested_dataclass
class AppInputField(AppField):
    optional: bool = False
    multi: bool = False
    advanced: bool = False

    @overload
    @staticmethod
    def normalize(data: List[Dict]) -> List["AppInputField"]: ...

    @overload
    @staticmethod
    def normalize(data: Dict) -> "AppInputField": ...

    @staticmethod
    def normalize(
        data: Union[Dict, List[Dict]]
    ) -> Union["AppInputField", List["AppInputField"]]:
        if isinstance(data, list):
            return [AppInputField.normalize(d) for d in data]

        info = AppField.normalize(data).__dict__
        info["optional"] = info.get("optional", False)
        info["multi"] = info.get("multi", False)
        info["advanced"] = info.get("advanced", False)
        return AppInputField(**info)


@nested_dataclass
class AppOutputField(AppField):
    output_on_root: bool = False
    archive: bool = True

    @overload
    @staticmethod
    def normalize(data: List[Dict]) -> List["AppOutputField"]: ...

    @overload
    @staticmethod
    def normalize(data: Dict) -> "AppOutputField": ...

    @staticmethod
    def normalize(
        data: Union[Dict, List[Dict]]
    ) -> Union["AppOutputField", List["AppOutputField"]]:
        if isinstance(data, list):
            return [AppOutputField.normalize(d) for d in data]

        info = AppField.normalize(data).__dict__
        info["archive"] = info.get("archive", False)
        info["output_on_root"] = info.get("output_on_root", False)
        return AppOutputField(**info)


@hydrate(app_fetch)
@nested_dataclass
class App:
    id: str
    name: str
    description: str

    inputs: List[AppInputField]
    outputs: List[AppOutputField]
    config: dict
    github_branch: str
    github: str
    tags: List[str]

    @overload
    @staticmethod
    def normalize(data: List[Dict]) -> List["App"]: ...

    @overload
    @staticmethod
    def normalize(data: Dict) -> "App": ...

    @staticmethod
    def normalize(data: Union[Dict, List[Dict]]) -> Union["App", List["App"]]:
        if isinstance(data, list):
            return [App.normalize(d) for d in data]
        data["id"] = data["_id"]
        data["description"] = data["desc"]
        data["inputs"] = AppInputField.normalize(data["inputs"])
        data["outputs"] = AppOutputField.normalize(data["outputs"])
        data["config"] = data["config"]
        data["github_branch"] = data["github_branch"]
        data["github"] = data["github"]
        return App(**data)


def app_run(
    app_id, project_id, inputs, config, resource_id=None, tags=None, instance_id=None,
    auth=None
):
    project = project_fetch(project_id)
    if not project:
        raise Exception(f"Project {project_id} not found")

    app: App = app_fetch(id=app_id, auth=auth)
    if not app:
        raise Exception(f"App {app_id} not found")

    app_branch = app.github_branch
    validate_branch(app.github, app_branch)

    group_ids = [project.group]
    if project.has_public_resource:
        group_ids.append(PUBLIC_RESOURCES_GID)

    datatypes = datatype_query(
        ids=[input.datatype.id for input in app.inputs], limit=len(app.inputs), auth=auth
    )
    datatypes = {d.id: d for d in datatypes}
    app_inputs = {input.field: input for input in app.inputs}

    referenced_datasets = [id for id in inputs.values()]
    datasets = dataset_query(ids=referenced_datasets, limit=len(referenced_datasets), auth=auth)
    datasets = {d.id: d for d in datasets}

    resolved_inputs = {}
    for field, dataset_id in inputs.items():

        dataset = datasets.get(dataset_id)
        if not dataset:
            raise Exception(f"No dataset with ID '{dataset_id}'")

        if dataset.status != "stored":
            raise ValueError(
                f'Input data object {field}: {dataset_id} has storage status "{dataset.status}" and cannot be used until it has been successfully stored.'
            )

        if dataset.removed == True:
            raise ValueError(
                f"Input data object {field}: {dataset_id} has been removed and cannot be used."
            )

        app_input = app_inputs[field]
        if not app_input:
            raise Exception(f'This app\'s config does not include "{field}"')

        if dataset.datatype.id != app_input.datatype.id:
            raise Exception(
                f"Given input of datatype {datatypes[dataset.datatype.id].name} but "
                f"expected {datatypes[app_input.datatype.id].name} when checking "
                f"{field}: {dataset_id}"
            )

        _validate_datatype_tags(field, dataset, app_input)

        resolved_inputs[field] = resolved_inputs.get(field, [])
        resolved_inputs[field].append(dataset)

    _check_missing_inputs(app.inputs, resolved_inputs)

    instance = find_or_create_instance(app, project, instance_id)
    unique_dataset_ids = _collect_unique_dataset_ids(app, inputs)
    task = stage_datasets(instance.id, unique_dataset_ids)

    app_input_for_task, app_subdir_for_task = _prepare_inputs_and_subdirs(
        app, resolved_inputs, task
    )

    meta = _compile_metadata(app_input_for_task)
    app_outputs = _prepare_outputs(app, tags, resolved_inputs, project_id, meta)

    config = app.config
    config_values = _prepare_app_config(app, config)
    prepared_config = _prepare_config(
        config_values, task, resolved_inputs, datatypes=datatypes, app=app
    )
    prepared_config.update(
        {
            "_app": app.id,
            "_tid": task.config["_tid"] + 1,
            "_inputs": app_input_for_task,
            "_outputs": app_outputs,
        }
    )

    submission_params = {
        "instance_id": instance.id,
        "gids": group_ids,
        "name": app.name.strip(),
        "service": app.github,
        "service_branch": app_branch,
        "config": prepared_config,
        "deps_config": [
            {
                "task": task.id,
                "subdirs": app_subdir_for_task,
            }
        ],
    }

    if resource_id:
        resource = resource_query(id=resource_id, auth=auth)
        if not resource:
            raise Exception(f"Resource {resource_id} not found")
        submission_params["preferred_resource_id"] = resource

    task = task_run_app(submission_params)
