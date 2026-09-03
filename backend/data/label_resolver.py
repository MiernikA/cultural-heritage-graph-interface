from __future__ import annotations

from collections.abc import Collection
from functools import lru_cache

from backend.data.graph.constants import (
    E35_TITLE,
    E41_APPELLATION,
    P102_HAS_TITLE,
    P1I_IDENTIFIES,
    P82A_BEGIN,
    P82B_END,
    RDFS_LABEL,
)
from backend.data.graph.knowledge_graph import KnowledgeGraph
from backend.data.ontology.models import Ontology
from backend.data.text import compact_text, is_uri, uri_tail


class LabelResolver:
    def __init__(self, graph: KnowledgeGraph, ontology: Ontology) -> None:
        self.graph = graph
        self.ontology = ontology

    @lru_cache(maxsize=500_000)
    def label_for(self, uri: str) -> str:
        node = self.graph.nodes.get(uri)
        if node:
            direct = self._best_direct_label(node.labels, uri)
            if direct:
                return direct

            title = self._label_from_related_value(uri, P102_HAS_TITLE, {E35_TITLE})
            if title:
                return title

            appellation = self._label_from_related_value(uri, P1I_IDENTIFIES, {E41_APPELLATION}, incoming=True)
            if appellation:
                return appellation

            timespan = self._timespan_label(uri)
            if timespan:
                return timespan

        ontology_label = self.ontology.label_for(uri)
        if ontology_label:
            return ontology_label

        return uri_tail(uri)

    def predicate_label(self, uri: str) -> str:
        label = self.ontology.label_for(uri)
        return label if label else uri_tail(uri)

    def all_resolved_labels(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for uri in self.graph.nodes:
            labels[uri] = self.label_for(uri)
        for uri in self.ontology.terms:
            labels.setdefault(uri, self.label_for(uri))
        return labels

    def _best_direct_label(self, labels: list[str], uri: str) -> str | None:
        generated_tail = uri_tail(uri).replace(" ", "_")
        for label in labels:
            clean = compact_text(label)
            if clean and clean != generated_tail:
                return clean
        return None

    def _label_from_related_value(
        self,
        uri: str,
        predicate: str,
        expected_types: Collection[str],
        *,
        incoming: bool = False,
    ) -> str | None:
        node = self.graph.nodes.get(uri)
        if not node:
            return None

        edge_indices = node.incoming if incoming else node.outgoing

        for edge_index in edge_indices:
            edge = self.graph.edges[edge_index]

            if edge.predicate != predicate:
                continue

            if incoming:
                related_uri = edge.source
            else:
                if not edge.target_is_uri:
                    continue
                related_uri = edge.target

            related = self.graph.nodes.get(related_uri)
            if related and (
                not expected_types
                or related.rdf_types.intersection(expected_types)
            ):
                label = self._literal_or_direct_label(related_uri)
                if label:
                    return label

        return None

    def _literal_or_direct_label(self, uri: str) -> str | None:
        node = self.graph.nodes.get(uri)
        if not node:
            return None

        direct = self._best_direct_label(node.labels, uri)
        if direct:
            return direct

        for edge_index in node.outgoing:
            edge = self.graph.edges[edge_index]
            if edge.predicate == RDFS_LABEL and not is_uri(edge.target):
                return compact_text(edge.target)

        return None

    def _timespan_label(self, uri: str) -> str | None:
        node = self.graph.nodes.get(uri)
        if not node:
            return None

        begin: str | None = None
        end: str | None = None

        for edge_index in node.outgoing:
            edge = self.graph.edges[edge_index]
            if edge.predicate == P82A_BEGIN:
                begin = edge.target
            elif edge.predicate == P82B_END:
                end = edge.target

        if begin and end and begin == end:
            return begin
        if begin and end:
            return f"{begin} - {end}"
        return begin or end
