#!/bin/bash
BASE_DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
PLUGIN=$(basename "$(realpath ${BASE_DIR}/..)")
LANG_DEP=fr

wget https://raw.githubusercontent.com/NebzHB/dependance.lib/master/dependance.lib \
    --no-cache -O "${BASE_DIR}/dependance.lib" &>/dev/null
[ -f "${BASE_DIR}/dependance.lib" ] || { echo "Erreur: dependance.lib introuvable"; exit 1; }
. "${BASE_DIR}/dependance.lib"

wget https://raw.githubusercontent.com/NebzHB/dependance.lib/master/pyenv.lib \
    --no-cache -O "${BASE_DIR}/pyenv.lib" &>/dev/null
[ -f "${BASE_DIR}/pyenv.lib" ] || { echo "Erreur: pyenv.lib introuvable"; exit 1; }
. "${BASE_DIR}/pyenv.lib"

TARGET_PYTHON_VERSION="3.9"
VENV_DIR="${BASE_DIR}/venv"

pre

step 5 "Nettoyage APT"
try apt-get clean

step 10 "Mise a jour APT"
apt-get update 2>&1 || true
echo_success

autoSetupVenv

step 80 "Installation des paquets python"
try ${VENV_DIR}/bin/python3 -m pip install --upgrade pip -q
try ${VENV_DIR}/bin/python3 -m pip install -r "${BASE_DIR}/requirements.txt"

step 90 "Droits fichiers"
chown -R www-data:www-data "${BASE_DIR}" 2>/dev/null || true
echo_success

step 95 "Paquets installes"
${VENV_DIR}/bin/python3 -m pip freeze

post