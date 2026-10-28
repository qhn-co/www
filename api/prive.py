"""Zone privée de qhn.fr : une tuile par outil perso, visible après connexion.

La page publique ne contient rien de privé. Une fois connecté, son script
demande /api/prive, et c'est le serveur qui rend les tuiles. Sans session
valide, /api/prive répond 401 et la section n'apparaît pas.

Chaque outil est sondé toutes les 5 minutes depuis ce conteneur (adresse et
contenu attendu dans outils.json, rien de secret) ; l'historique sert au
graphique de la tuile. Les sondes ne demandent aucun jeton.

Connexion : une phrase de passe (PRIVE_MOT_DE_PASSE, variable Coolify), même
mécanisme que manage.ops.qhn.fr. Sans elle, la zone est fermée.
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(ICI, "outils.json"), encoding="utf-8") as f:
    OUTILS = json.load(f)
BASE = os.environ.get("PRIVE_BASE", "/var/lib/qhn/prive.sqlite")
INTERVALLE = 300
CONSERVATION = 31 * 86400
DUREE_SESSION = 8 * 3600
COOKIE = "__Host-qhn-prive"


def mot_de_passe():
    return os.environ.get("PRIVE_MOT_DE_PASSE", "")


def cle():
    # Dérivée de la phrase : la changer dans Coolify ferme toutes les sessions.
    return hmac.new(mot_de_passe().encode(), b"qhn-prive-session-v1", hashlib.sha256).digest()


# --- sessions -------------------------------------------------------------------

def signer(valeur):
    return hmac.new(cle(), valeur.encode(), hashlib.sha256).hexdigest()


def nouvelle_session(maintenant=None):
    fin = int(maintenant or time.time()) + DUREE_SESSION
    csrf = secrets.token_hex(16)
    corps = f"{fin}.{csrf}"
    return f"{corps}.{signer(corps)}", csrf, fin


def lire_session(valeur):
    """(csrf, fin) si la session est valide, sinon None."""
    if not mot_de_passe() or not valeur:
        return None
    try:
        fin, csrf, sig = valeur.split(".")
        fin_i = int(fin)
    except ValueError:
        return None
    if not hmac.compare_digest(sig, signer(f"{fin}.{csrf}")):
        return None
    return (csrf, fin_i) if fin_i > time.time() else None


def cookie_de(entetes):
    for morceau in (entetes.get("Cookie") or "").split(";"):
        nom, _, valeur = morceau.strip().partition("=")
        if nom == COOKIE:
            return valeur
    return ""


def entete_cookie(valeur, duree):
    return f"{COOKIE}={valeur}; Path=/; Max-Age={duree}; HttpOnly; Secure; SameSite=Strict"


_echecs = {}
_verrou = threading.Lock()


def bloque(ip):
    """5 échecs en 15 min depuis une adresse : refus pendant 15 min."""
    maintenant = time.time()
    with _verrou:
        for k in [k for k, v in _echecs.items() if not v or maintenant - v[-1] > 900]:
            del _echecs[k]
        return len([t for t in _echecs.get(ip, []) if maintenant - t < 900]) >= 5


def noter_echec(ip):
    with _verrou:
        _echecs.setdefault(ip, []).append(time.time())
    time.sleep(1)


def phrase_ok(saisie):
    attendu = mot_de_passe()
    if not attendu:
        return False
    a = hashlib.sha256(str(saisie).strip().lower().encode()).digest()
    b = hashlib.sha256(attendu.strip().lower().encode()).digest()
    return hmac.compare_digest(a, b)


# --- mesures --------------------------------------------------------------------

def connexion():
    os.makedirs(os.path.dirname(BASE), exist_ok=True)
    db = sqlite3.connect(BASE, timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS mesure (outil TEXT, t INTEGER, ok INTEGER, ms INTEGER)")
    db.execute("CREATE INDEX IF NOT EXISTS mesure_outil_t ON mesure (outil, t)")
    return db


def sonder(outil):
    """(ok, ms). ok exige une réponse 2xx-3xx ET le contenu attendu."""
    debut = time.monotonic()
    req = urllib.request.Request(outil["url"] + outil["sonde"], headers={"User-Agent": "qhn-prive/1"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # adresses fixes d'outils.json
            corps = r.read(65536).decode("utf-8", "replace")
            ok = 200 <= r.status < 400 and outil.get("contient", "") in corps
    except (urllib.error.URLError, OSError, ValueError):
        ok = False
    return ok, int((time.monotonic() - debut) * 1000)


def mesurer_tout(maintenant=None):
    t = int(maintenant or time.time())
    lignes = [(o["id"], t, *sonder(o)) for o in OUTILS if not o.get("bientot")]
    db = connexion()
    with db:
        db.executemany("INSERT INTO mesure VALUES (?, ?, ?, ?)", [(i, t, int(ok), ms) for i, t, ok, ms in lignes])
        db.execute("DELETE FROM mesure WHERE t < ?", (t - CONSERVATION,))
    db.close()


def boucle():
    while True:
        try:
            mesurer_tout()
        except Exception as erreur:  # noqa: BLE001  la boucle ne doit jamais mourir
            print(f"prive: mesure impossible : {type(erreur).__name__}", flush=True)
        time.sleep(INTERVALLE)


def demarrer():
    threading.Thread(target=boucle, daemon=True).start()


# --- tuiles ---------------------------------------------------------------------

def stats(db, outil, maintenant):
    """Disponibilité et temps de réponse sur 24 h, en 48 tranches de 30 min."""
    debut = maintenant - 86400
    rangs = db.execute("SELECT t, ok, ms FROM mesure WHERE outil = ? AND t > ? ORDER BY t",
                       (outil, debut)).fetchall()
    tranches = [[] for _ in range(48)]
    for t, ok, ms in rangs:
        tranches[min(47, (t - debut) // 1800)].append((ok, ms))
    barres = []
    for tr in tranches:
        if not tr:
            barres.append(None)
        else:
            oks = [ms for ok, ms in tr if ok]
            barres.append({"ms": sum(oks) // len(oks) if oks else 0, "panne": len(oks) < len(tr)})
    dernier = rangs[-1] if rangs else None
    oks = [ms for _, ok, ms in rangs if ok]
    return {
        "mesures": len(rangs),
        "dispo": round(100 * len(oks) / len(rangs), 1) if rangs else None,
        "ms": sum(oks) // len(oks) if oks else None,
        "dernier": dernier,
        "barres": barres,
    }


def svg(barres):
    """Barres du temps de réponse ; une tranche avec un échec est en rouge."""
    w, h, bas = 300, 96, 80
    hauts = [b["ms"] for b in barres if b]
    plafond = max(hauts) if hauts and max(hauts) > 0 else 1
    pas = w / len(barres)
    morceaux = [f'<line x1="0" y1="{bas}" x2="{w}" y2="{bas}" stroke="currentColor" stroke-opacity=".15"/>']
    for i, b in enumerate(barres):
        if b is None:
            continue
        haut = max(3, b["ms"] / plafond * (bas - 6)) if not b["panne"] else bas - 6
        couleur = "var(--ko)" if b["panne"] else "var(--accent)"
        opacite = "1" if i == len(barres) - 1 else ".55"
        morceaux.append(f'<rect x="{i * pas + pas * .18:.1f}" y="{bas - haut:.1f}" width="{pas * .64:.1f}" '
                        f'height="{haut:.1f}" rx="1.5" fill="{couleur}" fill-opacity="{opacite}"/>')
    morceaux.append('<text x="0" y="93">24 h</text><text x="300" y="93" text-anchor="end">maintenant</text>')
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" '
            f'aria-label="Temps de réponse sur 24 heures">{"".join(morceaux)}</svg>')


def tuiles(maintenant=None):
    maintenant = int(maintenant or time.time())
    db = connexion()
    rendu = []
    try:
        for o in OUTILS:
            t = {"id": o["id"], "nom": o["nom"], "genre": o["genre"], "url": o["url"], "teinte": o["teinte"]}
            if o.get("bientot"):
                t.update(etat="off", kpi="—", unite="pas encore en ligne", detail="",
                         svg=svg([None] * 48), pied=[o["url"].removeprefix("https://"), o["bientot"]])
                rendu.append(t)
                continue
            s = stats(db, o["id"], maintenant)
            if not s["mesures"]:
                t.update(etat="off", kpi="inconnu", unite="pas encore mesuré", detail="",
                         svg=svg([None] * 48), pied=["première mesure dans 5 min", ""])
            else:
                ok_dernier = bool(s["dernier"][1])
                etat = "ko" if not ok_dernier else ("warn" if s["dispo"] < 99 else "ok")
                age = max(0, (maintenant - s["dernier"][0]) // 60)
                t.update(etat=etat, kpi=f"{s['dispo']:g} %".replace(".", ","), unite="disponible sur 24 h",
                         detail=(f"{s['ms']} ms en moyenne" if s["ms"] is not None else "aucune réponse"),
                         svg=svg(s["barres"]),
                         pied=["temps de réponse", f"mesuré il y a {age} min" if age else "mesuré à l'instant"])
            rendu.append(t)
    finally:
        db.close()
    return rendu
