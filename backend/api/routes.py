from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.dependencies import get_explorer, get_recommendations
from backend.data.schemas import (
    EntityDetail,
    GraphStats,
    Recommendation,
    SearchResult,
)
from backend.exploration.service import ExplorerService
from backend.recommendations.loader import RecommendationArtifactError
from backend.recommendations.service import RecommendationService

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/stats", response_model=GraphStats)
def stats(explorer: ExplorerService = Depends(get_explorer)) -> dict[str, int]:
    return explorer.stats()


@router.get("/search", response_model=list[SearchResult])
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=100),
    explorer: ExplorerService = Depends(get_explorer),
) -> list[SearchResult]:
    return explorer.search(q, limit)


@router.get("/entities/{entity_uri:path}", response_model=EntityDetail)
def get_entity(entity_uri: str, explorer: ExplorerService = Depends(get_explorer)) -> EntityDetail:
    return _get_entity(entity_uri, explorer)


@router.get("/entity", response_model=EntityDetail)
def get_entity_by_query(uri: str = Query(..., min_length=1), explorer: ExplorerService = Depends(get_explorer)) -> EntityDetail:
    return _get_entity(uri, explorer)


@router.get("/recommendations", response_model=list[Recommendation])
def recommendations(
    uri: str = Query(..., min_length=1),
    limit: int | None = Query(None, ge=1),
    service: RecommendationService = Depends(get_recommendations),
) -> list[Recommendation]:
    try:
        return service.recommend_for_entity(uri, limit)
    except RecommendationArtifactError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/recommendations/featured", response_model=list[Recommendation])
def featured_recommendations(
    uri: str = Query(..., min_length=1),
    service: RecommendationService = Depends(get_recommendations),
) -> list[Recommendation]:
    try:
        return service.featured_recommendations_for_entity(uri)
    except RecommendationArtifactError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _get_entity(entity_uri: str, explorer: ExplorerService) -> EntityDetail:
    entity = explorer.get_entity(entity_uri)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity
