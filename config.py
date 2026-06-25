"""
FinanSmart Central — Configuration
Toutes les valeurs sensibles viennent des variables d'environnement.
Sur Railway, elles sont définies dans l'onglet "Variables" du service.
"""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

# Charge le fichier .env (s'il existe) dans les variables d'environnement.
# Le fichier est rangé un niveau au-dessus de finansmart_central/ (dans fs/)
# pour éviter qu'il se retrouve par erreur dans le dossier suivi par Git ou
# synchronisé avec un cloud. En production sur Railway, ce fichier n'existe
# pas — les variables sont déjà injectées directement par la plateforme,
# load_dotenv() ne fait alors rien (sans erreur).
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH)
else:
    # Repli sur le comportement par défaut (recherche automatique), au cas où
    # quelqu'un remettrait un .env directement dans finansmart_central/.
    load_dotenv()


def _required(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None:
        raise RuntimeError(
            f"Variable d'environnement obligatoire manquante : {name}. "
            f"Définissez-la dans les Variables Railway (ou un fichier .env en local)."
        )
    return val


def _env_ou(name: str, default: str = "") -> str:
    """Comme os.environ.get, mais traite une valeur vide ('') comme absente.
    Utile car un .env contenant 'DATABASE_URL=' (sans valeur) renvoie une
    chaîne vide, pas None — os.environ.get(...) ignorerait alors la valeur
    par défaut prévue pour ce cas."""
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    return val


class Config:
    # ── Base de données ──────────────────────────────────────────────────────
    # Railway injecte automatiquement DATABASE_URL quand un plugin PostgreSQL
    # est attaché au service. En local, on retombe sur SQLite pour développer
    # sans avoir besoin d'un PostgreSQL local.
    SQLALCHEMY_DATABASE_URI = _env_ou(
        "DATABASE_URL", "sqlite:///finansmart_central_dev.db"
    ).replace("postgres://", "postgresql://", 1)  # Railway donne parfois l'ancien préfixe
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Sécurité ──────────────────────────────────────────────────────────────
    # Clé de signature des JWT (sessions admin / utilisateurs côté serveur).
    SECRET_KEY = _env_ou("FINANSMART_SECRET_KEY") or secrets.token_hex(32)

    # Clé API que CHAQUE poste FinanSmart utilise pour s'authentifier auprès
    # de ce serveur central. Doit être identique à celle configurée dans
    # CENTRAL_API_KEY sur les postes clients (voir client_sync.py).
    # En production, définissez-la explicitement dans Railway — ne pas laisser
    # la valeur générée à chaud, sinon elle change à chaque redéploiement et
    # tous les clients perdent l'accès.
    CLIENT_API_KEY = _env_ou("FINANSMART_CLIENT_API_KEY") or None

    # Clé séparée et plus sensible pour le dashboard admin centralisé.
    ADMIN_API_KEY = _env_ou("FINANSMART_ADMIN_API_KEY") or None

    # ── Divers ────────────────────────────────────────────────────────────────
    ENV = _env_ou("FINANSMART_ENV", "production")
    DEBUG = ENV == "development"
