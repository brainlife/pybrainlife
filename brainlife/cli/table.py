import json
import logging
import sys

from ..api.api import auth_header, services
from . import tables
from .utils import ensure_auth


logger = logging.getLogger("pybrainlife.cli")


def args(subparser):
    parser = subparser.add_parser(
        "table", help="Tables of a project: participants, phenotype, sessions, scans and other BIDS tables."
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    p = subparsers.add_parser("list", help="List the tables of a project")
    p.add_argument("-p", "--project", help="Project ID", required=True)
    p.add_argument("-j", "--json", help="Output as JSON", action="store_true")

    p = subparsers.add_parser("get", help="Download a table as .tsv (or its rows as JSON)")
    p.add_argument("-p", "--project", help="Project ID", required=True)
    p.add_argument("-t", "--table", help='Table ID (from "bl table list"), or "participants"', required=True)
    p.add_argument("-o", "--output", help="File to write (default: standard output)")
    p.add_argument("-j", "--json", help="Output the table and its rows as JSON", action="store_true")

    p = subparsers.add_parser("upload", help="Create or replace a table from a .tsv organized like participants.tsv")
    p.add_argument("-p", "--project", help="Project ID", required=True)
    p.add_argument("-n", "--name", help='Table name, e.g. "phenotype/bdi"', required=True)
    p.add_argument("-k", "--kind", help="phenotype, samples, sessions, scans, or any other word (default: other)")
    p.add_argument("--json-sidecar", help=".json sidecar with the column definitions")
    p.add_argument("tsv", help=".tsv file")

    p = subparsers.add_parser("import", help="Upload every BIDS table (phenotype, samples, sessions, scans) of a BIDS folder")
    p.add_argument("-p", "--project", help="Project ID", required=True)
    p.add_argument("-d", "--directory", help="BIDS folder (where dataset_description.json is)", required=True)

    p = subparsers.add_parser("remove", help="Remove a table")
    p.add_argument("-p", "--project", help="Project ID", required=True)
    p.add_argument("-t", "--table", help="Table ID", required=True)


def run(args):
    ensure_auth()
    headers = auth_header()
    warehouse = services["warehouse"]
    try:
        if args.subcommand == "list":
            found = tables.list_tables(headers, args.project, warehouse)
            if args.json:
                print(json.dumps(found))
                return 0
            for t in found:
                print("%s\t%s\t%s\t%s rows" % (t["_id"], t.get("kind", ""), t["name"], t.get("row_count", "?")))
            return 0

        if args.subcommand == "get":
            table, rows = tables.get_table(headers, args.project, args.table, warehouse)
            text = json.dumps({"table": table, "rows": rows}) + "\n" if args.json else tables.rows_to_tsv(table, rows)
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(text)
            else:
                sys.stdout.write(text)
            return 0

        if args.subcommand == "upload":
            with open(args.tsv, encoding="utf-8") as f:
                body = {"name": args.name, "tsv": f.read()}
            if args.kind:
                body["kind"] = args.kind
            if args.json_sidecar:
                with open(args.json_sidecar, encoding="utf-8") as f:
                    body["json"] = f.read()
            res = tables.put_table(headers, args.project, body, warehouse)
            if res.get("warning"):
                logger.warning(res["warning"])
            print(res["table"]["_id"])
            return 0

        if args.subcommand == "import":
            sent = tables.upload_tables(headers, {"_id": args.project}, args.directory,
                                        {"warehouse": warehouse}, log=logger.warning)
            print("%d table(s) uploaded" % sent)
            return 0

        if args.subcommand == "remove":
            tables.remove_table(headers, args.project, args.table, warehouse)
            return 0
    except tables.TableApiMissing:
        logger.error("this brainlife.io has no table API yet")
        return 1
    except (OSError, RuntimeError) as err:
        logger.error(str(err))
        return 1

    logger.error('use "bl table -h" to see the subcommands')
    return 2
