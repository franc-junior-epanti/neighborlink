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

## Base de données

```powershell
docker compose up -d postgres
alembic upgrade head
```

Toutes les données locataires portent `organization_id`. Les migrations Alembic utilisent `DATABASE_URL` depuis `.env`.

## Coordinateur initial

Après création de l'utilisateur Cognito, rattacher son `sub` à l'association locale avec `scripts/bootstrap_coordinator.py`. Le script est idempotent et ne prend aucun mot de passe.

## AgentCore Runtime

La configuration de déploiement vit dans `agentcore/`. Le point d'entrée AWS est
`agent/runtime.py`; il utilise le même contrat Pydantic et le même workflow que
l'adaptateur local.

Prérequis : AWS CLI avec le profil `perso`, Node.js, le CLI `@aws/agentcore` et `uv`.

```powershell
$env:AWS_PROFILE = "perso"
$env:AWS_REGION = "us-east-1"
agentcore validate
agentcore package --runtime NeighborLinkRuntime
agentcore deploy --dry-run -y
agentcore deploy -y
```

L'exemple `agentcore/invoke-douala.json` permet un smoke test structuré. Après le
déploiement, récupérer l'ARN avec `agentcore status --runtime NeighborLinkRuntime --json`,
puis renseigner `AGENT_RUNTIME_MODE=agentcore` et `AGENT_RUNTIME_ARN` dans l'environnement
FastAPI. Conserver `AGENT_RUNTIME_MODE=local` pour le développement sans appel AWS.
