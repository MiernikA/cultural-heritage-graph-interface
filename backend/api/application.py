from __future__ import annotations

from dataclasses import dataclass

from backend.config import Settings
from backend.data.store import load_backend_data
from backend.exploration.service import ExplorerService
from backend.recommendations.filters import RecommendationFilter
from backend.data.label_resolver import LabelResolver
from backend.exploration.relation_resolver import RelationResolver
from backend.recommendations.service import RecommendationService
from backend.data.semantic_resolver import SemanticResolver


@dataclass(slots=True)
class ApplicationContext:
    explorer: ExplorerService
    recommendations: RecommendationService


def build_application_context(settings: Settings) -> ApplicationContext:
    data = load_backend_data(settings)
    graph = data.graph

    labels = LabelResolver(data.graph, data.ontology)
    resolved_labels = labels.all_resolved_labels()
    graph.build_placeholder_aliases(resolved_labels)
    graph.build_search_index(resolved_labels)
    semantics = SemanticResolver(graph, labels)
    relations = RelationResolver(labels)
    explorer = ExplorerService(
        graph,
        labels,
        semantics,
        relations,
        max_relationships=settings.max_relationships_per_direction,
    )
    recommendation_filter = RecommendationFilter(graph, labels, semantics)
    recommendations = RecommendationService(
        labels,
        semantics,
        data.recommendation_artifacts,
        recommendation_filter,
    )
    return ApplicationContext(
        explorer=explorer,
        recommendations=recommendations,
    )
