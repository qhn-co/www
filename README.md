# www — page d'accueil de qhn.fr

Une page statique qui liste les petits projets web du parc. Première itération,
reprise de la maquette « qhn.fr » du 2026-10-15, avec les vrais domaines.

- `site/` : le contenu servi, tel quel.
- `nginx.conf` : `/sante` pour la sonde ; `/explorer/*` renvoie vers `aveliou.qhn.fr`.
- `Dockerfile` : nginx alpine, version figée, plus python3 pour `api/`.
- `api/` : le service local derrière nginx (`serveur.py`) : formulaire de suggestion
  (`suggestion.py`) et zone privée (`prive.py`, outils listés dans `outils.json`).

Déploiement : application Coolify `www-prod-web` (projet `www`, srv05),
construite depuis ce dépôt public, branche `main`. Un push ne redéploie pas
tout seul : relancer le déploiement depuis Coolify (ou son API).

Dépôt public : il ne contient et ne contiendra aucun secret. Les identifiants
SMTP vivent dans les variables d'environnement de Coolify.

## Formulaire « Une idée de petit projet ? »
Le formulaire poste vers `/api/suggestion`. nginx le transmet à
`api/suggestion.py`, un petit service Python (bibliothèque standard seule)
qui tourne dans le même conteneur sur 127.0.0.1:8081 et envoie le mail par le
SMTP Infomaniak. Limites : 2 000 caractères, champ piège contre les robots,
5 envois par heure et par adresse, plus une limite nginx.

Variables d'environnement de `www-prod-web` dans Coolify (jamais dans ce dépôt
public). Les identifiants SMTP existent déjà en variables d'équipe : Coolify ne
les injecte pas d'office, chaque application les référence, par exemple
`SMTP_USERNAME={{team.SMTP_USERNAME}}`. Le service accepte les deux noms
usuels de chaque réglage, pour reprendre les noms d'équipe tels quels.

| Réglage | Noms acceptés | Obligatoire | Par défaut |
|---|---|---|---|
| compte qui envoie | `SMTP_USER` ou `SMTP_USERNAME` | oui | |
| mot de passe | `SMTP_PASS` ou `SMTP_PASSWORD` | oui | |
| destinataire | `MAIL_TO` ou `SMTP_TO` | oui | |
| serveur | `SMTP_HOST` | non | `mail.infomaniak.com` |
| port | `SMTP_PORT` | non | `587` |
| chiffrement | `SMTP_SECURITY` (`starttls` ou `ssl`) | non | `ssl` sur 465, sinon `starttls` |
| expéditeur | `MAIL_FROM` ou `SMTP_FROM` | non | le compte (Infomaniak exige le même) |

Tant que les trois obligatoires manquent, le formulaire répond « pas encore
branché ». `GET /api/sante` dit si le SMTP est configuré, sans rien révéler.
Le champ e-mail du visiteur devient le `Reply-To` : répondre au mail lui répond.

Tests : `python3 -m unittest discover api`.

## Zone privée « Mes outils »
Sur la même page, une section de tuiles (une par outil perso, avec un graphique)
qui n'existe pas dans le HTML public : le script de la page demande
`/api/prive`, et le serveur ne rend les tuiles qu'avec une session valide.
On se connecte par le lien « Connexion » en bas de page.

- `PRIVE_MOT_DE_PASSE` (Coolify) : la phrase de passe. Absente, la zone est
  fermée. La changer ferme toutes les sessions (clé de session dérivée).
- Session de 8 h, cookie `__Host-qhn-prive` (HttpOnly, Secure, SameSite=Strict),
  5 échecs en 15 min depuis une adresse bloquent 15 min, plus la limite nginx.
- Chaque outil d'`api/outils.json` est sondé toutes les 5 min (adresse et contenu
  attendu, rien de secret). Les tuiles montrent la disponibilité et le temps de
  réponse sur 24 h. Historique dans `PRIVE_BASE` (`/var/lib/qhn/prive.sqlite`) :
  sans volume Coolify, il repart de zéro à chaque déploiement.
- Graphiques propres à un outil (patrimoine, fiches, articles…) : à ajouter un
  par un, chacun avec un accès en lecture seule en variable Coolify.
