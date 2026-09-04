from __future__ import annotations

from backend.data.schemas import (
    EntityRef,
    Recommendation,
    RecommendationReason,
)
from backend.recommendations.explainability import RecommendationExplainer
from backend.recommendations.filters import RecommendationFilter
from backend.recommendations.loader import RecommendationArtifacts
from backend.recommendations.semantic_engine import SemanticRecommendationCandidate, SemanticRecommendationEngine
from backend.data.label_resolver import LabelResolver
from backend.data.semantic_resolver import SemanticResolver


DIRECT_RETRIEVAL = "Direct embedding retrieval"
DEFAULT_CANDIDATE_LIMIT = 500
FEATURED_RECOMMENDATION_LIMIT = 4


class RecommendationService:
    def __init__(
        self,
        labels: LabelResolver,
        semantics: SemanticResolver,
        artifacts: RecommendationArtifacts,
        recommendation_filter: RecommendationFilter,
    ) -> None:
        self.labels = labels
        self.semantics = semantics
        self.artifacts = artifacts
        self.filter = recommendation_filter
        self.semantic_engine = SemanticRecommendationEngine(self.filter.graph, self.artifacts)
        self.explainer = RecommendationExplainer(self.filter.graph, labels, semantics)

    def recommend_for_entity(self, uri: str, limit: int | None = None) -> list[Recommendation]:
        current_uri = self.filter.graph.canonical_uri(uri)
        recommendations = [
            recommendation
            for item in self.semantic_engine.recommend(current_uri, DEFAULT_CANDIDATE_LIMIT)
            for recommendation in [self._recommendation_for_semantic_candidate(current_uri, item)]
            if recommendation is not None
        ]
        return recommendations[:limit] if limit is not None else recommendations

    def featured_recommendations_for_entity(self, uri: str) -> list[Recommendation]:
        return self.recommend_for_entity(uri, FEATURED_RECOMMENDATION_LIMIT)

    def _recommendation_for_semantic_candidate(self, current_uri: str, item: SemanticRecommendationCandidate) -> Recommendation | None:
        recommendation = self.filter.build_recommendation_for_uri(current_uri, item.uri, round(item.distance * 100.0, 2))
        if not recommendation:
            return None
        recommendation.semantic_similarity = float(item.distance)
        recommendation.retrieval_origin = DIRECT_RETRIEVAL
        recommendation.retrieval_chain = self._retrieval_chain_refs((current_uri, item.uri))
        recommendation.reasons = [
            RecommendationReason(
                type=reason,
                weight=1.0,
                contribution=1.0,
                rdf_path=item.rdf_paths_by_reason.get(reason, []),
            )
            for reason in item.recommendation_reason
            if reason != "person_or_actor"
        ]
        recommendation.reasons.append(
            RecommendationReason(
                type="embedding_similarity",
                weight=1.0,
                contribution=round(float(item.distance), 4),
                rdf_path=[],
            )
        )
        recommendation.reason_tags = [reason for reason in item.recommendation_reason if reason != "person_or_actor"]
        recommendation.explanation = self.explainer.explain(current_uri, recommendation)
        return recommendation

    def _retrieval_chain_refs(self, chain: tuple[str, ...]) -> list[EntityRef]:
        return [self._entity_ref(uri) for uri in chain]

    def _entity_ref(self, uri: str) -> EntityRef:
        profile = self.semantics.profile_for(uri)
        if profile:
            return EntityRef(uri=uri, label=profile.display_name, semantic_type=profile.semantic_type, icon=profile.icon)
        return EntityRef(uri=uri, label=self.labels.label_for(uri), semantic_type=self._technical_type(uri), icon="circle-dot")

    def _technical_type(self, uri: str) -> str:
        node = self.filter.graph.nodes.get(uri)
        if not node or not node.rdf_types:
            return "Technical entity"
        labels = [self.labels.predicate_label(type_uri) for type_uri in sorted(node.rdf_types)]
        return next((label for label in labels if label), "Technical entity")
