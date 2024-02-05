import os
import stat
import jwt

from pathlib import Path
from ..api.api import get_host, get_auth, set_auth
import uuid
from ..api.task import instance_query, instance_create
from ..api.datatype import datatype_query
import requests
from typing import List
home = Path.home() or ""
token_path = home / ".config" / get_host() / ".jwt"


def init_auth():
    token = load_auth("env")
    if token is None:
        token = load_auth("file")
    set_auth(token)
    return token


def get_token_path():
    return home / ".config" / get_host() / ".jwt"


def load_auth(method="env"):
    """Get authentication token"""

    if method == "file":
        path = get_token_path()
        if not path.exists():
            return
        with open(path, "r") as f:
            return f.read()
    elif method == "env":
        return os.environ.get("BL_TOKEN")

    raise ValueError("Invalid method")


def save_auth(token):
    token_path = get_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as f:
        f.write(token)
    os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)


def ensure_auth():
    token = get_auth()
    if token is None:
        raise Exception("Not authenticated")

    jwt.decode(
        token,
        options={"verify_signature": False, "verify_exp": True}
      )
    
def logged_in_user_details():
    token = get_auth()
    if token is None:
        raise Exception("Not authenticated")
    return jwt.decode(token, options={"verify_signature": False, "verify_exp": True})


def validate_branch(github_repo, branch):
    try:
        headers = {"User-Agent": "brainlife CLI"}
        response = requests.get(f'https://api.github.com/repos/{github_repo}/branches', headers=headers)
        response.raise_for_status()

        branches = response.json()
        if not any(branch == valid_branch['name'] for valid_branch in branches):
            raise ValueError(f"The given github branch ({branch}) does not exist for {github_repo}")
    except Exception as err:
        raise Exception(f"Error checking branch: {err}")
    return branch 

def find_or_create_instance(app, project, instance_id=None):
    if instance_id:
        instance = instance_query(id=instance_id)
        if not instance:
            raise Exception(f"Instance {instance_id} not found")
    else:
        new_instance_name = (app['tags'] or 'CLI Process') + "." + str(uuid.uuid4())
        instance = instance_create(new_instance_name, "(CLI)", project.id)
    
    return instance

def fetch_and_map_datatypes():
    """
    Fetches all datatypes using the given query function and maps them by their IDs.
    
    Parameters:
    - datatype_query: A function that accepts a limit parameter and returns a list of datatypes.
    
    Returns:
    - A dictionary mapping datatype IDs to datatypes.
    """
    datatypes = datatype_query(limit=0)
    datatype_table = {d['id']: d for d in datatypes}
    return datatype_table


def map_app_inputs(app_inputs):
    """
    Maps app inputs by their IDs.
    
    Parameters:
    - app_inputs: A list of app input dictionaries.
    
    Returns:
    - A dictionary mapping app input IDs to app inputs.
    """
    #using field as id is mapped as field
    id_to_app_input_table = {input.field: input for input in app_inputs}
    return id_to_app_input_table

def parse_file_id_and_dataset_query_id(input):
    """
    Parses a file ID and dataset query ID from a string.
    
    Parameters:
    - input: A string in the format "file_id:dataset_query_id".
    
    Returns:
    - A tuple containing the file ID and dataset query ID.
    """
    if ":" not in input:
        raise ValueError(f"Invalid input: {input}, No key given for dataset query. Expected format: file_id:dataset_query_id")
    file_id, dataset_query = input.split(':')
    return file_id.strip(), dataset_query.strip()

def validate_datatype_tags(file_id, input, dataset, app_input):
    """
    Validates the dataset's datatype tags against the app's input requirements.
    """
    user_input_tags = set(dataset.datatype_tags)

    for tag in app_input.datatype_tags:
        tag = str(tag).strip()
        if tag.startswith("!"):
            required_absent_tag = tag[1:]
            if required_absent_tag in user_input_tags:
                raise ValueError(f"This app requires that the input data object for {file_id} should NOT have datatype tag '{required_absent_tag}' but found it in {input}")
        else:
            if tag not in user_input_tags:
                raise ValueError(f"This app requires that the input data object for {file_id} have datatype tag '{tag}', but it is not set on {input}")

