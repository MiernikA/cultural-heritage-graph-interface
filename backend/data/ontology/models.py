from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class OntologyTerm:
    uri: str
    labels: list[str] = field(default_factory=list)
    term_type: str | None = None


@dataclass(slots=True)
class Ontology:
    terms: dict[str, OntologyTerm]

    def label_for(self, uri: str) -> str | None:
        term = self.terms.get(uri)
        if not term or not term.labels:
            return None
        return term.labels[0]
