from __future__ import annotations

import pickle
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Iterator


class RecommendationArtifactError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecommendationArtifacts:
    entity_to_id_path: Path
    embeddings_path: Path
    index_path: Path
    embedding_dim: int
    index_space: str

    @cached_property
    def entity_to_id(self) -> dict[str, int]:
        _require_file(self.entity_to_id_path)
        loaded = _load_mapping(self.entity_to_id_path)
        if not isinstance(loaded, dict):
            raise RecommendationArtifactError(f"Entity mapping must be a dict, got {type(loaded).__name__}")
        return {str(label): int(embedding_id) for label, embedding_id in loaded.items()}

    @cached_property
    def id_to_entity(self) -> dict[int, str]:
        return {embedding_id: label for label, embedding_id in self.entity_to_id.items()}

    @cached_property
    def embedding_metadata(self) -> dict[int, tuple[str, str]]:
        if not _has_columns(self.embeddings, {"id", "emb_name", "uri_or_ref"}):
            return {}

        metadata: dict[int, tuple[str, str]] = {}
        for row in self.embeddings[["id", "emb_name", "uri_or_ref"]].itertuples(index=False):
            metadata[int(row.id)] = (str(row.emb_name), str(row.uri_or_ref))
        return metadata

    @cached_property
    def embedding_ids_by_uri(self) -> dict[str, list[int]]:
        ids_by_uri: dict[str, list[int]] = {}
        for embedding_id, (_, uri_or_ref) in self.embedding_metadata.items():
            ids_by_uri.setdefault(uri_or_ref, []).append(embedding_id)
        return ids_by_uri

    @cached_property
    def embeddings(self) -> Any:
        _require_file(self.embeddings_path)
        try:
            import pandas as pd
        except ImportError as exc:
            raise RecommendationArtifactError(
                "Recommendation embeddings require pandas and numpy. Install project requirements first."
            ) from exc
        try:
            return pd.read_pickle(self.embeddings_path)
        except Exception as exc:
            try:
                return _read_legacy_pandas_pickle(self.embeddings_path)
            except Exception as fallback_exc:
                raise RecommendationArtifactError(
                    f"Could not load recommendation embeddings from {self.embeddings_path}: {_safe_error(fallback_exc)}"
                ) from fallback_exc

    @cached_property
    def index(self) -> Any:
        _require_file(self.index_path)
        try:
            import hnswlib
        except ImportError as exc:
            raise RecommendationArtifactError("Recommendation search requires hnswlib. Install project requirements first.") from exc

        index = hnswlib.Index(space=self.index_space, dim=self.embedding_dim)
        try:
            index.load_index(str(self.index_path))
            index.set_ef(50)
        except Exception as exc:
            raise RecommendationArtifactError(
                f"Could not load HNSW recommendation index from {self.index_path}: {_safe_error(exc)}"
            ) from exc
        return index


def _require_file(path: Path) -> None:
    if not path.exists():
        raise RecommendationArtifactError(f"Recommendation artifact not found: {path}")


def _load_mapping(path: Path) -> object:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            data_members = [name for name in archive.namelist() if name.endswith("/data.pkl")]
            if len(data_members) != 1:
                raise RecommendationArtifactError(f"Unexpected Torch checkpoint layout in {path}")
            return pickle.loads(archive.read(data_members[0]))

    with path.open("rb") as handle:
        return pickle.load(handle)


def _has_columns(value: Any, columns: set[str]) -> bool:
    return hasattr(value, "columns") and columns.issubset(set(str(column) for column in value.columns))


def _read_legacy_pandas_pickle(path: Path) -> Any:
    import numpy as np
    from pandas.arrays import StringArray

    def unpickle_array(cls: type, checksum: int, state: object) -> object:
        if cls is StringArray:
            return StringArray(np.array([], dtype=object))
        import pandas._libs.arrays as arrays

        return arrays.__pyx_unpickle_NDArrayBacked(cls, checksum, state)

    class LegacyPandasUnpickler(pickle.Unpickler):
        def find_class(self, module: str, name: str) -> object:
            if module == "pandas._libs.arrays" and name == "__pyx_unpickle_NDArrayBacked":
                return unpickle_array
            return super().find_class(module, name)

    with _patched_string_array_setstate():
        with path.open("rb") as handle:
            return LegacyPandasUnpickler(handle).load()


@contextmanager
def _patched_string_array_setstate() -> Iterator[None]:
    from pandas.arrays import StringArray

    original_setstate = StringArray.__setstate__

    def setstate(self: StringArray, state: object) -> None:
        if isinstance(state, tuple) and len(state) == 2:
            StringArray.__init__(self, state[1])
            return
        original_setstate(self, state)

    StringArray.__setstate__ = setstate
    try:
        yield
    finally:
        StringArray.__setstate__ = original_setstate


def _safe_error(exc: Exception) -> str:
    message = ascii(str(exc))
    if len(message) > 320:
        message = message[:317] + "..."
    return f"{type(exc).__name__}: {message}"
