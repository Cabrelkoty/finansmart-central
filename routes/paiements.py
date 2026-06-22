"""
FinanSmart Central — Routes paiements

Centralise l'historique des paiements (Mobile Money, carte, virement,
validation manuelle admin), peu importe le poste d'où vient la demande.
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from auth import require_admin_key, require_client_key
from models import Paiement, Utilisateur, db

bp = Blueprint("paiements", __name__, url_prefix="/api/paiements")

_METHODES_VALIDES = {
    "mtn_momo",
    "orange_money",
    "moov_flooz",
    "wave",
    "celtis_cash",
    "carte",
    "virement",
    "manuel",
}


@bp.route("/enregistrer", methods=["POST"])
@require_client_key
def enregistrer():
    """Enregistre une tentative de paiement (avant confirmation finale par
    le fournisseur ou par un admin)."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    montant = data.get("montant")
    devise = data.get("devise") or "XOF"
    methode = data.get("methode")
    transaction_id = data.get("transaction_id")

    if not email or montant is None or methode not in _METHODES_VALIDES:
        return jsonify({"ok": False, "erreur": "Champs invalides ou méthode de paiement inconnue."}), 400

    utilisateur = Utilisateur.query.filter_by(email=email).first()

    paiement = Paiement(
        utilisateur_id=utilisateur.id if utilisateur else None,
        email=email,
        montant=montant,
        devise=devise,
        methode=methode,
        transaction_id=transaction_id,
        statut="en_attente",
    )
    db.session.add(paiement)
    db.session.commit()
    return jsonify({"ok": True, "paiement": paiement.to_dict()})


@bp.route("/<int:paiement_id>/valider", methods=["POST"])
@require_admin_key
def valider(paiement_id):
    paiement = Paiement.query.get(paiement_id)
    if not paiement:
        return jsonify({"ok": False, "erreur": "Paiement introuvable."}), 404
    paiement.statut = "valide"
    db.session.commit()
    return jsonify({"ok": True, "paiement": paiement.to_dict()})


@bp.route("/<int:paiement_id>/refuser", methods=["POST"])
@require_admin_key
def refuser(paiement_id):
    paiement = Paiement.query.get(paiement_id)
    if not paiement:
        return jsonify({"ok": False, "erreur": "Paiement introuvable."}), 404
    paiement.statut = "refuse"
    db.session.commit()
    return jsonify({"ok": True, "paiement": paiement.to_dict()})


@bp.route("/utilisateur/<email>", methods=["GET"])
@require_client_key
def historique_utilisateur(email):
    paiements = (
        Paiement.query.filter_by(email=email.strip().lower())
        .order_by(Paiement.date.desc())
        .all()
    )
    return jsonify({"ok": True, "paiements": [p.to_dict() for p in paiements]})
