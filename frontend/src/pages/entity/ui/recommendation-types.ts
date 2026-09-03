export type RecommendationSortKey = "semantic_type" | "label" | "reason" | "distance";
export type SortDirection = "asc" | "desc";

export type RecommendationSortState = {
  direction: SortDirection;
  key: RecommendationSortKey;
};
