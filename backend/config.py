import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
SOURCE_DATA_DIR = DATA_DIR / "source"
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
)


@dataclass(frozen=True)
class Settings:
    graph_tsv_path: Path = SOURCE_DATA_DIR / "graph_all_cac.tsv"
    ontology_rdf_path: Path = SOURCE_DATA_DIR / "chexrish_onto_prototype2.rdf"
    max_relationships_per_direction: int = 250
    recommendation_entity_to_id_path: Path = SOURCE_DATA_DIR / "complex_entity_to_id_all_cac.pkl"
    recommendation_embeddings_path: Path = SOURCE_DATA_DIR / "complex_embeddings_all_cac.pkl"
    recommendation_index_path: Path = SOURCE_DATA_DIR / "hnsw_index_complex_model_all_cac.bin"
    recommendation_embedding_dim: int = 400
    recommendation_index_space: str = "ip"
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS


@lru_cache
def get_settings() -> Settings:
    return Settings(
        graph_tsv_path=Path(os.getenv("KG_GRAPH_TSV_PATH", SOURCE_DATA_DIR / "graph_all_cac.tsv")),
        ontology_rdf_path=Path(os.getenv("KG_ONTOLOGY_RDF_PATH", SOURCE_DATA_DIR / "chexrish_onto_prototype2.rdf")),
        max_relationships_per_direction=int(os.getenv("KG_MAX_RELATIONSHIPS_PER_DIRECTION", "250")),
        recommendation_entity_to_id_path=_artifact_path(
            os.getenv("KG_RECOMMENDATION_ENTITY_TO_ID_PATH"),
            "complex_entity_to_id_all_cac.pkl",
        ),
        recommendation_embeddings_path=_artifact_path(
            os.getenv("KG_RECOMMENDATION_EMBEDDINGS_PATH"),
            "complex_embeddings_all_cac.pkl",
        ),
        recommendation_index_path=_artifact_path(
            os.getenv("KG_RECOMMENDATION_INDEX_PATH"),
            "hnsw_index_complex_model_all_cac.bin",
        ),
        recommendation_embedding_dim=int(os.getenv("KG_RECOMMENDATION_EMBEDDING_DIM", "400")),
        recommendation_index_space=os.getenv("KG_RECOMMENDATION_INDEX_SPACE", "ip"),
        cors_origins=_csv_env("KG_CORS_ORIGINS", DEFAULT_CORS_ORIGINS),
    )


def _artifact_path(override: str | None, filename: str) -> Path:
    if override:
        return Path(override)
    return SOURCE_DATA_DIR / filename


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())
