# NeighborLink

> Coordinate people. Strengthen communities.

NeighborLink est organisé en deux applications indépendantes :

- [`frontend/`](./frontend/README.md) : React + TypeScript, destiné à AWS Amplify.
- [`backend/`](./backend/README.md) : FastAPI, destiné à un conteneur AWS App Runner.

Leur contrat sera HTTP/JSON via OpenAPI. Chaque dossier possède ses propres dépendances, scripts, tests et instructions de déploiement.

## Développement local

Chaque application contient sa propre configuration. Suivre les README de `backend/` et `frontend/` dans deux terminaux ; PostgreSQL et l'exemple d'environnement se trouvent dans `backend/`.

Git reste entièrement sous le contrôle du propriétaire du projet.
