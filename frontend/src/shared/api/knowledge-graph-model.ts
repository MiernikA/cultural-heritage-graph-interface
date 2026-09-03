export type TypeRef = {
  uri: string;
  label: string;
};

export type EntityRef = {
  uri: string;
  label: string;
  semantic_type: string;
  icon: string;
  rdf_types: TypeRef[];
};

export type RdfPathStep = {
  source: EntityRef | string;
  predicate_uri: string;
  predicate_label: string;
  target: EntityRef | string;
};

export type Relationship = {
  relation: string;
  display_label: string;
  direction: "outgoing" | "incoming" | "undirected";
  symmetric: boolean;
  target: EntityRef;
  category: string;
  explanation: string;
  rdf_path: RdfPathStep[];
  simplified: boolean;
};

export type RelationshipGroup = {
  label: string;
  relationships: Relationship[];
};

export type RawTriple = {
  subject: EntityRef | string;
  predicate_uri: string;
  predicate_label: string;
  object: EntityRef | string;
};

export type EntityAdvanced = {
  uri: string;
  raw_triples: RawTriple[];
};

export type EntityDetail = {
  uri: string;
  display_name: string;
  semantic_type: string;
  description: string;
  icon: string;
  aliases: string[];
  importance: string[];
  rdf_types: TypeRef[];
  summary: string[];
  connections: RelationshipGroup[];
  advanced: EntityAdvanced;
};

export type Recommendation = {
  uri: string;
  label: string;
  semantic_type: string;
  icon: string;
  rdf_types: TypeRef[];
  score: number;
  semantic_similarity: number;
  retrieval_origin: "Direct embedding retrieval" | "Technical embedding expansion";
  retrieval_chain: EntityRef[];
  reasons: RecommendationReason[];
  reason_tags: string[];
  explanation: RecommendationExplanation | null;
};

export type RecommendationReason = {
  type: string;
  weight: number;
  contribution: number;
  rdf_path: string[];
};

export type ExplanationEvidence = {
  type: string;
  title: string;
  description: string;
  weight: number;
  contribution: number;
  rdf_path: RdfPathStep[];
};

export type RecommendationExplanation = {
  summary: string;
  evidence: ExplanationEvidence[];
};

export type SearchResult = {
  uri: string;
  label: string;
  semantic_type: string;
  description: string;
  icon: string;
  rdf_types: TypeRef[];
  score: number;
};
