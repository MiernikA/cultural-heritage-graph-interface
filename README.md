# Knowledge Graph Explorer

## English

### About this project

This repository contains the application developed for Adrian Miernik's master's thesis:

> **Project and implementation of an exploratory interface for cultural heritage using knowledge graphs and explainable recommendations**
>
> Jagiellonian University in Kraków, Faculty of Physics, Astronomy and Applied Computer Science, 2026

The application is an exploratory interface for cultural heritage data represented as a knowledge graph. It enables users to search for entities, inspect their semantic relationships, move between connected resources, and receive recommendations supported by human-readable explanations and RDF evidence paths.

The system consists of:

- a Python and FastAPI backend that loads the knowledge graph, ontology, ComplEx embeddings, and HNSW index;
- a React and TypeScript frontend for searching and exploring entities;
- a recommendation mechanism combining vector similarity with semantic relationships found in the graph;
- standard and expert views, including relationship maps, grouped connections, recommendation explanations, and source RDF details.

### Source data

The source data and recommendation artifacts are **not stored in this GitHub repository**. The complete dataset is several gigabytes in size, and individual files exceed GitHub's regular file-size limit.

Download the data from:

<https://huggingface.co/datasets/MiernikA/cultural-heritage-graph-data>

Place the following files in `backend/data/source/`:

```text
backend/data/source/
├── chexrish_onto_prototype2.rdf
├── complex_embeddings_all_cac.pkl
├── complex_entity_to_id_all_cac.pkl
├── graph_all_cac.tsv
└── hnsw_index_complex_model_all_cac.bin
```

The backend will not start correctly without the graph and ontology files. Recommendation endpoints additionally require the embedding files and HNSW index.

### Requirements

- Python 3.12 or a compatible Python 3 version
- Node.js and npm
- the five source-data files listed above

### Running the application locally

Clone the repository and enter its directory:

```powershell
git clone https://github.com/MiernikA/cultural-heritage-graph-interface.git
cd cultural-heritage-graph-interface
```

Download the source data and copy all five files to `backend/data/source/` before starting the backend.

#### 1. Start the backend

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

On Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

The API will be available at `http://127.0.0.1:8001/api`. Verify the backend at:

```text
http://127.0.0.1:8001/api/health
```

#### 2. Start the frontend

Open a second terminal and run:

```powershell
cd frontend
npm install
$env:VITE_API_BASE_URL="http://127.0.0.1:8001/api"
npm run dev
```

On Linux or macOS, set the variable with:

```bash
export VITE_API_BASE_URL="http://127.0.0.1:8001/api"
```

The frontend will normally be available at `http://localhost:5173`. The API address above is also the frontend's default, so setting `VITE_API_BASE_URL` can be omitted when the backend is running on port `8001`.

### Optional backend configuration

The default data directory can be changed with `KG_SOURCE_DATA_DIR`. Individual paths can also be configured with:

- `KG_GRAPH_TSV_PATH`
- `KG_ONTOLOGY_RDF_PATH`
- `KG_RECOMMENDATION_ENTITY_TO_ID_PATH`
- `KG_RECOMMENDATION_EMBEDDINGS_PATH`
- `KG_RECOMMENDATION_INDEX_PATH`
- `KG_CORS_ORIGINS`

### Production build

```powershell
cd frontend
npm install
npm run build
```

The generated files will be placed in `frontend/dist/`.

---

## Polski

### O projekcie

Repozytorium zawiera aplikację przygotowaną w ramach pracy magisterskiej Adriana Miernika:

> **Projekt i implementacja eksploracyjnego interfejsu dla dziedzictwa kulturowego z wykorzystaniem grafów wiedzy oraz mechanizmów explainable recommendations**
>
> Uniwersytet Jagielloński w Krakowie, Wydział Fizyki, Astronomii i Informatyki Stosowanej, 2026

