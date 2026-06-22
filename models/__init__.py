"""
FinanSmart Central — Modèles de données

Reprend la même logique de hash de mot de passe que le client local
(PBKDF2-HMAC-SHA256, 600 000 itérations) afin que les comptes migrés depuis
les bases SQLite locales (comptes.db) restent valides sans forcer un reset
de mot de passe pour tout le monde.
"""

import hashlib
import os
import secrets
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

_PBKDF2_ITER = 600_000


def hash_password(password: str) -> str:
    sel = os.urandom(32)
    hash_b = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), sel, _PBKDF2_ITER)
    return sel.hex() + ":" + hash_b.hex()


def verifier_password(password: str, stored: str) -> bool:
    try:
        if ":" not in stored:
            # Compatibilité avec d'anciens hash SHA-256 nu, le cas échéant.
            return hashlib.sha256(password.encode("utf-8")).hexdigest() == stored
        sel_hex, hash_hex = stored.split(":", 1)
        hash_b = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(sel_hex), _PBKDF2_ITER
        )
        return hash_b.hex() == hash_hex
    except Exception:
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Utilisateur(db.Model):
    """Compte FinanSmart — un par personne, indépendamment du nombre de
    machines sur lesquelles elle se connecte."""

    __tablename__ = "utilisateurs"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    prenom = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    hash_mdp = db.Column(db.String(255), nullable=False)

    cle_licence = db.Column(db.String(64), nullable=False, index=True)
    type_cle = db.Column(db.String(32), default="client")
    statut = db.Column(db.String(32), default="actif")  # actif | suspendu | expire
    date_creation = db.Column(db.DateTime, default=_now)
    date_exp = db.Column(db.DateTime, nullable=True)
    derniere_connexion = db.Column(db.DateTime, nullable=True)

    machines = db.relationship(
        "Machine", backref="utilisateur", lazy=True, cascade="all, delete-orphan"
    )
    paiements = db.relationship(
        "Paiement", backref="utilisateur", lazy=True, cascade="all, delete-orphan"
    )

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "nom": self.nom,
            "prenom": self.prenom,
            "email": self.email,
            "cle_licence": self.cle_licence,
            "type_cle": self.type_cle,
            "statut": self.statut,
            "date_creation": self.date_creation.isoformat() if self.date_creation else None,
            "date_exp": self.date_exp.isoformat() if self.date_exp else None,
            "derniere_connexion": self.derniere_connexion.isoformat()
            if self.derniere_connexion
            else None,
            "nb_machines": len(self.machines),
        }


class Machine(db.Model):
    """Un poste physique sur lequel FinanSmart est installé. Un utilisateur
    peut avoir plusieurs machines (selon ce que la licence autorise)."""

    __tablename__ = "machines"

    id = db.Column(db.Integer, primary_key=True)
    utilisateur_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=False)
    machine_id = db.Column(db.String(255), nullable=False, index=True)
    nom_machine = db.Column(db.String(255), nullable=True)  # nom d'hôte, facultatif
    derniere_sync = db.Column(db.DateTime, nullable=True)
    version_logiciel = db.Column(db.String(32), nullable=True)
    derniere_ip = db.Column(db.String(64), nullable=True)
    statut = db.Column(db.String(32), default="active")  # active | bloquee

    __table_args__ = (db.UniqueConstraint("utilisateur_id", "machine_id", name="uq_user_machine"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "machine_id": self.machine_id,
            "nom_machine": self.nom_machine,
            "derniere_sync": self.derniere_sync.isoformat() if self.derniere_sync else None,
            "version_logiciel": self.version_logiciel,
            "statut": self.statut,
        }


class DemandeCle(db.Model):
    """Demande de création de compte en attente de validation par code email
    (étape 1 → 2 du flux d'inscription)."""

    __tablename__ = "demandes_cle"

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=_now)
    nom = db.Column(db.String(120))
    prenom = db.Column(db.String(120))
    email = db.Column(db.String(255), index=True)
    machine_id = db.Column(db.String(255))
    type_cle = db.Column(db.String(32))
    cle = db.Column(db.String(64))
    date_exp = db.Column(db.DateTime, nullable=True)
    code = db.Column(db.String(16))
    code_expire_at = db.Column(db.DateTime, nullable=True)
    active = db.Column(db.Boolean, default=False)


class Paiement(db.Model):
    """Historique des paiements (Mobile Money, carte, virement, validation
    manuelle admin) — centralisé pour avoir une vue globale sur tous les
    utilisateurs, peu importe leur poste."""

    __tablename__ = "paiements"

    id = db.Column(db.Integer, primary_key=True)
    utilisateur_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=True)
    email = db.Column(db.String(255), index=True)
    date = db.Column(db.DateTime, default=_now)
    montant = db.Column(db.Numeric(12, 2), nullable=False)
    devise = db.Column(db.String(8), default="XOF")
    methode = db.Column(db.String(32))  # mtn_momo | orange_money | moov_flooz | wave | celtis_cash | carte | virement | manuel
    transaction_id = db.Column(db.String(255), nullable=True)
    statut = db.Column(db.String(32), default="en_attente")  # en_attente | valide | refuse | rembourse

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "date": self.date.isoformat() if self.date else None,
            "montant": float(self.montant) if self.montant is not None else None,
            "devise": self.devise,
            "methode": self.methode,
            "transaction_id": self.transaction_id,
            "statut": self.statut,
        }


class ResetToken(db.Model):
    """Code de réinitialisation de mot de passe."""

    __tablename__ = "reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), index=True, nullable=False)
    code = db.Column(db.String(16), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    utilise = db.Column(db.Boolean, default=False)


class JournalConnexion(db.Model):
    """Journal des connexions, pour les statistiques du dashboard admin."""

    __tablename__ = "journal_connexions"

    id = db.Column(db.Integer, primary_key=True)
    utilisateur_id = db.Column(db.Integer, db.ForeignKey("utilisateurs.id"), nullable=True)
    email = db.Column(db.String(255))
    machine_id = db.Column(db.String(255))
    date = db.Column(db.DateTime, default=_now)
    version = db.Column(db.String(32))
    ip = db.Column(db.String(64), nullable=True)


class SecretMachine(db.Model):
    """Sel de licence (.lseed) historique de chaque poste, migré depuis
    l'ancien système local pour pouvoir continuer à valider/régénérer les
    clés FS/FD déjà émises avant le passage au serveur central.

    ⚠ Donnée hautement sensible : une fuite de cette table combinée au
    secret global compromettrait la totalité des clés jamais émises.
    Ne jamais exposer cette table via une route non protégée par
    require_admin_key, et ne jamais la journaliser en clair."""

    __tablename__ = "secrets_machines"

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    sel = db.Column(db.String(255), nullable=False)
    migre_le = db.Column(db.DateTime, default=_now)


def generer_code(longueur: int = 8) -> str:
    """Code alphanumérique majuscule, même format que le système existant."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(longueur))
