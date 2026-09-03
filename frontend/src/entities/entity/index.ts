export type {
  EntityAdvanced,
  EntityDetail,
  EntityRef,
  ExplanationEvidence,
  RawTriple,
  RdfPathStep,
  Recommendation,
  RecommendationExplanation,
  RecommendationReason,
  Relationship,
  RelationshipGroup,
  SearchResult,
  TypeRef,
} from "@/shared/api";
export type { FeaturedEntity } from "./model/featured-entities";
export { FEATURED_ENTITIES, GRAPH_STATS } from "./model/featured-entities";
export {
  isUserFacingEntity,
  isUserFacingType,
  semanticDescription,
  semanticTypeLabel,
} from "./model/semantic-rules";
export { isEntityRef, shortUri } from "./lib/entity-ref";