Aplikacja jest eksploracyjnym interfejsem do danych dziedzictwa kulturowego reprezentowanych w postaci grafu wiedzy. Umożliwia wyszukiwanie encji, analizowanie ich relacji semantycznych, przechodzenie pomiędzy powiązanymi zasobami oraz korzystanie z rekomendacji uzupełnionych o czytelne wyjaśnienia i źródłowe ścieżki RDF.

System składa się z:

- backendu Python i FastAPI, który wczytuje graf wiedzy, ontologię, reprezentacje ComplEx i indeks HNSW;
- frontendu React i TypeScript służącego do wyszukiwania i eksplorowania encji;
- mechanizmu rekomendacyjnego łączącego podobieństwo wektorowe z relacjami semantycznymi odnalezionymi w grafie;
- widoku standardowego i eksperckiego, obejmujących mapę relacji, pogrupowane powiązania, wyjaśnienia rekomendacji oraz źródłowe informacje RDF.

### Dane źródłowe

Dane źródłowe i artefakty rekomendacyjne **nie są przechowywane w tym repozytorium GitHub**. Pełny zbiór ma rozmiar kilku gigabajtów, a niektóre pojedyncze pliki przekraczają standardowy limit rozmiaru pliku w GitHub.

Dane można pobrać z:

<https://huggingface.co/datasets/MiernikA/cultural-heritage-graph-data>

Następujące pliki należy umieścić w `backend/data/source/`:

```text
backend/data/source/
├── chexrish_onto_prototype2.rdf
├── complex_embeddings_all_cac.pkl
├── complex_entity_to_id_all_cac.pkl
├── graph_all_cac.tsv
└── hnsw_index_complex_model_all_cac.bin
```

Backend nie uruchomi się prawidłowo bez plików grafu i ontologii. Endpointy rekomendacyjne wymagają dodatkowo reprezentacji wektorowych oraz indeksu HNSW.

### Wymagania

- Python 3.12 lub zgodna wersja Python 3
- Node.js i npm
- pięć wymienionych wyżej plików danych źródłowych

### Lokalne uruchomienie aplikacji

Sklonuj repozytorium i przejdź do jego katalogu:

```powershell
git clone https://github.com/MiernikA/cultural-heritage-graph-interface.git
cd cultural-heritage-graph-interface
```

Przed uruchomieniem backendu pobierz dane źródłowe i skopiuj wszystkie pięć plików do `backend/data/source/`.

#### 1. Uruchomienie backendu

W Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

W systemie Linux lub macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

API będzie dostępne pod adresem `http://127.0.0.1:8001/api`. Poprawne działanie backendu można sprawdzić pod adresem:

```text
http://127.0.0.1:8001/api/health
```

#### 2. Uruchomienie frontendu

Otwórz drugi terminal i wykonaj:

```powershell
cd frontend
npm install
$env:VITE_API_BASE_URL="http://127.0.0.1:8001/api"
npm run dev
```

W systemie Linux lub macOS zmienną można ustawić poleceniem:

```bash
export VITE_API_BASE_URL="http://127.0.0.1:8001/api"
```

Frontend będzie zwykle dostępny pod adresem `http://localhost:5173`. Powyższy adres API jest również domyślną wartością frontendu, dlatego ustawienie `VITE_API_BASE_URL` można pominąć, jeżeli backend działa na porcie `8001`.

### Opcjonalna konfiguracja backendu

Domyślny katalog danych można zmienić za pomocą `KG_SOURCE_DATA_DIR`. Dostępne są również ustawienia osobnych ścieżek:

- `KG_GRAPH_TSV_PATH`
- `KG_ONTOLOGY_RDF_PATH`
- `KG_RECOMMENDATION_ENTITY_TO_ID_PATH`
- `KG_RECOMMENDATION_EMBEDDINGS_PATH`
- `KG_RECOMMENDATION_INDEX_PATH`
- `KG_CORS_ORIGINS`

### Build produkcyjny

```powershell
cd frontend
npm install
npm run build
```

Wygenerowane pliki zostaną zapisane w `frontend/dist/`.
