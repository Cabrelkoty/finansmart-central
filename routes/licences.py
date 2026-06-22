"""
FinanSmart Central — Routes licences

Équivalent centralisé du flux d'inscription en 3 étapes existant
(demander-cle → valider-code → finaliser) + renouvellement + migration
des anciens secrets de machine.
"""

import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request

from auth import require_admin_key, require_client_key
from licence_logic import duree_licence, generer_cle_datee, verifier_cle
from models import DemandeCle, Machine, SecretMachine, Utilisateur, db, generer_code, verifier_password

bp = Blueprint("licences", __name__, url_prefix="/api/licences")

_EMAIL_RE = re.compile(r"[^@]+@[^@]+\.[^@]+")
_CODE_DUREE_MIN = 15


@bp.route("/demander-cle", methods=["POST"])
@require_client_key
def demander_cle():
    data = request.get_json(silent=True) or {}
    nom = (data.get("nom") or "").strip()
    prenom = (data.get("prenom") or "").strip()
    email = (data.get("email") or "").strip().lower()
    machine_id = (data.get("machine_id") or "").strip()
    type_cle = data.get("type_cle") or "client"

    if not nom or not prenom or not email or not machine_id:
        return jsonify({"ok": False, "erreur": "Tous les champs sont obligatoires."}), 400
    if not _EMAIL_RE.match(email):
        return jsonify({"ok": False, "erreur": "Adresse email invalide."}), 400
    if Utilisateur.query.filter_by(email=email).first():
        return jsonify({"ok": False, "erreur": "Un compte existe déjà avec cet email."}), 409

    date_exp = (datetime.now(timezone.utc) + duree_licence(type_cle)).date()
    cle = generer_cle_datee(machine_id, date_exp)
    code = generer_code(8)

    demande = DemandeCle(
        nom=nom,
        prenom=prenom,
        email=email,
        machine_id=machine_id,
        type_cle=type_cle,
        cle=cle,
        date_exp=datetime.combine(date_exp, datetime.min.time(), tzinfo=timezone.utc),
        code=code,
        code_expire_at=datetime.now(timezone.utc) + timedelta(minutes=_CODE_DUREE_MIN),
        active=False,
    )
    db.session.add(demande)
    db.session.commit()

    # NOTE : l'envoi d'email reste à brancher sur le service SMTP du serveur
    # central (à faire dans une prochaine étape). En attendant, si SMTP n'est
    # pas configuré, le code est retourné directement comme le fait déjà le
    # système actuel quand SMTP est absent.
    smtp_configure = bool(current_app.config.get("SMTP_HOST"))
    payload = {"ok": True}
    if not smtp_configure:
        payload["code_direct"] = code
    return jsonify(payload)


@bp.route("/valider-code", methods=["POST"])
@require_client_key
def valider_code():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip().upper()

    if not email or not code:
        return jsonify({"ok": False, "erreur": "Email et code requis."}), 400

    demande = (
        DemandeCle.query.filter_by(email=email, active=False)
        .order_by(DemandeCle.id.desc())
        .first()
    )
    if not demande:
        return jsonify({"ok": False, "erreur": "Aucune demande en attente pour cet email."}), 404
    if demande.code_expire_at and demande.code_expire_at < datetime.now(timezone.utc):
        return jsonify({"ok": False, "erreur": "Code expiré. Recommencez la demande."}), 410
    if demande.code != code:
        return jsonify({"ok": False, "erreur": "Code incorrect."}), 401

    demande.active = True
    db.session.commit()

    exp_str = demande.date_exp.strftime("%d/%m/%Y") if demande.date_exp else ""
    return jsonify({"ok": True, "cle_licence": demande.cle, "exp": exp_str})


@bp.route("/renouveler", methods=["POST"])
@require_client_key
def renouveler():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    cle = (data.get("cle") or "").strip().upper()

    if not email or not password or not cle:
        return jsonify({"ok": False, "erreur": "Tous les champs sont obligatoires."}), 400

    utilisateur = Utilisateur.query.filter_by(email=email).first()
    if not utilisateur or not verifier_password(password, utilisateur.hash_mdp):
        return jsonify({"ok": False, "erreur": "Email ou mot de passe incorrect."}), 401

    machine = Machine.query.filter_by(utilisateur_id=utilisateur.id).order_by(Machine.id.desc()).first()
    machine_id = machine.machine_id if machine else ""

    valide, exp_dt = verifier_cle(cle, machine_id)
    if not valide:
        return jsonify({"ok": False, "erreur": "Clé invalide pour cette machine."}), 400

    utilisateur.cle_licence = cle
    utilisateur.statut = "actif"
    utilisateur.date_exp = exp_dt
    db.session.commit()

    return jsonify({"ok": True, "message": "Licence renouvelée avec succès."})


@bp.route("/activer", methods=["POST"])
@require_client_key
def activer():
    """Vérifie une clé pour la machine appelante, sans créer de compte —
    utilisé par l'onglet 'Vérifier Licence'."""
    data = request.get_json(silent=True) or {}
    cle = (data.get("cle") or "").strip().upper()
    machine_id = (data.get("machine_id") or "").strip()

    if not cle or not machine_id:
        return jsonify({"ok": False, "erreur": "Clé et identifiant machine requis."}), 400

    valide, exp_dt = verifier_cle(cle, machine_id)
    if not valide:
        return jsonify({"ok": False, "erreur": "Clé invalide pour cette machine."}), 400

    return jsonify({"ok": True, "exp": exp_dt.strftime("%d/%m/%Y") if exp_dt else None})


@bp.route("/migrer-secret", methods=["POST"])
@require_admin_key
def migrer_secret():
    """Importe le sel (.lseed) historique d'un poste existant, pour que les
    clés FS/FD déjà émises avant le passage au serveur central restent
    valides. Appelé UNE SEULE FOIS par poste, lors de sa première
    synchronisation après mise à jour vers la version compatible serveur
    central. Réservé à la clé admin — jamais accessible aux postes clients
    en libre accès, car cette donnée est hautement sensible."""
    data = request.get_json(silent=True) or {}
    machine_id = (data.get("machine_id") or "").strip().upper()
    sel = (data.get("sel") or "").strip()

    if not machine_id or not sel or len(sel) < 32:
        return jsonify({"ok": False, "erreur": "machine_id et sel (≥32 caractères) requis."}), 400

    existant = SecretMachine.query.filter_by(machine_id=machine_id).first()
    if existant:
        existant.sel = sel
    else:
        db.session.add(SecretMachine(machine_id=machine_id, sel=sel))
    db.session.commit()
    return jsonify({"ok": True, "message": f"Secret migré pour la machine {machine_id}."})
