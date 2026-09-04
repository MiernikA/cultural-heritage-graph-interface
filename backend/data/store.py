from __future__ import annotations

from dataclasses import dataclass

from backend.config import Settings
from backend.data.graph.knowledge_graph import KnowledgeGraph, load_graph_from_tsv
from backend.data.ontology.loader import load_ontology, ontology_label_triples
from backend.data.ontology.models import Ontology
from backend.recommendations.loader import RecommendationArtifacts


@dataclass(slots=True)
class BackendDataStore:
    graph: KnowledgeGraph
    ontology: Ontology
    recommendation_artifacts: RecommendationArtifacts


def load_backend_data(settings: Settings) -> BackendDataStore:
    ontology = load_ontology(settings.ontology_rdf_path)
    graph = load_graph_from_tsv(settings.graph_tsv_path)
    graph_subjects = set(graph.nodes)

    for subject, predicate, obj in ontology_label_triples(ontology):
        if subject not in graph_subjects:
            graph.add_triple(subject, predicate, obj)

    return BackendDataStore(
        graph=graph,
        ontology=ontology,
        recommendation_artifacts=RecommendationArtifacts(
            entity_to_id_path=settings.recommendation_entity_to_id_path,
            embeddings_path=settings.recommendation_embeddings_path,
            index_path=settings.recommendation_index_path,
            embedding_dim=settings.recommendation_embedding_dim,
            index_space=settings.recommendation_index_space,
        ),
    )
