"""
FinanSmart Central — Authentification serveur-à-serveur

Deux niveaux de clé distincts, volontairement séparés :
  - CLIENT_API_KEY : utilisée par CHAQUE poste FinanSmart pour synchroniser
    ses données (comptes, licences, paiements) avec le serveur central.
  - ADMIN_API_KEY : utilisée uniquement par le dashboard admin centralisé,
    qui peut lire/modifier les données de TOUS les utilisateurs. Ne jamais
    réutiliser cette clé dans le logiciel client.
"""

from functools import wraps

from flask import current_app, jsonify, request


def _extraire_cle(req) -> str | None:
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return req.headers.get("X-API-Key")


def require_client_key(view):
    """Protège les routes appelées par les postes clients FinanSmart."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        cle_attendue = current_app.config.get("CLIENT_API_KEY")
        if not cle_attendue:
            return jsonify({"ok": False, "erreur": "Serveur mal configuré : CLIENT_API_KEY absente."}), 500
        cle_recue = _extraire_cle(request)
        if not cle_recue or cle_recue != cle_attendue:
            return jsonify({"ok": False, "erreur": "Clé d'accès client invalide ou manquante."}), 401
        return view(*args, **kwargs)

    return wrapped


def require_admin_key(view):
    """Protège les routes réservées au dashboard admin centralisé."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        cle_attendue = current_app.config.get("ADMIN_API_KEY")
        if not cle_attendue:
            return jsonify({"ok": False, "erreur": "Serveur mal configuré : ADMIN_API_KEY absente."}), 500
        cle_recue = _extraire_cle(request)
        if not cle_recue or cle_recue != cle_attendue:
            return jsonify({"ok": False, "erreur": "Accès admin refusé."}), 401
        return view(*args, **kwargs)

    return wrapped
