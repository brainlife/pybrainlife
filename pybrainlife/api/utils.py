import re
from dataclasses import dataclass, is_dataclass
import requests

def is_id(value):
    return isinstance(value, str) and re.match(r'^[0-9a-fA-F]{24}$', value) is not None


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
                    new_obj = [field_type(**v) if isinstance(v, dict) else v for v in value]
                    valid_kwargs[name] = new_obj
                elif is_dataclass(field_type):
                    new_obj = field_type(value)
                    valid_kwargs[name] = new_obj
                else:
                    valid_kwargs[name] = value

            original_init(self, *args, **valid_kwargs)

        cls.__init__ = __init__
        return cls

    return wrapper(args[0]) if args else wrapper


def hydrate(fn):
    def wrapper(cls):
        original_init = cls.__init__
        def __init__(self, *args, **kwargs):
            if len(args) == 1 and is_id(args[0]) and not kwargs:
                kwargs = fn(args[0])
            if len(args) == 1 and isinstance(args[0], cls):
                kwargs = args[0].__dict__
            if isinstance(kwargs, cls):
                kwargs = kwargs.__dict__
            original_init(self, **kwargs)
        cls.__init__ = __init__
        return cls
        
    return wrapper


def validate_branch(github_repo, branch):
    try:
        headers = {"User-Agent": "brainlife CLI"}
        response = requests.get(f'https://api.github.com/repos/{github_repo}/branches', headers=headers)
        response.raise_for_status()

        branches = response.json()
        if not any(branch == valid_branch['name'] for valid_branch in branches):
            raise ValueError(f"The given github branch ({branch}) does not exist for {github_repo}")
    except Exception as err:
        raise Exception(f"Error checking branch: {err}")
    return branch 