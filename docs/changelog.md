# Changelog Plugin Roborock

## 2.0.0 (2026-05-12)
- Refonte complète basée sur python-roborock v5 (même lib que l'intégration HA officielle)
- Authentification par code email (comme l'app Roborock)
- Communication locale LAN prioritaire, fallback cloud automatique
- Support protocoles v1 / dyad / zeo / b01_q7 / b01_q10
- Polling 30s + callback push HTTP vers Jeedom
- Toutes les commandes HA : vacuum, select, sensor, binary_sensor, switch, number, button, time
- Venv Python isolé (compatible Debian 12)
