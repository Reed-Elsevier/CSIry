# FastAPI backend

## Setup

```bash
cd backend
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoints

- `GET /` -> welcome message
- `GET /health` -> health check
- `GET /items/{item_id}` -> sample item route
- `POST /items` -> create item example
- `POST /chat` -> chat with the RAG knowledge base and configured LLM

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```
