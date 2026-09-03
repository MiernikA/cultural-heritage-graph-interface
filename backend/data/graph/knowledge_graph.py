from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from backend.data.graph.constants import RDF_TYPE, RDFS_LABEL
from backend.data.graph.models import Edge, Node
from backend.data.text import compact_text, is_uri, local_class_prefix, normalize_for_search


class KnowledgeGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.by_type: dict[str, set[str]] = defaultdict(set)
        self.search_index: dict[str, set[str]] = defaultdict(set)
        self.label_index: dict[str, str] = {}
        self.canonical_uri_by_placeholder: dict[str, str] = {}

    def get_or_create_node(self, uri: str) -> Node:
        node = self.nodes.get(uri)
        if node is None:
            node = Node(uri=uri)
            self.nodes[uri] = node
        return node

    def add_triple(self, subject: str, predicate: str, obj: str) -> None:
        subject_node = self.get_or_create_node(subject)

        if predicate == RDF_TYPE and is_uri(obj):
            subject_node.rdf_types.add(obj)
            self.by_type[obj].add(subject)
            return

        if predicate == RDFS_LABEL:
            label = compact_text(obj)
            if label and label not in subject_node.labels:
                subject_node.labels.append(label)
            return

        edge = Edge(source=subject, predicate=predicate, target=obj, target_is_uri=is_uri(obj))
        edge_index = len(self.edges)
        self.edges.append(edge)
        subject_node.outgoing.append(edge_index)
        if edge.target_is_uri:
            target_node = self.get_or_create_node(obj)
            target_node.incoming.append(edge_index)

    def build_search_index(self, resolved_labels: dict[str, str]) -> None:
        self.search_index.clear()
        self.label_index = {}
        for uri, label in resolved_labels.items():
            if not self.is_described_entity(uri):
                continue
            haystack = normalize_for_search(f"{label} {uri}")
            self.label_index[uri] = haystack
            for gram in _ngrams(haystack):
                self.search_index[gram].add(uri)

    def search_candidates(self, query: str) -> set[str]:
        normalized = normalize_for_search(query)
        grams = _ngrams(normalized)
        if not grams:
            return set()

        matches: set[str] | None = None
        for gram in grams:
            gram_matches = self.search_index.get(gram, set())
            matches = set(gram_matches) if matches is None else matches.intersection(gram_matches)
            if not matches:
                return set()
        return {uri for uri in (matches or set()) if normalized in self.label_index.get(uri, "")}

    def scored_search_candidates(self, query: str, max_candidates: int = 1_500) -> dict[str, float]:
        normalized = normalize_for_search(query)
        if not normalized:
            return {}

        candidates: dict[str, float] = {}
        grams = _ngrams(normalized)
        if len(normalized) <= 3:
            for uri, haystack in self.label_index.items():
                if normalized in haystack:
                    candidates[uri] = 1.0
            return candidates

        for gram in grams:
            for uri in self.search_index.get(gram, set()):
                candidates[uri] = candidates.get(uri, 0.0) + 1.0

        gram_count = max(1, len(grams))
        ranked = sorted(candidates.items(), key=lambda item: item[1], reverse=True)
        return {uri: overlap / gram_count for uri, overlap in ranked[:max_candidates]}

    def is_described_entity(self, uri: str) -> bool:
        node = self.nodes.get(uri)
        if not node:
            return False
        return bool(node.rdf_types or node.outgoing)

    def is_placeholder_reference(self, uri: str) -> bool:
        node = self.nodes.get(uri)
        if not node:
            return False
        return not self.is_described_entity(uri)

    def build_placeholder_aliases(self, resolved_labels: dict[str, str]) -> None:
        self.canonical_uri_by_placeholder.clear()

        by_label: dict[str, list[str]] = defaultdict(list)
        for uri, label in resolved_labels.items():
            if uri in self.nodes:
                by_label[normalize_for_search(label)].append(uri)

        for uri in self.nodes:
            if not self.is_placeholder_reference(uri):
                continue
            label = normalize_for_search(resolved_labels.get(uri, ""))
            candidates = [candidate for candidate in by_label.get(label, []) if candidate != uri and self.is_described_entity(candidate)]
            canonical = _choose_canonical_uri(uri, candidates)
            if canonical:
                self.canonical_uri_by_placeholder[uri] = canonical

    def canonical_uri(self, uri: str) -> str:
        return self.canonical_uri_by_placeholder.get(uri, uri)


def load_graph_from_tsv(path: Path) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    pending: list[str] | None = None

    def flush_pending() -> None:
        nonlocal pending
        if pending is not None:
            graph.add_triple(pending[0], pending[1], pending[2])
            pending = None

    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.rstrip("\r\n")
            if not line:
                if pending is not None:
                    pending[2] += "\n"
                continue
            parts = line.split("\t", 2)
            if len(parts) == 3 and is_uri(parts[0]) and is_uri(parts[1]):
                flush_pending()
                pending = parts
            elif pending is not None:
                pending[2] += "\n" + line
            else:
                raise ValueError(f"Invalid TSV triple at line {line_number}: expected 3 columns")
    flush_pending()
    return graph


def _ngrams(value: str) -> set[str]:
    text = normalize_for_search(value)
    chunks = [chunk for chunk in text.split() if chunk]
    grams: set[str] = set()
    for chunk in chunks:
        if len(chunk) <= 3:
            grams.add(chunk)
        else:
            grams.update(chunk[index : index + 3] for index in range(len(chunk) - 2))
    return grams


def _choose_canonical_uri(uri: str, candidates: list[str]) -> str | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    source_prefix = local_class_prefix(uri)
    same_prefix = [candidate for candidate in candidates if local_class_prefix(candidate) == source_prefix]
    if len(same_prefix) == 1:
        return same_prefix[0]
    return None
