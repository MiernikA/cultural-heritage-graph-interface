from __future__ import annotations

from pydantic import BaseModel, Field


class TypeRef(BaseModel):
    uri: str
    label: str


class EntityRef(BaseModel):
    uri: str
    label: str
    semantic_type: str = "Entity"
    icon: str = "circle-dot"
    rdf_types: list[TypeRef] = Field(default_factory=list)


class RecommendationReason(BaseModel):
    type: str
    weight: float
    contribution: float
    rdf_path: list[str] = Field(default_factory=list)


class RdfPathStep(BaseModel):
    source: EntityRef | str
    predicate_uri: str
    predicate_label: str
    target: EntityRef | str


class ExplanationEvidence(BaseModel):
    type: str
    title: str
    description: str
    weight: float
    contribution: float
    rdf_path: list[RdfPathStep] = Field(default_factory=list)


class RecommendationDebugExplanation(BaseModel):
    embedding_contribution: float
    semantic_contribution: float
    rule_weights: dict[str, float] = Field(default_factory=dict)
    raw_rdf_paths: dict[str, list[str]] = Field(default_factory=dict)


class RecommendationExplanation(BaseModel):
    summary: str
    evidence: list[ExplanationEvidence] = Field(default_factory=list)
    debug: RecommendationDebugExplanation


class Recommendation(BaseModel):
    uri: str
    label: str
    semantic_type: str
    icon: str = "circle-dot"
    rdf_types: list[TypeRef] = Field(default_factory=list)
    score: float
    semantic_similarity: float = 0.0
    retrieval_origin: str = "Direct embedding retrieval"
    retrieval_chain: list[EntityRef] = Field(default_factory=list)
    reasons: list[RecommendationReason] = Field(default_factory=list)
    reason_tags: list[str] = Field(default_factory=list)
    explanation: RecommendationExplanation | None = None


class Relationship(BaseModel):
    relation: str
    display_label: str
    direction: str
    symmetric: bool = False
    target: EntityRef
    category: str
    explanation: str = ""
    rdf_path: list[RdfPathStep]
    simplified: bool = False


class RelationshipGroup(BaseModel):
    label: str
    relationships: list[Relationship]


class RawTriple(BaseModel):
    subject: EntityRef | str
    predicate_uri: str
    predicate_label: str
    object: EntityRef | str


class EntityAdvanced(BaseModel):
    uri: str
    raw_triples: list[RawTriple]


class EntityDetail(BaseModel):
    uri: str
    display_name: str
    semantic_type: str
    description: str
    icon: str
    aliases: list[str] = Field(default_factory=list)
    importance: list[str] = Field(default_factory=list)
    rdf_types: list[TypeRef]
    summary: list[str]
    connections: list[RelationshipGroup]
    advanced: EntityAdvanced


class SearchResult(BaseModel):
    uri: str
    label: str
    semantic_type: str
    description: str
    icon: str
    rdf_types: list[TypeRef]
    score: float


class GraphStats(BaseModel):
    nodes: int
    edges: int
    types: int
    predicates: int
