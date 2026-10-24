#!/bin/sh
# Exécuté par l'entrypoint de l'image nginx avant le démarrage de nginx.
# Lance le service d'envoi en tâche de fond et le relance s'il s'arrête,
# pour qu'une erreur Python ne laisse pas le formulaire muet jusqu'au
# prochain déploiement.
(
  while true; do
    python3 /opt/suggestion/suggestion.py
    echo "suggestion: arrêté, relance dans 2 s" >&2
    sleep 2
  done
) &
