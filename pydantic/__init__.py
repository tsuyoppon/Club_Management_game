import os
from typing import Any, Optional


class FieldInfo:
    def __init__(self, default: Any = None, env: Optional[str] = None, description: str | None = None):
        self.default = default
        self.env = env
        self.description = description


def Field(default: Any = None, *, env: Optional[str] = None, description: str | None = None):
    return FieldInfo(default=default, env=env, description=description)


class BaseSettings:
    def __init__(self, **kwargs: Any):
        annotations = getattr(self, "__annotations__", {})
        for key in annotations:
            value = getattr(self.__class__, key, None)
            if isinstance(value, FieldInfo):
                env_key = value.env or key
                val = os.getenv(env_key.upper(), value.default)
            else:
                val = value
            if key in kwargs:
                val = kwargs[key]
            setattr(self, key, val)
