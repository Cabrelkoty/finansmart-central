"""
FinanSmart Central — Logique des clés de licence

Reprend EXACTEMENT le même algorithme que licence.py côté poste client
(FS.../FD..., SHA-256 du sel+machine_id, segments de 4 caractères hex),
afin que les clés générées ici restent vérifiables par les postes clients
qui font encore une vérification locale en secours hors-ligne.

Deux sources de sel possibles :
  1. Si machine_id correspond à un poste migré (table secrets_machines),
     on utilise SON sel historique → les anciennes clés FS/FD émises avant
     la migration restent valides.
  2. Sinon, on utilise le secret global du serveur central (SECRET_KEY) →
     toute nouvelle clé émise après la migration.
"""

import hashlib
from datetime import date, datetime, timedelta, timezone

from flask import current_app

from models import SecretMachine

_EPOCH = date(2020, 1, 1)


def _sel_pour_machine(machine_id: str) -> str:
    machine_id = (machine_id or "").strip().upper()
    if machine_id:
        secret_machine = SecretMachine.query.filter_by(machine_id=machine_id).first()
        if secret_machine:
            return secret_machine.sel
    return current_app.config["SECRET_KEY"]


def generer_cle(machine_id: str) -> str:
    """Clé permanente liée au machine_id (équivalent FS...)."""
    sel = _sel_pour_machine(machine_id)
    raw = hashlib.sha256(f"{sel}{machine_id.upper()}".encode()).hexdigest().upper()
    seg = [raw[i * 4 : (i + 1) * 4] for i in range(4)]
    return f"FS{seg[0]}-{seg[1]}-{seg[2]}-{seg[3]}"


def generer_cle_datee(machine_id: str, date_exp: date) -> str:
    """Clé avec date d'expiration intégrée (équivalent FD...)."""
    sel = _sel_pour_machine(machine_id)
    mid = (machine_id or "").strip().upper()
    offset = (date_exp - _EPOCH).days
    date_enc = format(offset, "X").zfill(4)
    date_code = date_exp.strftime("%d%m%y")
    raw = hashlib.sha256(f"{sel}{mid}{date_code}".encode()).hexdigest().upper()
    seg = [raw[i * 4 : (i + 1) * 4] for i in range(4)]
    return f"FD{seg[0]}-{date_enc}-{seg[2]}-{seg[3]}"


def verifier_cle(cle: str, machine_id: str) -> tuple[bool, datetime | None]:
    """Vérifie une clé FS ou FD pour un machine_id donné.
    Retourne (valide, date_expiration_ou_None)."""
    cle = (cle or "").strip().upper()
    if not cle or "-" not in cle:
        return False, None

    if cle.startswith("FS"):
        attendue = generer_cle(machine_id)
        return (cle == attendue), None

    if cle.startswith("FD"):
        try:
            parts = cle.split("-")
            date_enc = parts[1]
            offset = int(date_enc, 16)
            date_exp = _EPOCH + timedelta(days=offset)
            attendue = generer_cle_datee(machine_id, date_exp)
            valide = cle == attendue
            exp_dt = datetime.combine(date_exp, datetime.min.time(), tzinfo=timezone.utc)
            return valide, exp_dt
        except Exception:
            return False, None

    return False, None


def duree_licence(type_cle: str) -> timedelta:
    """Durée par défaut selon le type de licence, alignée sur l'offre
    actuelle (client = 3 mois, entreprise = 1 an)."""
    if type_cle == "entreprise":
        return timedelta(days=365)
    return timedelta(days=90)
