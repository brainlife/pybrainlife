"""bl bids upload: upload a BIDS folder that is already converted (e.g. by ezBIDS) to a project.

Each BIDS object becomes a data object of its brainlife datatype (objects already in the project
are skipped), participants.tsv/json go to the participants table, and the other BIDS tables
(phenotype, samples, sessions, scans) become project tables. This is what the ezBIDS
"Send to brainlife" import (brainlife/app-bids-import) runs; it replaces the Node CLI's
`bl bids upload`.
"""

import os
import sys

from .aimport import brainlife_api as bl
from .aimport import upload as uploader
from .aimport.bids_walker import walk
from .aimport.command import load_jwt
from .tables import upload_tables


def args(subparser):
    parser = subparser.add_parser("bids", help="Upload a BIDS folder to a project.")
    subparsers = parser.add_subparsers(dest="subcommand")
    p = subparsers.add_parser("upload", help="Upload a BIDS folder (data objects, participants and tables)")
    p.add_argument("-p", "--project", help="Project ID", required=True)
    p.add_argument("-d", "--directory", help="BIDS folder (where dataset_description.json is)")
    p.add_argument("folder", nargs="?", help="BIDS folder (same as -d)")
    p.add_argument("-t", "--tag", action="append", default=[], help="Tag every uploaded object (repeatable)")


class Deps:
    """What run() talks to; tests replace any of these."""

    def __init__(self, **kw):
        self.load_jwt = load_jwt
        self.api = None
        self.find_project = bl.project_by_id
        self.walk = walk
        self.update_participants = uploader.update_participants
        self.upload_datasets = uploader.upload_datasets
        self.upload_tables = upload_tables
        self.log = print
        self.error = lambda msg: print(msg, file=sys.stderr, flush=True)
        for k, v in kw.items():
            if not hasattr(self, k):
                raise TypeError("unknown dependency " + k)
            setattr(self, k, v)


def run(args, deps=None):
    deps = deps or Deps()
    if args.subcommand != "upload":
        deps.error('use "bl bids upload -h"')
        return 2
    root = args.directory or args.folder
    if not root or not os.path.isfile(os.path.join(root, "dataset_description.json")):
        deps.error("bids upload: %s is not a BIDS folder (no dataset_description.json)" % root)
        return 2
    try:
        headers = {"Authorization": "Bearer " + deps.load_jwt()}
        api = deps.api or bl.default_api()
        project = deps.find_project(headers, args.project, api)
        if not project:
            deps.error("bids upload: project %s not found" % args.project)
            return 1
        bids = deps.walk(root)
        if bids["participants"] or bids["participants_json"]:
            deps.update_participants(headers, project, bids, api=api, log=deps.log)
        uploaded, skipped = deps.upload_datasets(headers, project, bids["datasets"], tags=args.tag, api=api, log=deps.log)
        tables = deps.upload_tables(headers, project, root, api=api, log=deps.log)
        deps.log("Uploaded %d object(s), skipped %d already in the project, %d table(s)" % (len(uploaded), len(skipped), tables))
        deps.log("%s/project/%s" % (api.get("main") or "https://brainlife.io", project["_id"]))
        return 0
    except Exception as err:
        deps.error("bids upload: %s" % err)
        return 1
