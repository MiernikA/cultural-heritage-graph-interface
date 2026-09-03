from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Edge:
    source: str
    predicate: str
    target: str
    target_is_uri: bool


@dataclass(slots=True)
class Node:
    uri: str
    rdf_types: set[str] = field(default_factory=set)
    labels: list[str] = field(default_factory=list)
    outgoing: list[int] = field(default_factory=list)
    incoming: list[int] = field(default_factory=list)
