import os
import io
import json
import time
import tarfile
import argparse
import requests

from bids.layout import BIDSLayout, Query

from .utils import ensure_auth
from ..api.datatype import datatype_query
from ..api.project import project_query
from ..api.task import instance_query, task_run, task_wait_dataset, task_wait
from ..api.api import auth_header, services


def args(subparser):
    parser = subparser.add_parser(
        "data", help="Information about data types available on Brainlife."
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    subparser = subparsers.add_parser("upload", help="Upload data")
    subparser.add_argument("-p", "--project", help="Project ID", required=True)
    subparser.add_argument("-d", "--directory", default='.', help="Root BIDS directory", required=True)
    subparser.add_argument("-t", "--tag", action="append", help="Dataset tags")
    subparser.add_argument("-j", "--json", help="Output as JSON", action="store_true")


def run(args, unknown):
    ensure_auth()

    if args.subcommand == "upload":
        return run_upload(args, unknown)


def run_upload(args, unknown):
    
    layout = BIDSLayout(args.directory)

    tags = args.tag or []

    metadata = {}
    if args.meta:
        with open(args.meta) as fp:
            metadata = json.load(fp)
    if args.subject:
        metadata["subject"] = args.subject
    if args.session:
        metadata["session"] = args.session
    if args.run:
        metadata["run"] = args.run
        tags += [f"run-{args.run}"]

    project = project_query(args.project)
    if not project:
        print(f"No project found for {args.project}")
        return 1
    else:
        project = project[0]

    instance_name = f"upload.{project.group}"
    instances = instance_query(name=instance_name)
    if instances:
        instance = instances[0]
    else:
        instance = instance_create(instance_name, project=project)

    task = task_run(instance.id, instance_name, "brainlife/app-noop", {})
    task_wait(task.id)

    stream_fp = io.BytesIO()
    tar = tarfile.TarFile.open(None, 'w|gz', stream_fp)

    for file in datatype.files:

        if not file.field in files_args:
            continue

        filepath = getattr(files_args, file.field)

        if file.type == 'd' and not os.path.isdir(filepath):
            print(f"{file.field} is not a directory")
            return 1

        if file.type == 'f' and not os.path.isfile(filepath):
            print(f"{file.field} is not a file")
            return 1

        if file.type == 'd':
            filepath = filepath.rstrip('/')
            for dir, _, files in os.walk(filepath):
                tardir = dir.replace(filepath, file.name)

                for f in files:
                    subfilepath = f'{dir}/{f}'
                    tarsubfilepath = f'{tardir}/{f}'
                    tar.add(subfilepath, arcname=tarsubfilepath)
        else:
            tarfilepath = file.name
            tar.add(filepath, arcname=tarfilepath)

    tar.close()
    stream_fp.seek(0)

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
            "fileids": list(files_args.__dict__.keys()),
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

    for dataset in datasets:
        print(f'{services["main"]}/project/{project.id}#object:{dataset["_id"]}')

    return 0
