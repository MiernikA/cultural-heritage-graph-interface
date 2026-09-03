import type { EntityRef, Recommendation, SearchResult } from "@/shared/api";
import type { TFunction, TranslationKey } from "@/shared/i18n";

const USER_FACING_SEMANTIC_TYPES = new Set([
  "Person",
  "Object",
  "Place",
  "Event",
  "Institution",
  "Actor",
  "Type",
  "Academic degree",
  "Field of study",
  "Professional role",
  "Role",
  "Language",
]);

const SEMANTIC_TYPE_KEYS: Record<string, TranslationKey> = {
  "Academic degree": "semanticType.academicDegree",
  Actor: "semanticType.actor",
  "Field of study": "semanticType.fieldOfStudy",
  Institution: "semanticType.institution",
  Language: "semanticType.language",
  Object: "semanticType.object",
  Person: "semanticType.person",
  Place: "semanticType.place",
  "Professional role": "semanticType.professionalRole",
  Role: "semanticType.role",
  Type: "semanticType.type",
};

const SEMANTIC_DESCRIPTION_KEYS: Record<string, TranslationKey> = {
  "Academic degree": "semanticDescription.academicDegree",
  Actor: "semanticDescription.actor",
  "Field of study": "semanticDescription.fieldOfStudy",
  Institution: "semanticDescription.institution",
  Language: "semanticDescription.language",
  Object: "semanticDescription.object",
  Person: "semanticDescription.person",
  Place: "semanticDescription.place",
  "Professional role": "semanticDescription.professionalRole",
  Role: "semanticDescription.role",
  Type: "semanticDescription.type",
};

export function isUserFacingType(type: string) {
  return USER_FACING_SEMANTIC_TYPES.has(type);
}

export function isUserFacingEntity(entity: EntityRef | Recommendation | SearchResult) {
  return isUserFacingType(entity.semantic_type);
}

export function semanticTypeLabel(type: string, t: TFunction) {
  const key = SEMANTIC_TYPE_KEYS[type];
  return key ? t(key) : type;
}

export function semanticDescription(type: string, fallback: string, t: TFunction) {
  const key = SEMANTIC_DESCRIPTION_KEYS[type];
  return key ? t(key) : fallback;
}
