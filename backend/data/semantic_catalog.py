from __future__ import annotations

from dataclasses import dataclass

from backend.data.graph.constants import CIDOC
from backend.data.text import local_class_prefix, uri_tail


@dataclass(frozen=True, slots=True)
class SemanticType:
    label: str
    icon: str
    category: str
    description: str
    technical: bool = False


TYPE_BY_URI = {
    CIDOC + "E1_CRM_Entity": SemanticType("Concept", "tag", "Concepts", "A general concept or classification."),
    CIDOC + "E21_Person": SemanticType("Person", "user", "People", "A person represented in the knowledge graph."),
    CIDOC + "E22_Human-Made_Object": SemanticType("Object", "landmark", "Objects", "A physical or bibliographic object."),
    CIDOC + "E39_Actor": SemanticType("Actor", "building", "Institutions", "A person, group, or organization acting in an event."),
    CIDOC + "E52_Time-Span": SemanticType("Time", "clock", "Time", "A time span represented in the knowledge graph."),
    CIDOC + "E53_Place": SemanticType("Place", "map-pin", "Places", "A geographic or named place."),
    CIDOC + "E55_Type": SemanticType("Type", "tags", "Concepts", "A concept used to classify other entities."),
    CIDOC + "E56_Language": SemanticType("Language", "languages", "Concepts", "A language connected with documents or objects."),
    CIDOC + "E74_Group": SemanticType("Institution", "building-2", "Institutions", "A group, institution, or organization."),
}

TYPE_BY_LOCAL_PREFIX = {
    "E21": TYPE_BY_URI[CIDOC + "E21_Person"],
    "E22": TYPE_BY_URI[CIDOC + "E22_Human-Made_Object"],
    "E39": TYPE_BY_URI[CIDOC + "E39_Actor"],
    "E52": TYPE_BY_URI[CIDOC + "E52_Time-Span"],
    "E53": TYPE_BY_URI[CIDOC + "E53_Place"],
    "E55": TYPE_BY_URI[CIDOC + "E55_Type"],
    "E56": TYPE_BY_URI[CIDOC + "E56_Language"],
    "E74": TYPE_BY_URI[CIDOC + "E74_Group"],
    "NE3": SemanticType("Academic degree", "graduation-cap", "Concepts", "An academic title or degree."),
    "NE4": SemanticType("Field of study", "book-open", "Concepts", "A discipline or area of study."),
    "NE5": SemanticType("Professional role", "briefcase-business", "Concepts", "A profession, function, or role."),
    "NE6": SemanticType("Time concept", "clock", "Time", "A time-related concept."),
    "NE8": SemanticType("Role", "badge", "Concepts", "A role or social function."),
}

USER_FACING_SEMANTIC_TYPES = frozenset(
    {
        "Person",
        "Object",
        "Place",
        "Institution",
        "Actor",
        "Type",
        "Academic degree",
        "Field of study",
        "Professional role",
        "Role",
        "Language",
    }
)

TYPE_PRIORITY = (
    CIDOC + "E21_Person",
    CIDOC + "E22_Human-Made_Object",
    CIDOC + "E39_Actor",
    CIDOC + "E52_Time-Span",
    CIDOC + "E53_Place",
    CIDOC + "E55_Type",
    CIDOC + "E56_Language",
    CIDOC + "E74_Group",
    CIDOC + "E1_CRM_Entity",
)

TECHNICAL_LOCAL_PREFIXES = {
    "E12",
    "E33",
    "E35",
    "E41",
    "E65",
    "E67",
    "E69",
    "NE1",
    "NE2",
}

TECHNICAL_URI_TAIL_PREFIXES = {"PC"}

def semantic_type_for(type_uris: set[str], uri: str) -> SemanticType:
    for type_uri in TYPE_PRIORITY:
        if type_uri not in type_uris:
            continue
        semantic_type = TYPE_BY_URI.get(type_uri)
        if semantic_type:
            return semantic_type
    for type_uri in sorted(type_uris):
        semantic_type = TYPE_BY_URI.get(type_uri)
        if semantic_type:
            return semantic_type

    return TYPE_BY_LOCAL_PREFIX.get(local_class_prefix(uri), SemanticType("Entity", "circle-dot", "Other", "A described entity."))


def is_technical_type(type_uris: set[str], uri: str) -> bool:
    prefix = local_class_prefix(uri)
    if prefix in TECHNICAL_LOCAL_PREFIXES:
        return True
    for type_uri in type_uris:
        tail = uri_tail(type_uri)
        if any(tail.startswith(prefix) for prefix in TECHNICAL_URI_TAIL_PREFIXES):
            return True
        semantic_type = TYPE_BY_URI.get(type_uri)
        if semantic_type and semantic_type.technical:
            return True
    return False


def is_user_facing_semantic_type(label: str) -> bool:
    return label in USER_FACING_SEMANTIC_TYPES
