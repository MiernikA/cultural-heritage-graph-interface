import { isEntityRef, isUserFacingEntity, semanticTypeLabel, shortUri } from "@/entities/entity";
import type { EntityRef, RdfPathStep, RelationshipGroup } from "@/entities/entity";
import type { Language, TFunction, TranslationKey } from "@/shared/i18n";

export type PatternPart = {
  kind: "predicate" | "context";
  label: string;
  uri?: string;
};

export type SemanticPatternGroup = {
  key: string;
  pattern: PatternPart[];
  matches: EntityRef[];
};

export type SemanticRelationGroup = {
  key: string;
  label: string;
  patterns: SemanticPatternGroup[];
};

export function semanticTone(type: string) {
  return type.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

export function filterRelationships(relationships: RelationshipGroup["relationships"], query: string, language: Language, t: TFunction) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return relationships;
  }
  return relationships.filter((relationship) => {
    const haystack = [
      relationship.target.label,
      semanticTypeLabel(relationship.target.semantic_type, t),
      translatedRelationLabel(relationship.display_label, t),
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(normalizedQuery);
  });
}

export function groupTone(label: string) {
  return GROUP_TONES[label] ?? semanticTone(label);
}

export function groupIcon(label: string) {
  return GROUP_ICONS[label] ?? "circle-dot";
}

export function mapTypeLabel(label: string, t: TFunction) {
  const groupKey = RELATIONSHIP_GROUP_KEYS[label];
  if (groupKey) {
    return t(groupKey);
  }
  return semanticTypeLabel(label, t);
}

export function groupSemanticReasoning(relationships: RelationshipGroup["relationships"], language: Language, t: TFunction): SemanticRelationGroup[] {
  const relationMap = new Map<string, SemanticRelationGroup>();
  for (const relationship of relationships) {
    const relationLabel = translatedRelationLabel(relationship.display_label, t);
    const relationKey = relationship.display_label || relationship.relation;
    const pattern = rdfPatternFor(relationship.rdf_path, t);
    const patternKey = pattern.map((part) => `${part.kind}:${part.uri ?? part.label}`).join("|");
    let relationGroup = relationMap.get(relationKey);
    if (!relationGroup) {
      relationGroup = { key: relationKey, label: relationLabel, patterns: [] };
      relationMap.set(relationKey, relationGroup);
    }
    let patternGroup = relationGroup.patterns.find((item) => item.key === patternKey);
    if (!patternGroup) {
      patternGroup = { key: patternKey, pattern, matches: [] };
      relationGroup.patterns.push(patternGroup);
    }
    if (!patternGroup.matches.some((match) => match.uri === relationship.target.uri)) {
      patternGroup.matches.push(relationship.target);
    }
  }
  return Array.from(relationMap.values()).map((relationGroup) => ({
    ...relationGroup,
    patterns: relationGroup.patterns.map((patternGroup) => ({
      ...patternGroup,
      matches: [...patternGroup.matches].sort((a, b) => a.label.localeCompare(b.label, language)),
    })),
  }));
}

export function translatedGroupLabel(label: string, t: TFunction) {
  const key = RELATIONSHIP_GROUP_KEYS[label];
  return key ? t(key) : label;
}

export function translatedRelationLabel(label: string, t: TFunction) {
  const key = RELATIONSHIP_LABEL_KEYS[label];
  return key ? t(key) : label;
}

function rdfPatternFor(path: RdfPathStep[], t: TFunction): PatternPart[] {
  return path.flatMap((step, index) => {
    const parts: PatternPart[] = [
      {
        kind: "predicate",
        label: step.predicate_label || shortUri(step.predicate_uri),
        uri: step.predicate_uri,
      },
    ];
    if (index < path.length - 1 && isEntityRef(step.target) && !isUserFacingEntity(step.target)) {
      parts.push({
        kind: "context",
        label: rdfContextLabel(step.target, t),
        uri: step.target.uri,
      });
    }
    return parts;
  });
}

function rdfContextLabel(entity: EntityRef, t: TFunction) {
  const label = entity.label.trim();
  if (label && !/^(?:https?:\/\/|urn:|cidoc:)/i.test(label) && !/^[A-Z]{1,4}\d+[_-]/.test(label)) {
    return label;
  }
  return semanticTypeLabel(entity.semantic_type, t);
}

const GROUP_TONES: Record<string, string> = {
  Concepts: "concept",
  Events: "event",
  Institutions: "institution",
  Objects: "object",
  People: "person",
  Places: "place",
  Time: "type",
  Types: "type",
};

const GROUP_ICONS: Record<string, string> = {
  Concepts: "tags",
  Events: "clock",
  Institutions: "building-2",
  Objects: "landmark",
  People: "user",
  Places: "map-pin",
  Time: "clock",
  Types: "tag",
};

const RELATIONSHIP_GROUP_KEYS: Record<string, TranslationKey> = {
  Concepts: "relationshipGroup.concepts",
  Events: "relationshipGroup.events",
  Institutions: "relationshipGroup.institutions",
  Objects: "relationshipGroup.objects",
  Other: "relationshipGroup.other",
  People: "relationshipGroup.people",
  Places: "relationshipGroup.places",
  Time: "relationshipGroup.time",
  Types: "semanticType.type",
};

const RELATIONSHIP_LABEL_KEYS: Record<string, TranslationKey> = {
  "active here": "relationshipLabel.activeHere",
  "birth date": "relationshipLabel.birthDate",
  "birthplace of": "relationshipLabel.birthplaceOf",
  "born in": "relationshipLabel.bornIn",
  carries: "relationshipLabel.carries",
  created: "relationshipLabel.created",
  "created by": "relationshipLabel.createdBy",
  "death date": "relationshipLabel.deathDate",
  "death place of": "relationshipLabel.deathPlaceOf",
  "described by": "relationshipLabel.describedBy",
  "direct edge": "relationshipLabel.directEdge",
  "died in": "relationshipLabel.diedIn",
  "earned degree": "relationshipLabel.earnedDegree",
  "field of study": "relationshipLabel.fieldOfStudy",
  "has title": "relationshipLabel.hasTitle",
  "located at": "relationshipLabel.locatedAt",
  "member of": "relationshipLabel.memberOf",
  "participated in": "relationshipLabel.participatedIn",
  "professional role": "relationshipLabel.professionalRole",
  "related place": "relationshipLabel.relatedPlace",
  "shared described context": "relationshipLabel.sharedDescribedContext",
  studied: "relationshipLabel.studied",
  "studied at": "relationshipLabel.studiedAt",
  "title of": "relationshipLabel.titleOf",
  "type of": "relationshipLabel.typeOf",
  "worked as": "relationshipLabel.workedAs",
  "worked at": "relationshipLabel.workedAt",
};
