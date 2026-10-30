# Changelog Plugin Roborock

## 2.1.0 (2026-10-20)
Ameliorations reprises du plugin JeeRoborock.

**Pilotage**
- "Demarrer" et "Reprendre" reprennent un nettoyage par piece ou par zone interrompu (RESUME_SEGMENT / RESUME_ZONED) au lieu de relancer un cycle complet
- Un ordre de nettoyage envoye pendant le vidage du bac est refuse avec un message clair (le robot l'ignorait sans rien dire)
- Laver / secher la serpilliere et vider le bac sont refuses si le robot n'est pas a sa base
- Les erreurs du demon remontent enfin dans Jeedom (exception visible dans le dashboard et les scenarios)
- Reglages verifies apres envoi : aspiration, debit d'eau, itineraire, type de nettoyage relus jusqu'a 12 s ; "non confirme" journalise sinon
- Listes deroulantes (aspiration, debit d'eau, itineraire, modes station) limitees aux valeurs que le robot supporte ; correction du code "Profond+" sur les robots chinois (305)
- Nouvelle action "Rafraichir" (relecture complete immediate)

**Carte**
- Nouvel onglet "Carte" dans la page de l'equipement : image de la carte (pieces, trajet, robot, base, zones interdites, murs virtuels) avec le nom des pieces
- Clic sur la carte = coordonnees x,y en mm + piece cliquee : boutons "Aller ici" et "Nettoyer <piece>" (avec nombre de passages)
- Mode "Tracer une zone" : rectangle a la souris ou au doigt, bouton "Nettoyer la zone" (passages 1-3), coordonnees copiables pour un scenario
- Nouvelles infos "Piece courante" et "Carte mise a jour", action "Rafraichir carte"
- Carte relue toutes les 60 s pendant un nettoyage, une fois a l'arret, puis toutes les heures au repos (MQTT, sans quota)
- Image utilisable dans un widget perso : plugins/roborock/core/php/roborockMap.php?id=<id equipement> (utilisateur connecte)

**Pieces et zones**
- Pieces nommees comme dans l'application (plus de "Piece 16") ; commandes "Nettoyer <piece>" qui suivent les renommages sauf nom personnalise
- Nouvelle action "Nettoyer des pieces" par noms (Message) avec nombre de passages 1-3 (Titre)
- "Nettoyer une zone" corrigee (les coordonnees etaient envoyees en texte brut) + plusieurs zones separees par ";" + passages
- "Nettoyer segments" et "Aller au point" creees comme commandes

**Reglages de l'appareil et station**
- Ne pas deranger : action "NDD definir plage" (HH:MM-HH:MM) ; "NDD On" ne plante plus si la plage n'est pas encore lue
- Recharge en heures creuses : etat, plage, On / Off / definir plage (si le robot le gere)
- Modes de la station : mode de vidage et mode de lavage (info + liste)
- "Reservoir eau propre vide", "Bac eau sale plein ou absent", "Sac poussiere absent" en oui/non (mis a jour robot a la base uniquement)
- Consommables de station publies seulement si le robot remonte le compteur ; reset de la brosse de nettoyage

**Journal et statistiques**
- Dernier nettoyage : debut, fin, duree, surface, motif de fin, complet, erreur (relu automatiquement jusqu'a 30 min apres la fin)
- Statistiques cumulees historisees : duree totale, surface totale, nombre de nettoyages, nombre de vidages

**Robustesse**
- Commandes creees selon les capacites annoncees par le robot (champ "Capacites detectees") ; rien n'est supprime
- Indicateur "En ligne" et "Derniere mise a jour"
- Reconnexions bornees (jamais deux en parallele, 10 min mini apres un OFFLINE) et cache home_data entre reconnexions : la reconnexion horaire ne consomme plus de quota Roborock
- Reglages (NDD, volume, verrou, heures creuses, modes station) relus toutes les 10 min, consommables et statistiques toutes les 30 min
- python-roborock passe en 7.8.0 (version utilisee par JeeRoborock, liste des stations a jour) : reinstaller les dependances

## 2.0.0 (2026-05-12)
- Refonte complète basée sur python-roborock v5 (même lib que l'intégration HA officielle)
- Authentification par code email (comme l'app Roborock)
- Communication locale LAN prioritaire, fallback cloud automatique
- Support protocoles v1 / dyad / zeo / b01_q7 / b01_q10
- Polling 30s + callback push HTTP vers Jeedom
- Toutes les commandes HA : vacuum, select, sensor, binary_sensor, switch, number, button, time
- Venv Python isolé (compatible Debian 12)
