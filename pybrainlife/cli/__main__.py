import sys
import argparse
from .. import __version__

from ..api.api import host, set_host
from .utils import init_auth
from .login import args as login_args, run as login
from .datatype import args as datatype_args, run as datatype_run
from .data import args as data_args, run as data_run


def main():
    main_parser = argparse.ArgumentParser(add_help=False)
    main_parser.add_argument("-V", "--version", action="version", version=__version__)
    main_parser.add_argument("-H", "--host", help="Brainlife host", default=host)

    subparsers = main_parser.add_subparsers(dest="command")
    login_args(subparsers)
    datatype_args(subparsers)
    data_args(subparsers)

    args, unknown = main_parser.parse_known_args()

    if args.host:
        set_host(args.host)

    if args.command == "login":
        sys.exit(login(args))

    init_auth()

    if args.command == "datatype":
        sys.exit(datatype_run(args))

    if args.command == "data":
        sys.exit(data_run(args, unknown))
