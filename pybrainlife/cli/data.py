import os
import tarfile
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
from ..api.compound.data import download_dataset, upload_dataset


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

    subparser = subparsers.add_parser("download", help="Download data")
    subparser.add_argument("-i", "--id", help="Dataset ID")
    subparser.add_argument("-d", "--directory", help="Directory to download to")
    subparser.add_argument("-j", "--json", help="Output as JSON", action="store_true")
    # Allow positional arguments for id and directory to match legacy behavior or convenience
    subparser.add_argument("args", nargs="*", help="[ID] [Directory]")


def run(args, unknown):
    ensure_auth()

    if args.subcommand == "upload":
        return run_upload(args, unknown)

    if args.subcommand == "download":
        return run_download(args, unknown)

    if args.subcommand == "download-raw":
        return run_download_raw(args, unknown)


def run_upload(args, unknown):
    datatypes = datatype_query(search=args.datatype)
    if not datatypes:
        logger.error(f"No datatypes found for {args.datatype}")
        return 1

    datatype = datatypes[0]

    parser = argparse.ArgumentParser(
        add_help=False,
        description=f"Upload data for datatype: {datatype.name}",
        epilog="Specify the required files/directories for this datatype."
    )
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

    if datasets:
      logger.info("Datasets created:")
      for dataset in datasets:
          logger.info(f'{services["main"]}/project/{project.id}#object:{dataset["_id"]}')

    return 0


def run_download(args, unknown):
    dataset_id = args.id
    directory = args.directory

    # Handle positional arguments
    if args.args:
        if not dataset_id:
            dataset_id = args.args[0]
            if len(args.args) > 1 and not directory:
                directory = args.args[1]
        elif not directory:
             # if id was flag-provided, first positional could be directory
            directory = args.args[0]

    if not dataset_id:
        logger.error("Dataset ID is required")
        return 1

    if not directory:
        directory = dataset_id

    if not args.json:
        logger.info(f"downloading data object to {directory}")

    # Check dataset status
    res = requests.get(
        services["warehouse"] + "/dataset",
        headers=auth_header(),
        params={"find": json.dumps({"_id": dataset_id})}
    )

    if res.status_code != 200:
        logger.error("failed to find data object")
        logger.error(res.json())
        return 1

    datasets = res.json().get("datasets", [])
    if len(datasets) != 1:
        logger.error(f"couldn't find the data object with id {dataset_id}")
        return 1

    dataset = datasets[0]
    if dataset.get("status") != "stored":
        logger.error(f"data object status is not 'stored': {dataset.get('status')}")
        return 1

    # Create directory
    os.makedirs(directory, exist_ok=True)

    try:
        with download_dataset(dataset_id) as r:
            total_size = int(r.headers.get('content-length', 0))
            if not args.json and logger.level <= logging.INFO:
                 with tqdm.wrapattr(r.raw, "read", total=total_size, desc="Downloading") as raw_stream:
                     with tarfile.open(fileobj=raw_stream, mode="r|*") as tar:
                         tar.extractall(path=directory)
            else:
                 with tarfile.open(fileobj=r.raw, mode="r|*") as tar:
                     tar.extractall(path=directory)
    except Exception as e:
        logger.error(f"Error during download: {e}")
        return 1

    return 0

def run_download_raw(args, unknown):
    dataset_id = args.id

    raise NotImplementedError("download-raw is not implemented yet.")
