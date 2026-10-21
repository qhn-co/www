# www — page d'accueil de qhn.fr

Une page statique qui liste les petits projets web du parc. Première itération,
reprise de la maquette « qhn.fr » du 2026-10-15, avec les vrais domaines.

- `site/` : le contenu servi, tel quel.
- `nginx.conf` : `/sante` pour la sonde ; `/explorer/*` renvoie vers `aveliou.qhn.fr`.
- `Dockerfile` : nginx alpine, version figée.

Déploiement : application Coolify `www-prod-web` (projet `www`, srv05),
construite depuis ce dépôt public, branche `main`. Un push ne redéploie pas
tout seul : relancer le déploiement depuis Coolify (ou son API).

Dépôt public : il ne contient et ne contiendra aucun secret.
