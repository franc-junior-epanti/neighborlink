# NeighborLink Backend

API FastAPI autonome et future frontière de confiance de NeighborLink.

```powershell
Copy-Item .env.example .env
docker compose up -d postgres
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload
```

La documentation interactive sera disponible à `http://localhost:8000/docs`.
