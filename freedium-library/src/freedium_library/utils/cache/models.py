from dataclasses import dataclass
from typing import Union


@dataclass
class CacheResponse:
    """A single cache entry as returned by backends."""

    key: str
    value: Union[str, dict]
