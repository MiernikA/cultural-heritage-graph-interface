# Knowledge Graph Explorer

Aplikacja przygotowana jako czesc pracy magisterskiej.

## Uruchomienie

Backend:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

Frontend:

```powershell
cd frontend
npm install
$env:VITE_API_BASE_URL="http://127.0.0.1:8001/api"
npm run dev
```

Wymagane dane lokalne znajduja sie w `backend/data/source/`.

Pliki danych nie sa przechowywane w repozytorium aplikacji. Najprostszy wariant deploymentu:

1. Umiesc dane w osobnym hostingu, np. Hugging Face Dataset.
2. Na serwerze backendu pobierz je do `backend/data/source/`.

```powershell
python scripts/download_source_data.py --base-url "https://huggingface.co/datasets/MiernikA/cultural-heritage-graph-data/resolve/main"
```

Wymagane pliki:

- `chexrish_onto_prototype2.rdf`
- `complex_entity_to_id_all_cac.pkl`
- `graph_all_cac.tsv`
- `complex_embeddings_all_cac.pkl`
- `hnsw_index_complex_model_all_cac.bin`
