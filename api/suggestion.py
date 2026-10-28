"""Reçoit le formulaire « Une idée de petit projet ? » et l'envoie par mail.

Le site est statique ; ce module fait partie du service lancé par serveur.py
à côté de nginx, sur 127.0.0.1:8081. nginx lui transmet POST /api/suggestion.
Bibliothèque standard uniquement : aucune dépendance à suivre.

Les identifiants SMTP viennent de l'environnement (variables Coolify), jamais
du dépôt, qui est public. Tant qu'ils manquent, le service répond 503 et le
formulaire dit qu'il n'est pas encore branché.
"""

import json
import os
import re
import smtplib
import ssl
import sys
import threading
import time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs

TAILLE_MAX = 16 * 1024
LIMITE_PAR_HEURE = 5
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")

_envois = {}
_verrou = threading.Lock()


def env(*noms, defaut=""):
    """Première variable définie parmi `noms`.

    Les variables d'équipe Coolify ({{team.*}}) ne sont pas toutes nommées
    pareil d'un service à l'autre (SMTP_USER ou SMTP_USERNAME...) : on accepte
    les deux formes pour que l'application puisse reprendre les noms d'équipe
    tels quels.
    """
    for nom in noms:
        valeur = os.environ.get(nom, "").strip()
        if valeur:
            return valeur
    return defaut


def config():
    """Rend la configuration SMTP, ou None si une variable obligatoire manque."""
    utilisateur = env("SMTP_USER", "SMTP_USERNAME")
    mot_de_passe = env("SMTP_PASS", "SMTP_PASSWORD")
    destinataire = env("MAIL_TO", "SMTP_TO")
    if not (utilisateur and mot_de_passe and destinataire):
        return None
    port = int(env("SMTP_PORT", defaut="587"))
    securite = env("SMTP_SECURITY", defaut="ssl" if port == 465 else "starttls").lower()
    return {
        "hote": env("SMTP_HOST", defaut="mail.infomaniak.com"),
        "port": port,
        "ssl": securite in ("ssl", "tls", "smtps"),
        "utilisateur": utilisateur,
        "mot_de_passe": mot_de_passe,
        # Infomaniak refuse un expéditeur différent du compte authentifié.
        "expediteur": env("MAIL_FROM", "SMTP_FROM") or utilisateur,
        "destinataire": destinataire,
    }


def trop_frequent(ip):
    maintenant = time.time()
    with _verrou:
        recents = [t for t in _envois.get(ip, []) if maintenant - t < 3600]
        if len(recents) >= LIMITE_PAR_HEURE:
            _envois[ip] = recents
            return True
        recents.append(maintenant)
        _envois[ip] = recents
        return False


def nettoyer(champs):
    """Rend (idee, prenom, email) ou lève ValueError avec un message lisible."""
    idee = str(champs.get("idee", "")).strip()
    prenom = " ".join(str(champs.get("name", "")).split())[:80]
    email = str(champs.get("email", "")).strip()[:120]
    if not idee:
        raise ValueError("Décris ton idée avant d'envoyer.")
    if len(idee) > 2000:
        raise ValueError("Ton idée dépasse 2 000 caractères. Raccourcis-la un peu.")
    if email and not EMAIL_RE.match(email):
        raise ValueError("L'adresse e-mail ne semble pas valide.")
    return idee, prenom, email


def envoyer(cfg, idee, prenom, email):
    msg = EmailMessage()
    msg["Subject"] = "Nouvelle idée de projet sur qhn.fr"
    msg["From"] = formataddr(("qhn.fr", cfg["expediteur"]))
    msg["To"] = cfg["destinataire"]
    msg["Message-ID"] = make_msgid(domain="qhn.fr")
    if email:
        msg["Reply-To"] = formataddr((prenom, email)) if prenom else email
    msg.set_content(
        f"Prénom : {prenom or '(non renseigné)'}\n"
        f"E-mail : {email or '(non renseigné)'}\n\n{idee}\n"
    )
    contexte = ssl.create_default_context()
    if cfg["ssl"]:
        with smtplib.SMTP_SSL(cfg["hote"], cfg["port"], context=contexte, timeout=20) as smtp:
            smtp.login(cfg["utilisateur"], cfg["mot_de_passe"])
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(cfg["hote"], cfg["port"], timeout=20) as smtp:
            smtp.starttls(context=contexte)
            smtp.login(cfg["utilisateur"], cfg["mot_de_passe"])
            smtp.send_message(msg)


class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "suggestion"

    def log_message(self, fmt, *args):
        sys.stderr.write("api: " + (fmt % args) + "\n")

    def repondre(self, code, message, ok=False):
        if self.veut_json:
            corps = json.dumps({"ok": ok, "message": message}).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)
        else:
            # Envoi sans JavaScript : on renvoie vers une page de résultat.
            self.send_response(303)
            self.send_header("Location", "/merci.html" if ok else "/oups.html")
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_GET(self):
        # Sonde du conteneur : le service répond, configuré ou non.
        self.veut_json = True
        if self.path == "/api/sante":
            return self.repondre(200, "ok" if config() else "ok, SMTP non configuré", ok=True)
        return self.repondre(404, "Adresse inconnue.")

    def do_POST(self):
        self.veut_json = "application/json" in self.headers.get("Accept", "")
        if self.path != "/api/suggestion":
            return self.repondre(404, "Adresse inconnue.")
        try:
            taille = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            taille = -1
        if taille < 0 or taille > TAILLE_MAX:
            return self.repondre(413, "Le message est trop long.")
        brut = self.rfile.read(taille).decode("utf-8", "replace")
        if self.headers.get("Content-Type", "").startswith("application/json"):
            try:
                champs = json.loads(brut or "{}")
            except json.JSONDecodeError:
                return self.repondre(400, "Requête illisible.")
            if not isinstance(champs, dict):
                return self.repondre(400, "Requête illisible.")
        else:
            champs = {k: v[0] for k, v in parse_qs(brut).items()}

        # Champ piège : un robot le remplit, un humain ne le voit pas.
        if champs.get("botcheck"):
            return self.repondre(200, "Merci, ton idée est bien arrivée.", ok=True)
        try:
            idee, prenom, email = nettoyer(champs)
        except ValueError as erreur:
            return self.repondre(400, str(erreur))
        cfg = config()
        if cfg is None:
            return self.repondre(503, "Le formulaire n'est pas encore branché.")
        ip = self.headers.get("X-Real-IP") or self.client_address[0]
        if trop_frequent(ip):
            return self.repondre(429, "Tu as déjà envoyé plusieurs idées. Réessaie dans une heure.")
        try:
            envoyer(cfg, idee, prenom, email)
        except (smtplib.SMTPException, OSError) as erreur:
            # Le type d'erreur seulement : jamais d'identifiant dans le journal.
            self.log_message("échec SMTP : %s", type(erreur).__name__)
            return self.repondre(502, "L'envoi a échoué. Réessaie dans un moment.")
        return self.repondre(200, "Merci, ton idée est bien arrivée.", ok=True)


# Point d'entrée : serveur.py, qui ajoute la zone privée à ce gestionnaire.
