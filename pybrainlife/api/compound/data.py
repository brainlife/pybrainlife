import os
import io
import json
import time
import tarfile
import argparse
from typing import List
import requests

from ...api.project import Project
from ...api.datatype import DataType, DataTypeTag

from ...api.task import instance_query, instance_create, task_run, task_wait_dataset, task_wait
from ...api.api import auth_header, services

def build_tar(datatype, files):
    stream_fp = io.BytesIO()
    tar = tarfile.TarFile.open(None, 'w|gz', stream_fp)

    for file in datatype.files:

        if not file.field in files:
            continue

        filepath = files[file.field]

        if file.type == 'd' and not os.path.isdir(filepath):
            raise Exception(f"{file.field} is not a directory: {filepath}")

        if file.type == 'f' and not os.path.isfile(filepath):
            raise Exception(f"{file.field} is not a file: {filepath}")

        if file.type == 'd':
            filepath = filepath.rstrip('/')
            for dir, _, dirfiles in os.walk(filepath):
                tardir = dir.replace(filepath, file.name)

                for f in dirfiles:
                    subfilepath = f'{dir}/{f}'
                    tarsubfilepath = f'{tardir}/{f}'
                    tar.add(subfilepath, arcname=tarsubfilepath)
        else:
            tarfilepath = file.name
            tar.add(filepath, arcname=tarfilepath)

    tar.close()
    stream_fp.seek(0)

    return stream_fp


def upload_dataset(
    project: Project,
    datatype: DataType,
    files,
    description: str,
    tags: List[DataTypeTag],
    datatype_tags: List[DataTypeTag],
    metadata: dict,
  ):
    instance_name = f"upload.{project.group}"
    instances = instance_query(name=instance_name)
    if instances:
        instance = instances[0]
    else:
        instance = instance_create(instance_name, project=project)

    task = task_run(instance.id, instance_name, "brainlife/app-noop", {})
    task_wait(task.id)

    stream_fp = build_tar(datatype, files)

    res = requests.post(
        services["amaretti"] + f"/task/upload/{task.id}",
        params={
            "p": "upload/upload.tar.gz",
            "untar": True,
        },
        data=stream_fp,
        headers={**auth_header()},
    )

    if res.status_code != 200:
        raise Exception(res.json()["message"])

    res = requests.post(
        services["warehouse"] + "/dataset/finalize-upload",
        json={
            "task": task.id,
            "datatype": datatype.id,
            "subdir": "upload",
            "fileids": list(files.keys()),
            "datatype_tags": datatype_tags,
            "meta": metadata,
            "tags": tags,
            "desc": description,
        },
        headers={**auth_header()},
    )
    upload_data = res.json()

    if "validator_task" in upload_data:
        datasets = task_wait(upload_data["validator_task"]["_id"])
    else:
        datasets = task_wait_dataset(task.id)

    return datasets
