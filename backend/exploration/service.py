from __future__ import annotations

from collections import defaultdict
from math import log1p

from backend.data.graph.knowledge_graph import KnowledgeGraph
from backend.data.graph.constants import CIDOC, RDF_TYPE, RDFS_LABEL
from backend.data.graph.models import Edge, Node
from backend.data.schemas import (
    EntityAdvanced,
    EntityDetail,
    EntityRef,
    RawTriple,
    RdfPathStep,
    Relationship,
    RelationshipGroup,
    SearchResult,
    TypeRef,
)
from backend.data.label_resolver import LabelResolver
from backend.exploration.relation_resolver import RelationResolver
from backend.data.semantic_resolver import SemanticResolver
from backend.data.text import is_uri, normalize_for_search, uri_tail


class ExplorerService:
    def __init__(
        self,
        graph: KnowledgeGraph,
        labels: LabelResolver,
        semantics: SemanticResolver,
        relations: RelationResolver,
        max_relationships: int = 250,
    ) -> None:
        self.graph = graph
        self.labels = labels
        self.semantics = semantics
        self.relations = relations
        self.max_relationships = max_relationships

    def get_entity(self, uri: str) -> EntityDetail | None:
        uri = self.graph.canonical_uri(uri)
        node = self.graph.nodes.get(uri)
        if not node or not self.graph.is_described_entity(uri):
            return None
        profile = self.semantics.profile_for(uri)
        if not profile:
            return None
        return EntityDetail(
            uri=uri,
            display_name=profile.display_name,
            semantic_type=profile.semantic_type,
            description=profile.description,
            icon=profile.icon,
            aliases=list(profile.aliases),
            importance=self._importance(uri, node),
            rdf_types=self._types(node),
            summary=self._summary(node),
            connections=self._connection_groups(uri),
            advanced=EntityAdvanced(uri=uri, raw_triples=self._raw_triples(node)),
        )

    def search(self, query: str, limit: int = 25) -> list[SearchResult]:
        candidate_scores = self.graph.scored_search_candidates(query)
        results: list[SearchResult] = []

        for uri, index_score in candidate_scores.items():
            if not self.graph.is_described_entity(uri) or self.semantics.is_technical_node(uri) or uri.startswith(CIDOC):
                continue
            profile = self.semantics.profile_for(uri)
            if not profile:
                continue
            label = profile.display_name
            node = self.graph.nodes.get(uri)
            score = self._search_score(query, uri, label, profile.aliases, node, index_score)
            results.append(
                SearchResult(
                    uri=uri,
                    label=label,
                    semantic_type=profile.semantic_type,
                    description=profile.description,
                    icon=profile.icon,
                    rdf_types=self._types(node) if node else [],
                    score=score,
                )
            )

        results.sort(key=lambda item: (-item.score, item.label.casefold(), item.uri))
        return results[:limit]

    def stats(self) -> dict[str, int]:
        predicates = {edge.predicate for edge in self.graph.edges}
        return {
            "nodes": len(self.graph.nodes),
            "edges": len(self.graph.edges),
            "types": len(self.graph.by_type),
            "predicates": len(predicates),
        }

    def _connection_groups(self, uri: str) -> list[RelationshipGroup]:
        grouped: dict[str, dict[str, Relationship]] = defaultdict(dict)
        source_profile = self.semantics.profile_for(uri)
        if not source_profile:
            return []
        for semantic_path in self.semantics.semantic_paths_for(uri, self.max_relationships):
            target = self._entity_ref(semantic_path.target_uri)
            target_profile = self.semantics.profile_for(semantic_path.target_uri)
            if not target_profile:
                continue
            resolved = self.relations.resolve(
                uri,
                semantic_path.target_uri,
                semantic_path.path,
                source_profile,
                target_profile,
                semantic_path.confidence,
            )
            relationship = Relationship(
                relation=resolved.display_label,
                display_label=resolved.display_label,
                direction=resolved.direction,
                symmetric=resolved.symmetric,
                category=resolved.category,
                explanation=resolved.explanation,
                target=target,
                rdf_path=[self._path_step(edge) for edge in semantic_path.path],
                simplified=len(semantic_path.path) > 1,
            )
            existing = grouped[relationship.category].get(relationship.target.uri)
            if existing and len(existing.rdf_path) <= len(relationship.rdf_path):
                continue
            grouped[relationship.category][relationship.target.uri] = relationship

        return [
            RelationshipGroup(label=label, relationships=list(relationships.values()))
            for label, relationships in sorted(grouped.items(), key=lambda item: item[0].casefold())
            if relationships.values()
        ]

    def _summary(self, node: Node) -> list[str]:
        facts: list[str] = []
        type_labels = [self.labels.predicate_label(type_uri) for type_uri in node.rdf_types]
        readable_types = [label for label in type_labels if label and not label.startswith("E")]
        if readable_types:
            facts.append("Type: " + ", ".join(sorted(readable_types)[:3]))
        return facts

    def _importance(self, uri: str, node: Node) -> list[str]:
        facts: list[str] = []
        connection_count = len(node.outgoing) + len(node.incoming)
        if connection_count:
            facts.append(f"Connected to {connection_count:,} graph statements.".replace(",", " "))
        semantic_count = len(self.semantics.semantic_paths_for(uri, min(self.max_relationships, 80)))
        if semantic_count:
            facts.append(f"{semantic_count} meaningful connections are ready to explore.")
        if node.labels:
            facts.append("Has a resolved display label from the source data.")
        return facts[:3]

    def _raw_triples(self, node: Node) -> list[RawTriple]:
        triples: list[RawTriple] = []
        subject = self._raw_value_ref(node.uri)
        for type_uri in sorted(node.rdf_types):
            triples.append(
                RawTriple(
                    subject=subject,
                    predicate_uri=RDF_TYPE,
                    predicate_label=self._raw_predicate_label(RDF_TYPE),
                    object=self._raw_value_ref(type_uri),
                )
            )
        for label in node.labels:
            triples.append(
                RawTriple(
                    subject=subject,
                    predicate_uri=RDFS_LABEL,
                    predicate_label=self._raw_predicate_label(RDFS_LABEL),
                    object=label,
                )
            )
        for edge in [self.graph.edges[index] for index in node.outgoing]:
            subject = self._raw_value_ref(edge.source)
            obj = self._raw_target_ref(edge.target)
            triples.append(
                RawTriple(
                    subject=subject,
                    predicate_uri=edge.predicate,
                    predicate_label=self._raw_predicate_label(edge.predicate),
                    object=obj,
                )
            )
        for edge in [self.graph.edges[index] for index in node.incoming]:
            subject = self._raw_value_ref(edge.source)
            obj = self._raw_target_ref(edge.target)
            triples.append(
                RawTriple(
                    subject=subject,
                    predicate_uri=edge.predicate,
                    predicate_label=self._raw_predicate_label(edge.predicate),
                    object=obj,
                )
            )
        return triples

    def _visible_target_ref(self, value: str) -> EntityRef | str | None:
        if is_uri(value):
            return self._visible_ref(self.graph.canonical_uri(value))
        return value

    def _visible_ref(self, uri: str) -> EntityRef | None:
        uri = self.graph.canonical_uri(uri)
        profile = self.semantics.profile_for(uri)
        if not profile:
            return None
        node = self.graph.nodes.get(uri)
        return EntityRef(
            uri=uri,
            label=profile.display_name,
            semantic_type=profile.semantic_type,
            icon=profile.icon,
            rdf_types=self._types(node) if node else [],
        )

    def _raw_target_ref(self, value: str) -> EntityRef | str:
        if is_uri(value):
            return self._raw_value_ref(self.graph.canonical_uri(value))
        return value

    def _raw_value_ref(self, uri: str) -> EntityRef | str:
        uri = self.graph.canonical_uri(uri)
        node = self.graph.nodes.get(uri)
        label = self._raw_label_for(uri)
        if not node:
            return label
        profile = self.semantics.profile_for(uri)
        return EntityRef(
            uri=uri,
            label=label,
            semantic_type=profile.semantic_type if profile else "Raw RDF node",
            icon=profile.icon if profile else "circle-dot",
            rdf_types=self._types(node),
        )

    def _raw_label_for(self, uri: str) -> str:
        label = self.labels.label_for(uri)
        return uri if label == uri_tail(uri) else label

    def _raw_predicate_label(self, uri: str) -> str:
        label = self.labels.predicate_label(uri)
        return uri if label == uri_tail(uri) else label

    def _entity_ref(self, uri: str) -> EntityRef:
        uri = self.graph.canonical_uri(uri)
        node = self.graph.nodes.get(uri)
        profile = self.semantics.profile_for(uri)
        return EntityRef(
            uri=uri,
            label=profile.display_name if profile else self.labels.label_for(uri),
            semantic_type=profile.semantic_type if profile else "Entity",
            icon=profile.icon if profile else "circle-dot",
            rdf_types=self._types(node) if node else [],
        )

    def _types(self, node: Node | None) -> list[TypeRef]:
        if not node:
            return []
        return sorted(
            [TypeRef(uri=type_uri, label=self.labels.predicate_label(type_uri)) for type_uri in node.rdf_types],
            key=lambda item: item.label.casefold(),
        )

    def _path_step(self, edge: Edge) -> RdfPathStep:
        return RdfPathStep(
            source=self._visible_ref(edge.source) or "Semantic context",
            predicate_uri=edge.predicate,
            predicate_label=self.labels.predicate_label(edge.predicate),
            target=self._visible_target_ref(edge.target) or "Semantic context",
        )

    def _search_score(
        self,
        query: str,
        uri: str,
        label: str,
        aliases: tuple[str, ...],
        node: Node | None,
        index_score: float,
    ) -> float:
        normalized_query = normalize_for_search(query)
        label_scores = [_text_match_score(normalized_query, label)]
        label_scores.extend(_text_match_score(normalized_query, alias) for alias in aliases)
        label_score = max(label_scores)
        uri_score = _text_match_score(normalized_query, uri_tail(uri)) * 0.55
        type_score = _type_priority(self.semantics.profile_for(uri).semantic_type if self.semantics.profile_for(uri) else "")
        connection_score = log1p(len(node.outgoing) + len(node.incoming)) if node else 0.0
        return label_score + uri_score + (index_score * 120.0) + type_score + min(connection_score * 3.0, 24.0)


