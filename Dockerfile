FROM nginx:1.27.5-alpine
# python3 pour le service de api/ : formulaire et zone privée (bibliothèque standard seule).
RUN apk add --no-cache python3 && mkdir -p /var/lib/qhn
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY site/ /usr/share/nginx/html/
COPY api/suggestion.py api/prive.py api/serveur.py api/outils.json /opt/api/
COPY api/lancer.sh /docker-entrypoint.d/90-api.sh
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/sante && wget -qO- http://127.0.0.1:8081/api/sante || exit 1
