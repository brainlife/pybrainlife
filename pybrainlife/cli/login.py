import logging
from getpass import getpass

from ..api.api import login
from .utils import save_auth


logger = logging.getLogger("pybrainlife.cli")


def args(subparser):
    parser = subparser.add_parser("login", help="Perform login")
    parser.add_argument("--ldap", help="Login using LDAP", action="store_true")
    parser.add_argument("--username", help="Username")
    parser.add_argument("--password", help="Password")
    parser.add_argument("--ttl", help="Days for the login session to expire", type=int, default=7)


def run(args):
    if not args.quiet and args.username is None:
        args.username = input("Username: ")

    if not args.quiet and args.password is None:
        args.password = getpass("Password: ")

    try:
        token = login(
            args.username,
            args.password,
            ldap=args.ldap,
            ttl=args.ttl,
        )

        save_auth(token)

        logger.info("Login successful")
        return 0
    except:
        logger.info("Login failed")
        return 1
