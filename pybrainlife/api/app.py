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
    """Build an input-type config key's value (a relative path string like
    "../<stage-task-id>/<dataset-id>/t1.nii.gz" that the app's own script
    reads directly). Several .id-vs-.field mixups here used to make every
    input-type key silently disappear from the submitted config with no
    error: DataTypeFile.normalize() renames the same way AppField.normalize()
    does (semantic name -> .field, internal db id -> .id), so file lookups
    keyed by `.id` never matched a config spec's `file_id` (a semantic name
    like "t1"). download_task/u_input/user_inputs[0] are Task/Dataset
    dataclass instances, not dicts, so `['_id']` subscripting also never
    worked -- and DataTypeFile has no .filename/.dirname attribute at all
    (only .name, which normalize() already resolved to whichever one applies).
    """
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
                    dtype = datatypes[u_input.datatype.id]
                    id_to_file = {file.field: file for file in dtype.files}
                    input_dtype_file = id_to_file.get(config["file_id"])
                    if input_dtype_file:
                        filepath = f"../{download_task.id}/{u_input.id}/{input_dtype_file.name}"
                        result[key].append(filepath)
            else:
                dtype = datatypes[user_inputs[0].datatype.id]
                id_to_file = {file.field: file for file in dtype.files}
                input_dtype_file = id_to_file.get(config["file_id"])
                if input_dtype_file:
                    filepath = f"../{download_task.id}/{user_inputs[0].id}/{input_dtype_file.name}"
                    result[key] = filepath
        else:
            result[key] = values.get(key, config.get("default", None))

    return result


def _prepare_outputs(app, opt_tags, inputs, project_id, meta):
    app_outputs = []
    for output in app.outputs:
        # output.field is the app's own semantic slot name (e.g. "acpc") --
        # what the app's script actually writes its output to. output.id is
        # this AppOutputField's own internal database id (renamed from the
        # raw API's "id" by AppField.normalize()), not something the running
        # container knows about. Using output.id here (as ported literally
        # from the Node CLI's bl-app-run.js, where "id" means the semantic
        # name because that JS code works on the raw unrenamed API response)
        # sends the archiver a subdir/output id the app never produces, so
        # every submission fails within under a second, before any real work
        # starts.
        output_req = {
            "id": output.field,
            "datatype": output.datatype.id,
            "desc": getattr(output, "desc", app.name),
            "tags": opt_tags,
            "meta": meta,
            "archive": {"project": project_id, "desc": f"{output.field} from {app.name}"},
        }

        if hasattr(output, "output_on_root") and output.output_on_root:
            output_req["files"] = getattr(output, "files", [])
        else:
            output_req["subdir"] = output.field

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
    # DataTypeTag has no __hash__ (a plain, unfrozen dataclass), so a set of
    # the objects themselves raises TypeError; the membership checks below
    # compare against plain tag-name strings anyway (via str(tag), which
    # DataTypeTag.__repr__ renders as "name" / "!name"), so build the set
    # from .name too.
    user_input_tags = {t.name for t in dataset.datatype_tags}

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
        input_field.field
        for input_field in app_inputs
        if not input_field.optional and input_field.field not in resolved_inputs
    ]
    if missing_inputs:
        missing_input_ids = ", ".join(input for input in missing_inputs)
        raise ValueError(f"some required inputs are missing: {missing_input_ids}")


def _prepare_app_config(app, user_config):
    """`user_config` is a flat {config_key: value} dict of caller overrides
    (see app_run()'s own `config` parameter and its usage in
    tests/test_pybrainlife_app.py, e.g. `config={"reorient": True}`) -- not
    nested under a "config" key."""
    values = {}
    for key in app.config:
        app_param = app.config[key]
        user_param = user_config.get(key)

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
    """`input` (an AppInputField) uses `.field` for the app's own semantic
    slot name (e.g. "anat") and `.id` for this field's own internal database
    id (see AppField.normalize()'s rename) -- `inputs` (== app_run()'s
    resolved_inputs) is keyed by that same semantic `.field` name, and
    `input.id` never matches one of those keys, so every branch below used to
    be dead code (masked by `if input.id in inputs` always being False). Once
    that's corrected, `input`/`task`/`user_input` also need attribute access
    instead of dict-style subscripting: they're dataclass instances (AppInputField,
    Task, Dataset respectively), not dicts, only `output` (drawn from
    `task.config["_outputs"]`, plain JSON) actually is one.
    """
    subdirs = []
    app_inputs = []

    for input in app.inputs:
        keys = [
            key
            for key, value in app.config.items()
            if value.get("input_id") == input.field
        ]

        if input.field in inputs:
            for user_input in inputs[input.field]:
                dataset = next(
                    (
                        output
                        for output in task.config["_outputs"]
                        if output["dataset_id"] == user_input.id
                    ),
                    None,
                )
                if dataset:
                    app_inputs.append(
                        {
                            **dataset,
                            "id": input.field,
                            "task_id": task.id,
                            "keys": keys,
                        }
                    )

                    if input.includes:
                        for include in input.includes.split("\n"):
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
            "sort": "-stats.requested",
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
    includes: str = ""

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

        # Read these before AppField.normalize() runs: AppField's own
        # dataclass has no optional/multi/advanced fields, so nested_dataclass's
        # __init__ silently drops them from the object it builds -- pulling
        # them back out of that object's __dict__ afterward always finds the
        # default, never the real value.
        optional = data.get("optional", False)
        multi = data.get("multi", False)
        advanced = data.get("advanced", False)
        includes = data.get("includes", "")
        info = AppField.normalize(data).__dict__
        info["optional"] = optional
        info["multi"] = multi
        info["advanced"] = advanced
        info["includes"] = includes
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

        # Same ordering issue as AppInputField.normalize above: read these
        # from the raw dict before AppField.normalize() builds an object that
        # never carried them in the first place.
        archive = data.get("archive", False)
        output_on_root = data.get("output_on_root", False)
        info = AppField.normalize(data).__dict__
        info["archive"] = archive
        info["output_on_root"] = output_on_root
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
        data["description"] = data.get("desc", "")
        data["inputs"] = AppInputField.normalize(data["inputs"])
        data["outputs"] = AppOutputField.normalize(data["outputs"])
        data["config"] = data["config"]
        data["github_branch"] = data.get("github_branch", "main")
        data["github"] = data.get("github")
        return App(**data)


