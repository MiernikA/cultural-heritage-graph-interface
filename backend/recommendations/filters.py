from __future__ import annotations

from backend.data.graph.knowledge_graph import KnowledgeGraph
from backend.data.schemas import Recommendation, TypeRef
from backend.data.label_resolver import LabelResolver
from backend.data.semantic_resolver import SemanticResolver
from backend.data.text import is_uri


class RecommendationFilter:
    def __init__(
        self,
        graph: KnowledgeGraph,
        labels: LabelResolver,
        semantics: SemanticResolver,
    ) -> None:
        self.graph = graph
        self.labels = labels
        self.semantics = semantics

    def build_recommendation_for_uri(self, current_uri: str, uri: str, score: float) -> Recommendation | None:
        uri = self.graph.canonical_uri(uri)
        if uri == current_uri:
            return None
        if not is_uri(uri):
            return None
        node = self.graph.nodes.get(uri)
        if not node:
            return None
        profile = self.semantics.profile_for(uri)
        if not profile:
            return None
        label = profile.display_name
        if not label or label == uri:
            return None
        return Recommendation(
            uri=uri,
            label=label,
            semantic_type=profile.semantic_type,
            icon=profile.icon,
            rdf_types=_types(node.rdf_types, self.labels),
            score=score,
        )


def _types(type_uris: set[str], labels: LabelResolver) -> list[TypeRef]:
    return sorted(
        [TypeRef(uri=type_uri, label=labels.predicate_label(type_uri)) for type_uri in type_uris],
        key=lambda item: item.label.casefold(),
    )
