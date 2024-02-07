import json

from ..api.datatype import datatype_query
from .utils import ensure_auth


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
        datatypes = datatype_query(args.id, args.query, args.skip, args.limit)
        if not datatypes:
            print("No datatypes found")
            return 1

        if args.json:
            print(json.dumps(datatypes))

        else:
            for dt in datatypes:
                print(f"Id: {dt['_id']}")
                print(f"Name: {dt['name']}")
                print(f"Description: {dt['desc']}")
                print(f"Files:")
                for file in dt["files"]:
                    print(
                        f"  {(file['required'] and '(required) ' or '')}",
                        end="",
                    )
                    name = file.get("filename") or file.get("dirname")
                    print(
                        f"{file['id']}: {name}",
                    )
                print()

        return 0
