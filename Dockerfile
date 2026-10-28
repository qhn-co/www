FROM nginx:1.27.5-alpine
# python3 pour le petit service d'envoi du formulaire (bibliothèque standard seule).
RUN apk add --no-cache python3
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY site/ /usr/share/nginx/html/
COPY envoi/suggestion.py /opt/suggestion/suggestion.py
COPY envoi/lancer.sh /docker-entrypoint.d/90-suggestion.sh
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/sante && wget -qO- http://127.0.0.1:8081/api/sante || exit 1
