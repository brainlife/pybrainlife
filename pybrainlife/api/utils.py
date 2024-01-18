import re
from dataclasses import dataclass, is_dataclass


def is_id(value):
    return re.match(r'^[0-9a-fA-F]{24}$', value) is not None


def nested_dataclass(*args, **kwargs):
    def wrapper(cls):
        cls = dataclass(cls, **kwargs)
        original_init = cls.__init__

        def __init__(self, *args, **kwargs):
            valid_kwargs = {}
            for name, value in kwargs.items():
                field_type = cls.__annotations__.get(name, None)
                if not field_type:
                    continue
                if is_dataclass(field_type) and isinstance(value, dict):
                    new_obj = field_type(**value)
                    valid_kwargs[name] = new_obj
                elif (
                    hasattr(field_type, "__args__")
                    and is_dataclass(field_type.__args__[0])
                    and isinstance(value, list)
                ):
                    field_type = field_type.__args__[0]
                    new_obj = [field_type(**v) for v in value]
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
            original_init(self, **kwargs)
        cls.__init__ = __init__
        return cls
        
    return wrapper
