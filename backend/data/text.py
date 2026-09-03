from __future__ import annotations

import re
import unicodedata


_WS_RE = re.compile(r"\s+")


def compact_text(value: str) -> str:
    return _WS_RE.sub(" ", value).strip()


def normalize_for_search(value: str) -> str:
    value = compact_text(value).casefold()
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_marks


def uri_tail(uri: str) -> str:
    tail = uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    return compact_text(tail.replace("_", " "))


def local_class_prefix(uri: str) -> str:
    tail = uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    return tail.split("_", 1)[0]


def is_uri(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://") or value.startswith("urn:")
