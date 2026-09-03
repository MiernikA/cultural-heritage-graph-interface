from __future__ import annotations

from fastapi import Request

from backend.exploration.service import ExplorerService
from backend.recommendations.service import RecommendationService


def get_explorer(request: Request) -> ExplorerService:
    return request.app.state.context.explorer


def get_recommendations(request: Request) -> RecommendationService:
    return request.app.state.context.recommendations