def _validate_github_org_repo(github: str) -> None:
    """The warehouse `github` field is an "org/repo" pair, not a URL -- the
    brainlife.io registration form explicitly warns against pasting a full
    GitHub URL there. Catch that mistake before it reaches the server."""
    if github.startswith("http://") or github.startswith("https://") or "github.com" in github:
        raise ValueError(
            f"github={github!r} looks like a full URL. This field wants "
            "'org/repo' only (e.g. 'myorg/app-myapp'), not the full GitHub URL."
        )
    if github.count("/") != 1 or not all(github.split("/")):
        raise ValueError(f"github={github!r} must be exactly 'org/repo'.")


def app_create(
    name, github, github_branch=None, desc=None, tags=None, avatar=None,
    projects=None, admins=None, retry=None, doi=None, config=None,
    inputs=None, outputs=None, auth=None,
) -> "App":
    """Register a new brainlife app -- POST /app (see warehouse's
    api/controllers/app.js for the authoritative field list; there is no
    dedicated app-registration endpoint documented anywhere else, and neither
    this library nor the Node `bl` CLI exposed one before this).

    `inputs`/`outputs` are the raw wire-format lists this endpoint expects --
    each entry's `datatype` must already be a resolved datatype id (e.g. from
    `datatype_query(name=...)`), not a human-readable name; resolving names is
    left to the caller (see the compound/script layer for a friendlier CLI
    that does this for you). Shapes, per the warehouse Mongoose schema:
      inputs:  [{id, desc, datatype, datatype_tags[], optional, includes, multi, advanced}]
      outputs: [{id, desc, datatype, datatype_tags[], datatype_tags_pass,
                 output_on_root, files, archive}]

    Registering an app is more public than creating a project: with no
    `projects` restriction, the app is visible to everyone on brainlife.io by
    default, not just your own team.

    `github_branch`/`config`/`inputs`/`outputs` are always sent (defaulting to
    "master"/{}/[]/[] respectively) rather than left out when unset: App.normalize()
    reads all four with direct (non-.get()) dict access, matching the warehouse
    schema's own field list, so a value genuinely absent from the create
    response -- which Mongoose does not guarantee against for an unset field --
    would crash this function's own return path instead of the caller's.
    """
    _validate_github_org_repo(github)

    data = {
        "name": name,
        "github": github,
        "github_branch": github_branch or "master",
        "config": config if config is not None else {},
        "inputs": inputs if inputs is not None else [],
        "outputs": outputs if outputs is not None else [],
    }
    if desc is not None:
        data["desc"] = desc
    if tags is not None:
        data["tags"] = tags
    if avatar is not None:
        data["avatar"] = avatar
    if projects is not None:
        data["projects"] = projects
    if admins is not None:
        data["admins"] = admins
    if retry is not None:
        data["retry"] = retry
    if doi is not None:
        data["doi"] = doi

    url = services["warehouse"] + "/app"
    res = requests.post(url, json=data, headers=auth_header(auth))
    api_error(res)

    return App.normalize(res.json())


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

    # NOTE: this used to be `config = app.config` here, which clobbered the
    # caller's own `config` argument (the parameter this function was called
    # with) with the app's config *schema* before ever using it -- every
    # override the caller passed was silently discarded and only the app's
    # own defaults were ever submitted. Use the caller's config (default to
    # no overrides at all) instead.
    config_values = _prepare_app_config(app, config or {})
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
    return task
