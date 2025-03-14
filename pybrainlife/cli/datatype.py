import json
import logging

from ..api.datatype import datatype_query
from .utils import ensure_auth


logger = logging.getLogger("pybrainlife.cli")


def args(subparser):
    parser = subparser.add_parser(
        "datatype", help="Information about data types available on Brainlife."
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparser = subparsers.add_parser("query", help="Query datatypes")
    subparser.add_argument("-i", "--id", help="Filter datatype by Id")
    subparser.add_argument(
        "-q", "--query", help="Filter datatype by name or description"
    )
    subparser.add_argument("-s", "--skip", help="Skip N datatypes", type=int)
    subparser.add_argument("-l", "--limit", help="Number of results to show", type=int)
    subparser.add_argument("-j", "--json", help="Output as JSON", action="store_true")


def run(args):
    ensure_auth()

    if args.subcommand == "query":
        datatypes = datatype_query(
            id=args.id, search=args.query,
            skip=args.skip, limit=args.limit
        )
        if not datatypes:
            logger.error("No datatypes found")
            return 1

        if args.json:
            print(json.dumps(datatypes))

        else:
            print("Datatypes:")
            print("")
            for dt in datatypes:
                print(f"Id: {dt.id}")
                print(f"Name: {dt.name}")
                print(f"Description: {dt.description}")
                print(f"Files:")
                for file in dt.files:
                    print(
                        f"- {file.field}{(file.required and ' (required)' or '')}: {file.name}",
                    )
                print("")

        return 0
