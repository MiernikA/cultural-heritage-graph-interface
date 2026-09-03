from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from backend.data.graph.constants import RDF_TYPE, RDFS_LABEL
from backend.data.ontology.models import Ontology, OntologyTerm
from backend.data.text import compact_text

RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"

RDF_ABOUT = f"{{{RDF_NS}}}about"
RDF_RESOURCE = f"{{{RDF_NS}}}resource"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
RDFS_LABEL_TAG = f"{{{RDFS_NS}}}label"
RDF_TYPE_TAG = f"{{{RDF_NS}}}type"


def load_ontology(path: Path) -> Ontology:
    terms: dict[str, OntologyTerm] = {}

    for _event, elem in ET.iterparse(path, events=("end",)):
        if not elem.tag.endswith("Description"):
            continue

        uri = elem.attrib.get(RDF_ABOUT)
        if not uri:
            elem.clear()
            continue

        labels_with_lang: list[tuple[int, str]] = []
        term_type: str | None = None

        for child in elem:
            if child.tag == RDFS_LABEL_TAG and child.text:
                label = compact_text(child.text)
                if label:
                    labels_with_lang.append((_language_priority(child.attrib.get(XML_LANG)), label))
            elif child.tag == RDF_TYPE_TAG:
                term_type = child.attrib.get(RDF_RESOURCE) or term_type

        labels = _unique_labels([label for _priority, label in sorted(labels_with_lang, key=lambda item: item[0])])
        if labels or term_type:
            terms[uri] = OntologyTerm(uri=uri, labels=labels, term_type=term_type)

        elem.clear()

    return Ontology(terms=terms)


def ontology_label_triples(ontology: Ontology) -> list[tuple[str, str, str]]:
    triples: list[tuple[str, str, str]] = []
    for uri, term in ontology.terms.items():
        for label in term.labels:
            triples.append((uri, RDFS_LABEL, label))
        if term.term_type:
            triples.append((uri, RDF_TYPE, term.term_type))
    return triples


def _language_priority(lang: str | None) -> int:
    if lang == "pl":
        return 0
    if lang == "en":
        return 1
    if lang is None:
        return 2
    return 3


def _unique_labels(labels: list[str]) -> list[str]:
    unique: list[str] = []
    for label in labels:
        if label not in unique:
            unique.append(label)
    return unique
