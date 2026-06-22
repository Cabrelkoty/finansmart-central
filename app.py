"""
FinanSmart Central — Serveur central

Source de vérité pour les comptes, licences et paiements de TOUS les
utilisateurs FinanSmart, peu importe leur machine. Conçu pour être déployé
sur Railway (ou tout hébergeur compatible Flask + PostgreSQL).

Chaque poste FinanSmart (templates/connexion.html + app.py local) doit
synchroniser avec ce serveur via les routes /api/comptes, /api/licences et
/api/paiements, en utilisant la clé FINANSMART_CLIENT_API_KEY.

Le dashboard admin centralisé utilise les routes /api/admin-central avec
la clé FINANSMART_ADMIN_API_KEY (distincte, plus sensible).
"""

import os

from flask import Flask, jsonify
from flask_cors import CORS

from config import Config
from models import db


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    # CORS : autorise le dashboard admin local (127.0.0.1:5050) et tout
    # autre origin en lecture pour les routes admin-central.
    # En production Railway, le dashboard est servi depuis le poste local
    # donc l'origin varie. On accepte tous les origins sur /api/admin-central
    # car l'authentification repose sur la clé ADMIN_API_KEY, pas sur l'origin.
    CORS(app, resources={
        r"/api/admin-central/*": {"origins": "*"},
        r"/sante": {"origins": "*"},
    })

    from routes.admin import bp as admin_bp
    from routes.comptes import bp as comptes_bp
    from routes.licences import bp as licences_bp
    from routes.paiements import bp as paiements_bp

    app.register_blueprint(comptes_bp)
    app.register_blueprint(licences_bp)
    app.register_blueprint(paiements_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()

    @app.route("/")
    def racine():
        return jsonify({"service": "FinanSmart Central", "statut": "en ligne"})

    @app.route("/sante")
    def sante():
        """Endpoint de vérification de santé, utilisé par Railway et par les
        postes clients pour savoir si le serveur central est joignable avant
        de basculer en mode hors-ligne."""
        try:
            db.session.execute(db.text("SELECT 1"))
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "erreur": str(e)}), 503

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=app.config["DEBUG"])
