import os
import requests
import logging
import json
import logging
import argparse
from tqdm.std import tqdm

from .utils import ensure_auth
from ..api.datatype import datatype_query
from ..api.project import project_query
from ..api.api import auth_header, services
from ..api.compound.data import upload_dataset


logger = logging.getLogger("pybrainlife.cli")


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
        logger.error(f"No datatypes found for {args.datatype}")
        return 1

    datatype = datatypes[0]

    # Dynamically add CLI arguments for files/directories required by the datatype
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
        logger.error(f"No project found for {args.project}")
        return 1
    else:
        project = project[0]

    streaming_pipe = lambda stream_fp: (
      stream_fp
      if logger.level > logging.INFO else
      tqdm.wrapattr(stream_fp, "read", total=len(stream_fp.getbuffer()))
    )

    datasets = upload_dataset(
        project=project,
        datatype=datatype,
        files=files_args,
        description=description,
        tags=tags,
        datatype_tags=datatype_tags,
        metadata=metadata,
        streaming_pipe=streaming_pipe,
    )

    # Upload files to cloud storage via presigned URLs where each file is uploaded individually
    file_paths = []
    for file in datatype.files:
        if file.type == "d":
            dir_path = files_args.get(file.field)
            if dir_path:
                for root, dirs, files in os.walk(dir_path):
                    for name in files:
                        full_path = os.path.join(root, name)
                        relative_path = os.path.relpath(full_path, start=dir_path)
                        file_paths.append(relative_path)
        elif file.type == "f":
            file_path = files_args.get(file.field)
            if file_path:
                file_paths.append(file_path)

    if datasets:
        logger.info("Uploading dataset to cloud storage")
        for dataset in datasets:
            dataset_id = dataset["_id"]
            try:
                presigned_response = requests.post(
                    f"{services['amaretti']}/task/cloud/upload/{dataset_id}",
                    headers={**auth_header()},
                )
                try:
                    presigned_post = presigned_response.json()
                except ValueError as e:
                    logger.error("Failed to parse JSON from the response.")
                    raise e
                upload_url = presigned_post["url"]
                default_fields = presigned_post.get("fields", {})

                # Upload files using presigned URL
                for path in file_paths:
                    fields = default_fields.copy()
                    fields["key"] = f"scratch/datasets/{dataset_id}/{path}"

                    # Check if file exists
                    if not os.path.exists(path):
                        logger.error(f"File does not exist: {path}")
                        continue
                    elif not os.path.isfile(path):
                        logger.error(f"Path is not a file: {path}")
                        continue

                    with open(path, 'rb') as f:
                        files = {"file": f}
                        upload_response = requests.post(upload_url, data=fields, files=files)
                        if upload_response.status_code == 204:
                            logger.info(f"Upload successful.")
                        upload_response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.error(f"Error uploading files: {e}")
                return 1
    if datasets:
      logger.info("Datasets created:")
      for dataset in datasets:
          logger.info(f'{services["main"]}/project/{project.id}#object:{dataset["_id"]}')

    return 0
