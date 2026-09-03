from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Neighbor:
    embedding_id: int
    score: float


def query_similar(index: Any, embeddings: Any, embedding_id: int, candidate_count: int) -> list[Neighbor]:
    vector = _embedding_vector(embeddings, embedding_id)
    labels, distances = index.knn_query(vector, k=candidate_count)
    return [
        Neighbor(embedding_id=int(label), score=float(distance))
        for label, distance in zip(labels[0], distances[0], strict=True)
    ]


def _embedding_vector(embeddings: Any, embedding_id: int) -> Any:
    import numpy as np

    row = embeddings.loc[embedding_id] if hasattr(embeddings, "loc") else embeddings[embedding_id]
    if hasattr(embeddings, "columns"):
        dim_columns = [column for column in embeddings.columns if str(column).startswith("dim_")]
        if dim_columns:
            row = row[dim_columns]
    if hasattr(row, "to_numpy"):
        row = row.to_numpy()
    array = np.asarray(row)
    if array.dtype == object and array.size == 1:
        array = np.asarray(array.item())
    if array.dtype == object:
        try:
            array = array.astype("complex64", copy=False)
        except (TypeError, ValueError):
            pass
    if np.iscomplexobj(array):
        array = np.concatenate([array.real, array.imag])
    return array.astype("float32", copy=False).reshape(1, -1)