def check_missing_inputs(app_inputs, resolved_inputs):
    """
    Check for any required inputs that are missing.

    Parameters:
    - app_inputs: A list of app input objects.
    - provided_inputs: A dictionary of inputs provided, keyed by input id.

    Raises:
    - ValueError: If any required inputs are missing.
    """
    # #    #TEMP workaround for the test
    # # set optional and multi to false 
    for input in app_inputs:
        print(input)
    #     if input.optional is None:
    #         input['optional'] = False
    #     if input.multi is None:
    #         input['multi'] = False
    
    missing_inputs = [input_field.id for input_field in app_inputs 
                      if not input_field.optional and input_field.id not in resolved_inputs]
        
    if missing_inputs:
        missing_input_ids = ', '.join(input['id'] for input in missing_inputs)
        raise ValueError(f"some required inputs are missing: {missing_input_ids}")

def prepare_app_config(app, user_options):
    values = {}
    for key in app['config']:
        app_param = app['config'][key]
        user_param = user_options['config'].get(key)

        if app_param['type'] != 'input':
            if user_param is None:
                user_param = app_param.get('default')
            values[key] = user_param

    return values

def collect_unique_dataset_ids(app, inputs):
    dataset_ids = []
    for input in app['inputs']:
        if input['id'] in inputs:
            dataset_ids.extend(user_input['_id'] for user_input in inputs[input['id']])
    
    # Removing duplicates
    dataset_ids = list(set(dataset_ids))
    return dataset_ids


def prepare_inputs_and_subdirs(app, inputs, task):
    subdirs = []
    app_inputs = []

    for input in app['inputs']:
        keys = [key for key, value in app['config'].items() if value.get('input_id') == input['id']]

        if input['id'] in inputs:
            for user_input in inputs[input['id']]:
                dataset = next((output for output in task['config']['_outputs'] if output['dataset_id'] == user_input['_id']), None)
                if dataset:
                    app_inputs.append({
                        **dataset,
                        'id': input['id'],
                        'task_id': task['_id'],
                        'keys': keys,
                    })

                    if 'includes' in input:
                        for include in input['includes'].split("\n"):
                            subdirs.append(f"include:{dataset['id']}/{include}")
                    else:
                        subdirs.append(dataset['id'])

    return app_inputs, subdirs

def compile_metadata(app_inputs):
    meta = {}
    for dataset in app_inputs:
        for k in ['subject', 'session', 'run']:
            if k not in meta and k in dataset.get('meta', {}):
                meta[k] = dataset['meta'][k]
    return meta

def prepare_outputs(app, opt_tags, inputs, project_id, meta):
    app_outputs = []

    for output in app['outputs']:
        output_req = {
            'id': output['id'],
            'datatype': output['datatype'],
            'desc': output.get('desc', app['name']),
            'tags': opt_tags,
            'meta': meta,
            'archive': {
                'project': project_id,
                'desc': f"{output['id']} from {app['name']}"
            },
        }

        if 'output_on_root' in output and output['output_on_root']:
            output_req['files'] = output.get('files', [])
        else:
            output_req['subdir'] = output['id']

        # Handle tag pass through
        # ...

        tags = []
        if 'datatype_tags_pass' in output:
            input_datasets = inputs.get(output['datatype_tags_pass'], [])
            for dataset in input_datasets:
                if dataset and 'datatype_tags' in dataset:
                    tags.extend(dataset['datatype_tags'])
                if dataset:
                    output_req['meta'].update(dataset.get('meta', {}))
        tags.extend(output.get('datatype_tags', []))
        output_req['datatype_tags'] = list(set(tags))  # Remove duplicates and set

        app_outputs.append(output_req)
    return app_outputs

def prepare_config(values, download_task, inputs, datatype_table, app):
    id_to_app_input_table = {input['id']: input for input in app['inputs']}
    result = {}

    for key, config in app['config'].items():
        if config['type'] == 'input':
            input_id = config['input_id']
            user_inputs = inputs.get(input_id)
            if not user_inputs:
                continue
            app_input = id_to_app_input_table[input_id]

            if app_input.get('multi', False):
                result.setdefault(key, [])
                for u_input in user_inputs:
                    dtype = datatype_table[u_input['datatype']]
                    id_to_file = {file['id']: file for file in dtype['files']}
                    input_dtype_file = id_to_file[config['file_id']]
                    filepath = f"../{download_task['_id']}/{u_input['_id']}/{input_dtype_file.get('filename') or input_dtype_file.get('dirname')}"
                    result[key].append(filepath)
            else:
                dtype = datatype_table[user_inputs[0]['datatype']]
                id_to_file = {file['id']: file for file in dtype['files']}
                input_dtype_file = id_to_file[config['file_id']]
                filepath = f"../{download_task['_id']}/{user_inputs[0]['_id']}/{input_dtype_file.get('filename') or input_dtype_file.get('dirname')}"
                result[key] = filepath
        else:
            result[key] = values.get(key)

    return result