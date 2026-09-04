# Knowledge Graph Explorer

Rutynowy setup lokalny aplikacji.

## Wymagania

- Python 3
- Node.js i npm
- lokalne dane w `backend/data/source/`

## Dane

Pliki danych nie sa przechowywane w repozytorium. Umiesc je w `backend/data/source/`.

Wymagane pliki:

- `chexrish_onto_prototype2.rdf`
- `complex_entity_to_id_all_cac.pkl`
- `graph_all_cac.tsv`
- `complex_embeddings_all_cac.pkl`
- `hnsw_index_complex_model_all_cac.bin`

Opcjonalnie pobierz dane skryptem:

```powershell
python scripts/download_source_data.py --base-url "https://huggingface.co/datasets/MiernikA/cultural-heritage-graph-data/resolve/main"
```

## Backend

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

API bedzie dostepne pod:

```text
http://127.0.0.1:8001/api
```

## Frontend

W drugim terminalu:

```powershell
cd frontend
npm install
$env:VITE_API_BASE_URL="http://127.0.0.1:8001/api"
npm run dev
```

Frontend bedzie dostepny pod adresem wskazanym przez Vite, zwykle:

```text
http://localhost:5173
```
