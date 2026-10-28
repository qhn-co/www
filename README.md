# www — page d'accueil de qhn.fr

Une page statique qui liste les petits projets web du parc. Première itération,
reprise de la maquette « qhn.fr » du 2026-10-15, avec les vrais domaines.

- `site/` : le contenu servi, tel quel.
- `nginx.conf` : `/sante` pour la sonde ; `/explorer/*` renvoie vers `aveliou.qhn.fr`.
- `Dockerfile` : nginx alpine, version figée, plus python3 pour `envoi/`.
- `envoi/` : le service qui envoie les suggestions par mail.

Déploiement : application Coolify `www-prod-web` (projet `www`, srv05),
construite depuis ce dépôt public, branche `main`. Un push ne redéploie pas
tout seul : relancer le déploiement depuis Coolify (ou son API).

Dépôt public : il ne contient et ne contiendra aucun secret. Les identifiants
SMTP vivent dans les variables d'environnement de Coolify.

## Formulaire « Une idée de petit projet ? »
Le formulaire poste vers `/api/suggestion`. nginx le transmet à
`envoi/suggestion.py`, un petit service Python (bibliothèque standard seule)
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

Tests : `python3 -m unittest discover envoi`.
