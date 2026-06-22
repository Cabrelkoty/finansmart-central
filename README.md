# FinanSmart Central

Serveur central pour FinanSmart : source de vérité pour les comptes, les
licences et les paiements de tous les utilisateurs, peu importe leur poste.

⚠️ **Ce code n'a pas pu être exécuté dans l'environnement où il a été
écrit** (pas d'accès réseau pour installer SQLAlchemy/PostgreSQL). Il a été
vérifié syntaxiquement (`py_compile`) et relu attentivement, mais **vous
devez le tester en local avant de déployer en production**, en suivant les
étapes ci-dessous.

## 1. Tester en local

```bash
cd finansmart_central
python3 -m venv venv
source venv/bin/activate          # Windows : venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Ouvrez .env et générez les deux clés avec :
python3 -c "import secrets; print(secrets.token_hex(32))"
# Collez une valeur différente pour FINANSMART_SECRET_KEY,
# FINANSMART_CLIENT_API_KEY et FINANSMART_ADMIN_API_KEY.

python3 app.py
```

Le serveur démarre sur `http://127.0.0.1:8000` avec une base SQLite locale
(`finansmart_central_dev.db`) — pas besoin de PostgreSQL pour développer.

Test rapide :
```bash
curl http://127.0.0.1:8000/sante
# {"ok": true}

curl -X POST http://127.0.0.1:8000/api/comptes/creer \
  -H "Content-Type: application/json" \
  -H "X-API-Key: VOTRE_FINANSMART_CLIENT_API_KEY" \
  -d '{"nom":"Dupont","prenom":"Jean","email":"jean@test.com","password":"Test1234","cle_licence":"FSAAAA-BBBB-CCCC-DDDD"}'
```

## 2. Déployer sur Railway

1. Créez un compte sur [railway.app](https://railway.app).
2. **New Project → Deploy from GitHub repo** (poussez d'abord ce dossier
   `finansmart_central/` dans un repo Git dédié — ne mélangez pas avec le
   reste de FinanSmart).
3. **+ New → Database → PostgreSQL** dans le même projet. Railway injecte
   automatiquement `DATABASE_URL` dans votre service web — vous n'avez rien
   à configurer côté code.
4. Dans l'onglet **Variables** du service web, ajoutez :
   - `FINANSMART_SECRET_KEY`
   - `FINANSMART_CLIENT_API_KEY`
   - `FINANSMART_ADMIN_API_KEY`
   - `FINANSMART_ENV=production`
   (Utilisez des valeurs **différentes** de celles de votre `.env` local.)
5. Railway détecte le `Procfile` et lance `gunicorn` automatiquement.
6. Une fois déployé, Railway vous donne une URL du type
   `https://finansmart-central-production.up.railway.app`. C'est cette URL
   que chaque poste FinanSmart devra utiliser pour synchroniser.

## 3. Et après ?

Ce squelette couvre l'architecture et les routes de base. Reste à faire,
dans une prochaine session :

- **Côté poste client** (`fs/`) : un module `client_sync.py` qui contacte ce
  serveur au démarrage, retombe sur le cache SQLite local si hors-ligne, et
  envoie le `.lseed` de chaque machine vers `/api/licences/migrer-secret`
  lors de la première synchronisation.
- **Le dashboard admin local** : le rebrancher sur `/api/admin-central/*` au
  lieu de ses routes locales `/api/admin/*`.
- **Les paiements Mobile Money** : faire pointer chaque webhook
  (MTN MoMo, Orange Money, etc.) vers `/api/paiements/enregistrer`.
- **Tests automatisés** une fois SQLAlchemy disponible dans l'environnement
  d'exécution.

## Structure du projet

```
finansmart_central/
├── app.py                  # Point d'entrée Flask
├── config.py                # Configuration (variables d'environnement)
├── auth.py                  # Authentification par clé API (client / admin)
├── licence_logic.py         # Génération/validation des clés FS.../FD...
├── models/__init__.py       # Modèles SQLAlchemy (Utilisateur, Machine, ...)
├── routes/
│   ├── comptes.py           # /api/comptes/...
│   ├── licences.py          # /api/licences/...
│   ├── paiements.py         # /api/paiements/...
│   └── admin.py             # /api/admin-central/...
├── requirements.txt
├── Procfile                 # Commande de lancement Railway (gunicorn)
└── .env.example
```
