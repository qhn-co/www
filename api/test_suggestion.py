"""Teste le service d'envoi de bout en bout, avec un faux serveur SMTP."""

import json
import os
import smtplib
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from typing import ClassVar
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import serveur
import suggestion

ENV = {"SMTP_USER": "envoi@qhn.fr", "SMTP_PASS": "x", "MAIL_TO": "steven@exemple.fr"}


class FauxSMTP:
    envoyes: ClassVar[list] = []
    connexions: ClassVar[list] = []

    def __init__(self, hote, port, timeout=None, **_):
        FauxSMTP.connexions.append((hote, port))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def starttls(self, context=None):
        pass

    def login(self, utilisateur, mot_de_passe):
        self.utilisateur = utilisateur

    def send_message(self, msg):
        FauxSMTP.envoyes.append(msg)


class TestSuggestion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.serveur = ThreadingHTTPServer(("127.0.0.1", 0), serveur.Gestionnaire)
        cls.url = f"http://127.0.0.1:{cls.serveur.server_address[1]}"
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()

    def setUp(self):
        FauxSMTP.envoyes.clear()
        FauxSMTP.connexions.clear()
        suggestion._envois.clear()

    def poster(self, champs, ip="203.0.113.1"):
        req = urllib.request.Request(
            self.url + "/api/suggestion",
            data=json.dumps(champs).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json", "X-Real-IP": ip},
        )
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    @mock.patch.dict(os.environ, ENV, clear=True)
    @mock.patch("smtplib.SMTP", FauxSMTP)
    def test_envoi_complet(self):
        code, rep = self.poster({"idee": "Un calculateur d'allure", "name": "Léa", "email": "lea@exemple.fr"})
        self.assertEqual((code, rep["ok"]), (200, True))
        self.assertEqual(FauxSMTP.connexions, [("mail.infomaniak.com", 587)])
        msg = FauxSMTP.envoyes[0]
        self.assertEqual(msg["To"], "steven@exemple.fr")
        self.assertIn("envoi@qhn.fr", msg["From"])
        self.assertIn("lea@exemple.fr", msg["Reply-To"])
        self.assertIn("Un calculateur d'allure", msg.get_content())

    @mock.patch.dict(os.environ, {"SMTP_HOST": "smtp.exemple.fr", "SMTP_PORT": "465", "SMTP_USERNAME": "a@qhn.fr",
                                  "SMTP_PASSWORD": "x", "SMTP_TO": "b@qhn.fr", "SMTP_FROM": "c@qhn.fr"}, clear=True)
    def test_noms_des_variables_d_equipe(self):
        cfg = suggestion.config()
        self.assertEqual((cfg["hote"], cfg["port"], cfg["ssl"]), ("smtp.exemple.fr", 465, True))
        self.assertEqual((cfg["utilisateur"], cfg["destinataire"], cfg["expediteur"]), ("a@qhn.fr", "b@qhn.fr", "c@qhn.fr"))

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_non_configure(self):
        code, rep = self.poster({"idee": "x"})
        self.assertEqual(code, 503)
        self.assertIn("pas encore branché", rep["message"])

    @mock.patch.dict(os.environ, ENV, clear=True)
    @mock.patch("smtplib.SMTP", FauxSMTP)
    def test_refus(self):
        self.assertEqual(self.poster({"idee": "  "})[0], 400)
        self.assertEqual(self.poster({"idee": "x" * 2001})[0], 400)
        self.assertEqual(self.poster({"idee": "x", "email": "a@b.fr\nBcc: c@d.fr"})[0], 400)
        self.assertEqual(self.poster(["pas", "un", "objet"])[0], 400)
        self.assertEqual(FauxSMTP.envoyes, [])

    @mock.patch.dict(os.environ, ENV, clear=True)
    @mock.patch("smtplib.SMTP", FauxSMTP)
    def test_champ_piege(self):
        code, rep = self.poster({"idee": "spam", "botcheck": "on"})
        self.assertEqual((code, rep["ok"]), (200, True))
        self.assertEqual(FauxSMTP.envoyes, [])

    @mock.patch.dict(os.environ, ENV, clear=True)
    @mock.patch("smtplib.SMTP", FauxSMTP)
    def test_limite_par_heure(self):
        codes = [self.poster({"idee": f"idée {i}"})[0] for i in range(6)]
        self.assertEqual(codes, [200] * 5 + [429])
        self.assertEqual(self.poster({"idee": "autre"}, ip="203.0.113.2")[0], 200)

    @mock.patch.dict(os.environ, ENV, clear=True)
    def test_echec_smtp(self):
        with mock.patch("smtplib.SMTP", side_effect=smtplib.SMTPAuthenticationError(535, b"non")):
            self.assertEqual(self.poster({"idee": "x"})[0], 502)

    @mock.patch.dict(os.environ, ENV, clear=True)
    @mock.patch("smtplib.SMTP", FauxSMTP)
    def test_sans_javascript(self):
        req = urllib.request.Request(self.url + "/api/suggestion", data=b"idee=Bonjour&name=&email=",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})

        class SansSuivi(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.build_opener(SansSuivi).open(req)
        self.assertEqual((ctx.exception.code, ctx.exception.headers["Location"]), (303, "/merci.html"))
        self.assertEqual(len(FauxSMTP.envoyes), 1)


if __name__ == "__main__":
    unittest.main()
