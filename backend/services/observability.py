import os
from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any


@contextmanager
def observe(name: str, metadata: dict[str, Any]) -> Iterator[Any | None]:
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key and not secret_key:
        yield None
        return
    if not public_key or not secret_key:
        raise RuntimeError(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be configured together."
        )

    from langfuse import get_client

    client = get_client()
    with client.start_as_current_observation(
        as_type="span",
        name=name,
        input=metadata,
    ) as observation:
        try:
            yield observation
        except Exception as error:
            observation.update(
                level="ERROR",
                status_message=type(error).__name__,
            )
            raise
