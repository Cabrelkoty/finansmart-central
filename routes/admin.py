"""
FinanSmart Central — Routes admin

Vue globale sur TOUS les utilisateurs et TOUTES leurs machines, peu importe
où ils se trouvent. C'est la fonctionnalité que le dashboard admin local ne
pouvait pas offrir (il ne voyait que sa propre machine).
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from auth import require_admin_key
from models import Machine, Paiement, Utilisateur, db

bp = Blueprint("admin", __name__, url_prefix="/api/admin-central")


@bp.route("/utilisateurs", methods=["GET"])
@require_admin_key
def lister_utilisateurs():
    q = (request.args.get("q") or "").strip().lower()
    query = Utilisateur.query
    if q:
        query = query.filter(
            db.or_(
                Utilisateur.email.ilike(f"%{q}%"),
                Utilisateur.nom.ilike(f"%{q}%"),
                Utilisateur.prenom.ilike(f"%{q}%"),
            )
        )
    utilisateurs = query.order_by(Utilisateur.date_creation.desc()).all()
    return jsonify({"ok": True, "utilisateurs": [u.to_public_dict() for u in utilisateurs]})


@bp.route("/utilisateurs/<int:utilisateur_id>", methods=["GET"])
@require_admin_key
def detail_utilisateur(utilisateur_id):
    utilisateur = Utilisateur.query.get(utilisateur_id)
    if not utilisateur:
        return jsonify({"ok": False, "erreur": "Utilisateur introuvable."}), 404
    data = utilisateur.to_public_dict()
    data["machines"] = [m.to_dict() for m in utilisateur.machines]
    data["paiements"] = [p.to_dict() for p in utilisateur.paiements]
    return jsonify({"ok": True, "utilisateur": data})


@bp.route("/utilisateurs/<int:utilisateur_id>/statut", methods=["POST"])
@require_admin_key
def changer_statut(utilisateur_id):
    data = request.get_json(silent=True) or {}
    statut = data.get("statut")
    if statut not in ("actif", "suspendu", "expire"):
        return jsonify({"ok": False, "erreur": "Statut invalide."}), 400
    utilisateur = Utilisateur.query.get(utilisateur_id)
    if not utilisateur:
        return jsonify({"ok": False, "erreur": "Utilisateur introuvable."}), 404
    utilisateur.statut = statut
    db.session.commit()
    return jsonify({"ok": True, "utilisateur": utilisateur.to_public_dict()})


@bp.route("/machines/<int:machine_id>/bloquer", methods=["POST"])
@require_admin_key
def bloquer_machine(machine_id):
    machine = Machine.query.get(machine_id)
    if not machine:
        return jsonify({"ok": False, "erreur": "Machine introuvable."}), 404
    machine.statut = "bloquee"
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/statistiques", methods=["GET"])
@require_admin_key
def statistiques():
    maintenant = datetime.now(timezone.utc)
    il_y_a_24h = maintenant - timedelta(hours=24)
    il_y_a_30j = maintenant - timedelta(days=30)

    total_utilisateurs = Utilisateur.query.count()
    actifs = Utilisateur.query.filter_by(statut="actif").count()
    suspendus = Utilisateur.query.filter_by(statut="suspendu").count()
    expires = Utilisateur.query.filter_by(statut="expire").count()

    connectes_24h = (
        Utilisateur.query.filter(Utilisateur.derniere_connexion >= il_y_a_24h).count()
    )
    nouveaux_30j = Utilisateur.query.filter(Utilisateur.date_creation >= il_y_a_30j).count()

    total_machines = Machine.query.count()

    revenus_30j = (
        db.session.query(db.func.coalesce(db.func.sum(Paiement.montant), 0))
        .filter(Paiement.statut == "valide", Paiement.date >= il_y_a_30j)
        .scalar()
    )

    paiements_en_attente = Paiement.query.filter_by(statut="en_attente").count()

    return jsonify(
        {
            "ok": True,
            "statistiques": {
                "total_utilisateurs": total_utilisateurs,
                "actifs": actifs,
                "suspendus": suspendus,
                "expires": expires,
                "connectes_24h": connectes_24h,
                "nouveaux_30j": nouveaux_30j,
                "total_machines": total_machines,
                "revenus_30j": float(revenus_30j or 0),
                "paiements_en_attente": paiements_en_attente,
            },
        }
    )


@bp.route("/paiements", methods=["GET"])
@require_admin_key
def lister_paiements():
    statut = request.args.get("statut")
    query = Paiement.query
    if statut:
        query = query.filter_by(statut=statut)
    paiements = query.order_by(Paiement.date.desc()).limit(200).all()
    return jsonify({"ok": True, "paiements": [p.to_dict() for p in paiements]})
