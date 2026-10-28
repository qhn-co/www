"""Zone privée : connexion, sessions, tuiles. Sans réseau : les sondes sont simulées."""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import prive
import serveur

PHRASE = "cheval agrafe batterie correct"


class TestPrive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dossier = tempfile.TemporaryDirectory()
        prive.BASE = os.path.join(cls.dossier.name, "prive.sqlite")
        cls.serveur = ThreadingHTTPServer(("127.0.0.1", 0), serveur.Gestionnaire)
        cls.url = f"http://127.0.0.1:{cls.serveur.server_address[1]}"
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.dossier.cleanup()

    def setUp(self):
        prive._echecs.clear()

    def appel(self, chemin, corps=None, entetes=None, ip="203.0.113.9"):
        h = {"Accept": "application/json", "X-Real-IP": ip, **(entetes or {})}
        if corps is not None:
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.url + chemin, data=None if corps is None else json.dumps(corps).encode(),
                                     headers=h, method="POST" if corps is not None else "GET")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read()), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read()), e.headers

    @mock.patch.dict(os.environ, {"PRIVE_MOT_DE_PASSE": PHRASE})
    def test_sans_session_rien(self):
        code, rep, _ = self.appel("/api/prive")
        self.assertEqual(code, 401)
        self.assertNotIn("outils", rep)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_zone_fermee_sans_phrase(self):
        self.assertEqual(self.appel("/api/connexion", {"phrase": ""})[0], 503)
        self.assertIsNone(prive.lire_session("1.2.3"))

    @mock.patch.dict(os.environ, {"PRIVE_MOT_DE_PASSE": PHRASE})
    @mock.patch("prive.time.sleep", lambda s: None)
    def test_connexion_puis_tuiles_puis_deconnexion(self):
        self.assertEqual(self.appel("/api/connexion", {"phrase": "mauvaise"})[0], 401)
        code, _, h = self.appel("/api/connexion", {"phrase": "  Cheval agrafe BATTERIE correct "})
        self.assertEqual(code, 200)
        cookie = h["Set-Cookie"]
        for attendu in ("__Host-qhn-prive=", "HttpOnly", "Secure", "SameSite=Strict", "Path=/"):
            self.assertIn(attendu, cookie)
        valeur = cookie.split(";")[0]
        code, rep, _ = self.appel("/api/prive", entetes={"Cookie": valeur})
        self.assertEqual(code, 200)
        self.assertEqual([o["id"] for o in rep["outils"]], [o["id"] for o in prive.OUTILS])
        self.assertEqual(self.appel("/api/deconnexion", {}, {"Cookie": valeur, "X-CSRF": "faux"})[0], 403)
        code, _, h = self.appel("/api/deconnexion", {}, {"Cookie": valeur, "X-CSRF": rep["csrf"]})
        self.assertEqual(code, 200)
        self.assertIn("Max-Age=0", h["Set-Cookie"])

    @mock.patch.dict(os.environ, {"PRIVE_MOT_DE_PASSE": PHRASE})
    def test_session_falsifiee_ou_expiree(self):
        valeur, _, _ = prive.nouvelle_session()
        fin, csrf, sig = valeur.split(".")
        self.assertIsNotNone(prive.lire_session(valeur))
        self.assertIsNone(prive.lire_session(f"{int(fin) + 3600}.{csrf}.{sig}"))
        vieille, _, _ = prive.nouvelle_session(maintenant=time.time() - prive.DUREE_SESSION - 1)
        self.assertIsNone(prive.lire_session(vieille))
        with mock.patch.dict(os.environ, {"PRIVE_MOT_DE_PASSE": "autre phrase"}):
            self.assertIsNone(prive.lire_session(valeur))

    @mock.patch.dict(os.environ, {"PRIVE_MOT_DE_PASSE": PHRASE})
    @mock.patch("prive.time.sleep", lambda s: None)
    def test_blocage_apres_cinq_echecs(self):
        codes = [self.appel("/api/connexion", {"phrase": "non"}, ip="198.51.100.1")[0] for _ in range(6)]
        self.assertEqual(codes, [401] * 5 + [429])
        self.assertEqual(self.appel("/api/connexion", {"phrase": PHRASE}, ip="198.51.100.1")[0], 429)
        self.assertEqual(self.appel("/api/connexion", {"phrase": PHRASE}, ip="198.51.100.2")[0], 200)

    def test_tuiles_a_partir_des_mesures(self):
        maintenant = 1_800_000_000
        with mock.patch("prive.sonder", side_effect=lambda o: (o["id"] != "vault", 120)):
            for k in range(12):
                prive.mesurer_tout(maintenant - 3600 + k * 300)
        par_id = {t["id"]: t for t in prive.tuiles(maintenant)}
        self.assertEqual((par_id["vma"]["etat"], par_id["vma"]["kpi"]), ("ok", "100 %"))
        self.assertEqual(par_id["vma"]["detail"], "120 ms en moyenne")
        self.assertEqual((par_id["vault"]["etat"], par_id["vault"]["kpi"]), ("ko", "0 %"))
        self.assertIn("var(--ko)", par_id["vault"]["svg"])
        self.assertEqual(par_id["recettes"]["etat"], "off")
        self.assertTrue(all(t["svg"].startswith("<svg") for t in par_id.values()))


if __name__ == "__main__":
    unittest.main()