def _text_match_score(normalized_query: str, value: str) -> float:
    normalized_value = normalize_for_search(value)
    if not normalized_query or not normalized_value:
        return 0.0
    if normalized_value == normalized_query:
        return 1_000.0
    if normalized_value.startswith(normalized_query):
        return 850.0
    words = normalized_value.split()
    if any(word == normalized_query for word in words):
        return 820.0
    if any(word.startswith(normalized_query) for word in words):
        return 720.0
    if normalized_query in normalized_value:
        return 560.0

    query_tokens = normalized_query.split()
    if query_tokens and all(token in normalized_value for token in query_tokens):
        return 430.0 + (40.0 / max(1, len(words)))

    query_grams = _search_grams(normalized_query)
    value_grams = _search_grams(normalized_value)
    if not query_grams or not value_grams:
        return 0.0
    overlap = len(query_grams.intersection(value_grams)) / len(query_grams)
    return overlap * 260.0


def _search_grams(value: str) -> set[str]:
    chunks = [chunk for chunk in normalize_for_search(value).split() if chunk]
    grams: set[str] = set()
    for chunk in chunks:
        if len(chunk) <= 3:
            grams.add(chunk)
        else:
            grams.update(chunk[index : index + 3] for index in range(len(chunk) - 2))
    return grams


def _type_priority(semantic_type: str) -> float:
    return {
        "Person": 35.0,
        "Object": 30.0,
        "Place": 24.0,
        "Institution": 20.0,
        "Actor": 18.0,
        "Event": 16.0,
        "Type": 8.0,
    }.get(semantic_type, 0.0)
