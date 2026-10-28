"""Service de qhn.fr derrière nginx (127.0.0.1:8081) : formulaire et zone privée.

nginx lui transmet tout /api/. Bibliothèque standard seule.
"""

import json
import os
import sys
from http.server import ThreadingHTTPServer

import prive
import suggestion

ECOUTE = ("127.0.0.1", int(os.environ.get("SUGGESTION_PORT", "8081")))


class Gestionnaire(suggestion.Gestionnaire):
    def json(self, code, donnees, entetes=()):
        corps = json.dumps(donnees, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(corps)))
        for nom, valeur in entetes:
            self.send_header(nom, valeur)
        self.end_headers()
        self.wfile.write(corps)

    def ip(self):
        return self.headers.get("X-Real-IP") or self.client_address[0]

    def do_GET(self):
        if self.path == "/api/prive":
            session = prive.lire_session(prive.cookie_de(self.headers))
            if not session:
                return self.json(401, {"connecte": False, "ouverte": bool(prive.mot_de_passe())})
            csrf, fin = session
            return self.json(200, {"connecte": True, "csrf": csrf, "fin": fin, "outils": prive.tuiles()})
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/connexion":
            return self.connexion()
        if self.path == "/api/deconnexion":
            session = prive.lire_session(prive.cookie_de(self.headers))
            if session and self.headers.get("X-CSRF") != session[0]:
                return self.json(403, {"message": "Requête refusée."})
            return self.json(200, {"connecte": False}, [("Set-Cookie", prive.entete_cookie("", 0))])
        return super().do_POST()

    def connexion(self):
        if not prive.mot_de_passe():
            return self.json(503, {"message": "La zone privée n'est pas encore ouverte."})
        if prive.bloque(self.ip()):
            return self.json(429, {"message": "Trop d'essais. Réessaie dans un quart d'heure."})
        try:
            taille = int(self.headers.get("Content-Length", "0"))
            champs = json.loads(self.rfile.read(min(max(taille, 0), 4096)) or b"{}")
            saisie = champs.get("phrase", "") if isinstance(champs, dict) else ""
        except (ValueError, json.JSONDecodeError):
            saisie = ""
        if not prive.phrase_ok(saisie):
            prive.noter_echec(self.ip())
            return self.json(401, {"message": "Phrase de passe incorrecte."})
        valeur, _, _ = prive.nouvelle_session()
        return self.json(200, {"connecte": True}, [("Set-Cookie", prive.entete_cookie(valeur, prive.DUREE_SESSION))])


if __name__ == "__main__":
    smtp = "configuré" if suggestion.config() else "NON configuré"
    zone = "ouverte" if prive.mot_de_passe() else "fermée (PRIVE_MOT_DE_PASSE absent)"
    sys.stderr.write(f"api: écoute {ECOUTE[0]}:{ECOUTE[1]}, SMTP {smtp}, zone privée {zone}\n")
    prive.demarrer()
    ThreadingHTTPServer(ECOUTE, Gestionnaire).serve_forever()
