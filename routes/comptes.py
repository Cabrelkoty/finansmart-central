"""
FinanSmart Central — Routes comptes utilisateurs

Équivalent centralisé de comptes.py (logique côté poste client).
Toutes les routes nécessitent la clé API client (voir auth.py).
"""

import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from auth import require_client_key
from models import Machine, Utilisateur, db, hash_password, verifier_password

bp = Blueprint("comptes", __name__, url_prefix="/api/comptes")

_EMAIL_RE = re.compile(r"[^@]+@[^@]+\.[^@]+")


def _email_valide(email: str) -> bool:
    return bool(_EMAIL_RE.match((email or "").strip()))


def _mdp_valide(mdp: str) -> tuple[bool, str]:
    if len(mdp or "") < 8:
        return False, "Le mot de passe doit contenir au moins 8 caractères."
    if not re.search(r"[A-Z]", mdp):
        return False, "Le mot de passe doit contenir au moins une majuscule."
    if not re.search(r"[0-9]", mdp):
        return False, "Le mot de passe doit contenir au moins un chiffre."
    return True, ""


@bp.route("/creer", methods=["POST"])
@require_client_key
def creer_compte():
    data = request.get_json(silent=True) or {}
    nom = (data.get("nom") or "").strip()
    prenom = (data.get("prenom") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    cle_licence = (data.get("cle_licence") or "").strip().upper()
    machine_id = (data.get("machine_id") or "").strip()

    if not nom or not prenom or not email or not password or not cle_licence:
        return jsonify({"ok": False, "erreur": "Tous les champs sont obligatoires."}), 400
    if not _email_valide(email):
        return jsonify({"ok": False, "erreur": "Adresse email invalide."}), 400
    ok_mdp, msg_mdp = _mdp_valide(password)
    if not ok_mdp:
        return jsonify({"ok": False, "erreur": msg_mdp}), 400
    if Utilisateur.query.filter_by(email=email).first():
        return jsonify({"ok": False, "erreur": "Un compte existe déjà avec cet email."}), 409

    utilisateur = Utilisateur(
        nom=nom,
        prenom=prenom,
        email=email,
        hash_mdp=hash_password(password),
        cle_licence=cle_licence,
        statut="actif",
    )
    db.session.add(utilisateur)
    db.session.flush()  # pour obtenir utilisateur.id avant le commit

    if machine_id:
        db.session.add(Machine(utilisateur_id=utilisateur.id, machine_id=machine_id))

    db.session.commit()
    return jsonify({"ok": True, "message": "Compte créé avec succès.", "utilisateur": utilisateur.to_public_dict()})


@bp.route("/connecter", methods=["POST"])
@require_client_key
def connecter():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    machine_id = (data.get("machine_id") or "").strip()

    if not email or not password:
        return jsonify({"ok": False, "erreur": "Email et mot de passe requis."}), 400

    utilisateur = Utilisateur.query.filter_by(email=email).first()
    if not utilisateur or not verifier_password(password, utilisateur.hash_mdp):
        return jsonify({"ok": False, "erreur": "Email ou mot de passe incorrect."}), 401

    if utilisateur.statut != "actif":
        return jsonify({"ok": False, "erreur": "Compte suspendu ou licence expirée.", "statut": utilisateur.statut}), 403

    utilisateur.derniere_connexion = datetime.now(timezone.utc)

    if machine_id:
        machine = Machine.query.filter_by(utilisateur_id=utilisateur.id, machine_id=machine_id).first()
        if not machine:
            machine = Machine(utilisateur_id=utilisateur.id, machine_id=machine_id)
            db.session.add(machine)
        machine.derniere_sync = datetime.now(timezone.utc)
        machine.derniere_ip = request.remote_addr

    db.session.commit()
    return jsonify({"ok": True, "utilisateur": utilisateur.to_public_dict()})


@bp.route("/profil/<email>", methods=["GET"])
@require_client_key
def profil(email):
    """Permet au poste client de rafraîchir l'état d'un compte (ex : licence
    renouvelée depuis un autre poste, ou suspendue par l'admin) sans
    redemander le mot de passe — utilisé pour la synchronisation périodique."""
    utilisateur = Utilisateur.query.filter_by(email=email.strip().lower()).first()
    if not utilisateur:
        return jsonify({"ok": False, "erreur": "Compte introuvable."}), 404
    return jsonify({"ok": True, "utilisateur": utilisateur.to_public_dict()})
