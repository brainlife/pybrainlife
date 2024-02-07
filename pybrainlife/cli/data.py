import os
import io
import json
import time
import tarfile
import argparse
import requests

from .utils import ensure_auth
from ..api.datatype import datatype_query
from ..api.project import project_query
from ..api.api import auth_header, services
from ..api.compound.data import upload_dataset


def args(subparser):
    parser = subparser.add_parser(
        "data", help="Information about data types available on Brainlife."
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    subparser = subparsers.add_parser("upload", help="Upload data")
    subparser.add_argument("-p", "--project", help="Project ID", required=True)
    subparser.add_argument(
        "-d", "--datatype", help="Datatype name or ID", required=True
    )
    subparser.add_argument("--datatype_tag", action="append", help="Datatype tags")
    subparser.add_argument("-t", "--tag", action="append", help="Dataset tags")
    subparser.add_argument("-n", "--description", help="Description of the dataset")
    subparser.add_argument(
        "-s",
        "--subject",
        help="(metadata) subject of the uploaded dataset",
        required=True,
    )
    subparser.add_argument(
        "-e", "--session", help="(metadata) session of the uploaded dataset"
    )
    subparser.add_argument("-r", "--run", help="(metadata) run of the uploaded dataset")
    subparser.add_argument(
        "-m",
        "--meta",
        help="file path for a sidecar JSON file containing additional metadata",
    )
    subparser.add_argument("-j", "--json", help="Output as JSON", action="store_true")


def run(args, unknown):
    ensure_auth()

    if args.subcommand == "upload":
        return run_upload(args, unknown)


def run_upload(args, unknown):
    datatypes = datatype_query(search=args.datatype)
    if not datatypes:
        print(f"No datatypes found for {args.datatype}")
        return 1

    datatype = datatypes[0]

    # TODO better help message
    parser = argparse.ArgumentParser(add_help=False)
    for file in datatype.files:
        filetype = {"f": "file", "d": "directory"}[file.type]
        parser.add_argument(
            f"--{file.field}", help=f"{file.name} ({filetype})", required=file.required
        )
    files_args = vars(parser.parse_args(unknown))

    tags = args.tag or []
    datatype_tags = args.datatype_tag or []
    description = args.description

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

    datasets = upload_dataset(
        project=project,
        datatype=datatype,
        files=files_args,
        description=description,
        tags=tags,
        datatype_tags=datatype_tags,
        metadata=metadata,
    )

    for dataset in datasets:
        print(f'{services["main"]}/project/{project.id}#object:{dataset["_id"]}')

    return 0
