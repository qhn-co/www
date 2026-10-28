#!/bin/sh
# Exécuté par l'entrypoint de l'image nginx avant le démarrage de nginx.
# Lance le service (formulaire et zone privée) en tâche de fond et le relance s'il s'arrête,
# pour qu'une erreur Python ne laisse pas le formulaire ni la zone privée muets jusqu'au
# prochain déploiement.
(
  while true; do
    python3 /opt/api/serveur.py
    echo "api: arrêté, relance dans 2 s" >&2
    sleep 2
  done
) &
