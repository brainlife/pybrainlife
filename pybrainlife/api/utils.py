import re
from dataclasses import dataclass, is_dataclass
import requests


def is_id(value):
    return isinstance(value, str) and re.match(r"^[0-9a-fA-F]{24}$", value) is not None


def nested_dataclass(*args, **kwargs):
    def wrapper(cls):
        cls = dataclass(cls, **kwargs)
        original_init = cls.__init__

        def __init__(self, *args, **kwargs):
            valid_kwargs = {}
            for name, value in kwargs.items():
                field_type = cls.__dataclass_fields__.get(name, None)
                if not field_type:
                    continue
                field_type = field_type.type
                if is_dataclass(field_type) and isinstance(value, dict):
                    new_obj = field_type(**value)
                    valid_kwargs[name] = new_obj
                elif (
                    hasattr(field_type, "__args__")
                    and is_dataclass(field_type.__args__[0])
                    and isinstance(value, list)
                ):
                    field_type = field_type.__args__[0]
                    new_obj = [
                        field_type(**v) if isinstance(v, dict) else v for v in value
                    ]
                    valid_kwargs[name] = new_obj
                elif is_dataclass(field_type) and not isinstance(value, field_type):
                    new_obj = field_type(value)
                    valid_kwargs[name] = new_obj
                else:
                    valid_kwargs[name] = value

            original_init(self, *args, **valid_kwargs)

        cls.__init__ = __init__
        return cls

    return wrapper(args[0]) if args else wrapper


def hydrate(fn, nfn=None):
    cache = {}
    _pending = []  # list of (id, instance) tuples awaiting resolution

    def wrapper(cls):

        def _flush():
            if not _pending:
                return
            to_fetch = list({_id for _id, _ in _pending if _id not in cache})
            if to_fetch:
                if nfn is not None:
                    results = nfn(to_fetch)
                else:
                    results = {_id: fn(_id) for _id in to_fetch}
                for _id, result in results.items():
                    cache[_id] = result

            for _id, obj in _pending:
                object.__setattr__(obj, '_hydrate_resolved', True)
                if isinstance(cache[_id], dict):
                    raise ValueError()
                    _original_init[0](obj, **cache[_id])
                # elif isinstance(cache[_id], cls):
                _original_init[0](obj, **cache[_id].__dict__)

            _pending.clear()

        _original_init = [None]

        original_init = cls.__init__
        _original_init[0] = original_init

        def __init__(self, *args, **kwargs):
            if len(args) == 1 and is_id(args[0]) and not kwargs:
                _id = args[0]
                if _id in cache:
                    kwargs = cache[_id]
                elif nfn is not None:
                    object.__setattr__(self, '_hydrate_resolved', False)
                    _pending.append((_id, self))
                    return
                else:
                    kwargs = fn(_id)
            if len(args) == 1 and isinstance(args[0], cls):
                kwargs = args[0].__dict__
            if isinstance(kwargs, cls):
                kwargs = kwargs.__dict__
            object.__setattr__(self, '_hydrate_resolved', True)
            original_init(self, **kwargs)

        def __getattr__(self, name):
            if not object.__getattribute__(self, '_hydrate_resolved'):
                _flush()
                return object.__getattribute__(self, name)
            raise AttributeError(name)

        cls.__init__ = __init__
        cls.__getattr__ = __getattr__
        return cls

    return wrapper


def validate_branch(github_repo, branch):
    try:
        headers = {"User-Agent": "brainlife CLI"}
        response = requests.get(
            f"https://api.github.com/repos/{github_repo}/branches", headers=headers
        )
        response.raise_for_status()

        branches = response.json()
        if not any(branch == valid_branch["name"] for valid_branch in branches):
            raise ValueError(
                f"The given github branch ({branch}) does not exist for {github_repo}"
            )
    except Exception as err:
        raise Exception(f"Error checking branch: {err}")


def api_error(res, message=None):
    if res.status_code == 404:
        raise Exception("Not found")
    if res.status_code != 200:
        exc = Exception(message or "Unknown error occurred")
        try:
            data = res.json()
            exc = Exception(data.get("message", message))
        except:
            pass
        raise exc
