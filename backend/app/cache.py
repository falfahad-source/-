"""Finished responses of the read-only pages (verse, surah list, mushaf page...), kept in memory.

The Quranic data does not change between deployments, so after the first reader a page is
served from here instead of being rebuilt (dozens of queries and JSON encoding, slow on a small
host). What can change, the review state of a curated comparison, clears the cache when a
reviewer acts (review_api). Bounded by total size; per process, emptied on restart.
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from typing import Callable

from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response

MAX_BYTES = 48 * 1024 * 1024
_store: OrderedDict[str, bytes] = OrderedDict()
_size = 0
_lock = threading.Lock()


def cached_json(key: str, compute: Callable[[], object], max_age: int = 300) -> Response:
    """The JSON of `compute()` for `key`, computed once. An exception (e.g. a 404) is not cached.
    `max_age` lets the reader's browser reuse it too, for that many seconds."""
    global _size
    with _lock:
        body = _store.get(key)
        if body is not None:
            _store.move_to_end(key)
    if body is None:
        body = json.dumps(jsonable_encoder(compute()), ensure_ascii=False, separators=(",", ":")).encode()
        with _lock:
            if key not in _store:
                _store[key] = body
                _size += len(body)
                while _size > MAX_BYTES and _store:
                    _size -= len(_store.popitem(last=False)[1])
    return Response(body, media_type="application/json", headers={"Cache-Control": f"public, max-age={max_age}"})


def clear() -> None:
    global _size
    with _lock:
        _store.clear()
        _size = 0
