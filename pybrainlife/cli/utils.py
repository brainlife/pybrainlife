import os
import stat
import jwt

from pathlib import Path
from ..api.api import get_host, get_auth, set_auth

home = Path.home() or ""
token_path = home / ".config" / get_host() / ".jwt"


def init_auth():
    token = load_auth("env")
    if token is None:
        token = load_auth("file")
    set_auth(token)
    return token


def get_token_path():
    return home / ".config" / get_host() / ".jwt"


def load_auth(method="env"):
    """Get authentication token"""

    if method == "file":
        path = get_token_path()
        if not path.exists():
            return
        with open(path, "r") as f:
            return f.read()
    elif method == "env":
        return os.environ.get("BL_TOKEN")

    raise ValueError("Invalid method")


def save_auth(token):
    token_path = get_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as f:
        f.write(token)
    os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)


def ensure_auth():
    token = get_auth()
    if token is None:
        raise Exception("Not authenticated")

    jwt.decode(
        token,
        options={"verify_signature": False, "verify_exp": True}
      )
    
def logged_in_user_details():
    token = get_auth()
    if token is None:
        raise Exception("Not authenticated")
    return jwt.decode(token, options={"verify_signature": False, "verify_exp": True})