# NeighborLink Frontend

Application React + TypeScript autonome.

```powershell
npm install
npm run dev
npm test
npm run build
```

Le déploiement Amplify devra cibler ce dossier comme racine applicative.

Copier `.env.example` vers `.env`. Le mode `local` sert uniquement au développement ; pour AWS, utiliser `VITE_AUTH_MODE=cognito` et renseigner le User Pool et l'App Client Cognito.
