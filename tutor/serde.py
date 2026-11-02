"""Checkpoint serializer shared by the API's PostgresSaver and the in-memory graph used by the CLI and tests."""

import inspect

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

from tutor import schemas


def serializer() -> JsonPlusSerializer:
    """Checkpoint serializer allowed to rebuild every Pydantic model in tutor/schemas.py.

    LangGraph warns about (and will soon block) loading classes it wasn't told about,
    so new schema models are picked up here automatically.
    """
    models = [
        (schemas.__name__, name)
        for name, obj in vars(schemas).items()
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj.__module__ == schemas.__name__
    ]
    return JsonPlusSerializer(allowed_msgpack_modules=models)
