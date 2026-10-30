#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Demon Roborock pour Jeedom (python-roborock 7.8.x, compatible 5.14).

v2.1 - ameliorations inspirees de JeeRoborock :
  - listes de modes (aspiration, debit d'eau, itineraire) calculees selon le robot
  - verification des reglages apres envoi (relecture jusqu'a 12 s)
  - "Demarrer" reprend un nettoyage par piece / zone interrompu
  - refus d'un ordre de nettoyage pendant le vidage du bac
  - actions de station refusees hors de la base
  - Ne pas deranger / heures creuses avec plage horaire, modes de vidage et de lavage
  - bacs d'eau de la station en oui/non, consommables de station
  - journal du dernier nettoyage et statistiques cumulees
  - pieces nommees, nettoyage par noms, nombre de passages
  - indicateur "En ligne", reconnexions bornees, cache home_data (economie de quota)
"""
import sys, os, json, asyncio, argparse, logging, signal, socket, threading, datetime, re, time, unicodedata

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
VENV_LIB   = os.path.join(SCRIPT_DIR, 'venv', 'lib')
if os.path.isdir(VENV_LIB):
    for pyver in sorted(os.listdir(VENV_LIB)):
        sp = os.path.join(VENV_LIB, pyver, 'site-packages')
        if os.path.isdir(sp):
            sys.path.insert(0, sp)
            break

try:
    import aiohttp
    from roborock import RoborockException, RoborockInvalidCredentials, RoborockCommand
    from roborock.data import UserData
    from roborock.devices.device_manager import UserParams, create_device_manager
except ImportError as e:
    print(f"[FATAL] Import error: {e}", file=sys.stderr)
    sys.exit(1)

# Elements optionnels de la librairie : le demon reste fonctionnel s'ils manquent
try:
    from roborock.data import (get_clean_modes, get_water_mode_mapping, get_clean_routes,
                               get_wash_towel_modes, RoborockDockDustCollectionModeCode)
except Exception:  # pragma: no cover
    get_clean_modes = get_water_mode_mapping = get_clean_routes = get_wash_towel_modes = None
    RoborockDockDustCollectionModeCode = None
try:
    from roborock.device_features import is_wash_n_fill_dock, is_valid_dock
except Exception:  # pragma: no cover
    is_wash_n_fill_dock = is_valid_dock = None
try:
    from roborock.devices.cache import InMemoryCache
except Exception:  # pragma: no cover
    InMemoryCache = None
try:
    from roborock import RoborockDataProtocol
except Exception:  # pragma: no cover
    RoborockDataProtocol = None
try:
    from roborock.map.map_parser import MapParserConfig
    from vacuum_map_parser_base.config.drawable import Drawable
    MAP_PARSER_CONFIG = MapParserConfig(drawables=[
        Drawable.CHARGER, Drawable.PATH, Drawable.VACUUM_POSITION, Drawable.NO_GO_AREAS,
        Drawable.NO_MOPPING_AREAS, Drawable.VIRTUAL_WALLS, Drawable.ZONES, Drawable.GOTO_PATH,
    ])
except Exception:  # pragma: no cover
    MAP_PARSER_CONFIG = None

DATA_DIR = os.path.realpath(os.path.join(SCRIPT_DIR, '..', 'data'))

# Monkey-patch: desactive la connexion locale (cloud uniquement, cf. serveur CN)
try:
    from roborock.devices.rpc import v1_channel
    async def _disabled_local_connect(self, *, prefer_cache=True): pass
    async def _disabled_background_reconnect(self): pass
    v1_channel.V1Channel._local_connect = _disabled_local_connect
    v1_channel.V1Channel._background_reconnect = _disabled_background_reconnect
except Exception: pass

# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
ERROR_CODES = {
    0: 'Aucune erreur', 1: 'Lidar bloque', 2: 'Pare-choc coince',
    3: 'Roues suspendues', 4: 'Erreur capteur falaise', 5: 'Brosse princ. coincee',
    6: 'Brosse lat. coincee', 7: 'Roues coincees', 8: 'Robot coince',
    9: 'Pas de bac', 10: 'Erreur filtre', 11: 'Erreur boussole',
    12: 'Batterie faible', 13: 'Erreur charge', 14: 'Erreur batterie',
    15: 'Capteur mur sale', 16: 'Robot penche', 17: 'Erreur brosse lat.',
    18: 'Erreur ventilateur', 19: 'Dock non alimente', 20: 'Capteur flux optique sale',
    21: 'Pare-choc vertical presse', 22: 'Erreur localisation dock',
    23: 'Echec retour dock', 24: 'Zone interdite detectee',
    25: 'Erreur capteur visuel', 26: 'Erreur capteur mur', 27: 'Vibrarise coince',
    28: 'Robot sur tapis', 29: 'Filtre bloque', 30: 'Mur invisible detecte',
    31: 'Ne peut pas traverser tapis', 32: 'Erreur interne',
    34: 'Nettoyer dock vidage auto', 35: 'Erreur tension dock vidage auto',
    36: 'Rouleau lavage coince', 37: 'Rouleau lavage mal positionne',
    38: 'Reservoir eau propre vide', 39: 'Reservoir eau sale plein',
    40: 'Remettre filtre eau', 41: 'Reservoir eau propre vide',
    42: 'Verifier filtre eau installe', 43: 'Erreur bouton positionnement',
    44: 'Nettoyer filtre eau dock', 45: 'Rouleau lavage coince',
    48: 'Exception eau montante', 49: 'Exception vidange eau',
    51: 'Protection temperature', 52: 'Exception carrousel nettoyage',
    53: 'Carrousel nettoyage eau plein', 54: 'Chute chariot eau',
    55: 'Verifier carrousel nettoyage', 56: 'Erreur audio',
}

DOCK_ERROR_CODES = {
    0:  'Aucune erreur', 32: 'Pas de bac ou filtre', 33: 'Erreur ventilateur vidage auto',
    34: 'Conduit bloque', 35: 'Erreur tension vidage auto', 38: 'Reservoir eau propre vide',
    39: 'Reservoir eau sale plein', 42: 'Brosse maintenance coincee',
    44: 'Trappe reservoir sale ouverte', 46: 'Pas de bac', 53: 'Reservoir nettoyage plein ou bloque',
}

STATE_NAMES = {
    0: 'unknown', 1: 'initiating', 2: 'sleeping', 3: 'idle', 4: 'remote_control',
    5: 'cleaning', 6: 'returning_home', 7: 'manual_mode', 8: 'charging',
    9: 'charging_problem', 10: 'paused', 11: 'spot_cleaning', 12: 'error',
    13: 'shutting_down', 14: 'updating', 15: 'docking', 16: 'going_to',
    17: 'zoned_cleaning', 18: 'segment_cleaning', 22: 'emptying_the_bin',
    23: 'washing_the_mop', 25: 'washing_the_mop', 26: 'going_to_wash', 28: 'in_call',
    29: 'mapping', 33: 'attaching_the_mop', 34: 'detaching_the_mop',
    100: 'charging', 101: 'offline', 103: 'locked', 202: 'air_drying_stopping',
    6301: 'mopping', 6302: 'clean_mop_cleaning', 6303: 'clean_mop_mopping',
    6304: 'segment_mopping', 6305: 'segment_clean_mop_cleaning',
    6306: 'segment_clean_mop_mopping', 6307: 'zoned_mopping',
    6308: 'zoned_clean_mop_cleaning', 6309: 'zoned_clean_mop_mopping',
    6310: 'back_to_dock_washing',
}

# Docks avec lavage de serpilliere absents de la liste wash-n-fill de la librairie 5.14
EXTRA_WASH_DOCKS = {6, 14, 16, 18}  # utile seulement en 5.14 ; la 7.8 a une liste complete

# Cles historiques (conservees pour ne pas casser les scenarios / widgets existants)
FAN_MAPPING = {
    101: 'quiet', 102: 'balanced', 103: 'turbo', 104: 'max',
    105: 'off', 106: 'custom', 108: 'max_plus', 109: 'off_raise_main_brush', 110: 'smart_mode',
}
MOP_MAPPING = {
    300: 'standard', 301: 'deep', 302: 'custom',
    303: 'deep_plus', 304: 'fast', 305: 'deep_plus', 306: 'smart_mode',
}
WATER_MAPPING = {
    200: 'off', 201: 'low', 202: 'medium', 203: 'high', 204: 'custom',
    205: 'min', 206: 'max', 207: 'custom_water_flow', 208: 'extreme', 209: 'smart_mode',
    221: 'slight', 225: 'low_slide', 235: 'medium_slide', 245: 'moderate',
    248: 'high_slide', 250: 'extreme',
}

FAN_LABELS = {
    'quiet': 'Silencieux', 'balanced': 'Equilibre', 'turbo': 'Turbo', 'max': 'Maximum',
    'max_plus': 'Maximum+', 'off': 'Arret (lavage seul)', 'off_raise_main_brush': 'Arret (brosse relevee)',
    'gentle': 'Doux', 'custom': 'Personnalise', 'smart_mode': 'Auto',
}
WATER_LABELS = {
    'off': 'Arret', 'slight': 'Tres faible', 'low': 'Faible', 'low_slide': 'Faible', 'mild': 'Doux',
    'medium': 'Moyen', 'medium_slide': 'Moyen', 'standard': 'Standard', 'moderate': 'Modere',
    'high': 'Eleve', 'high_slide': 'Eleve', 'intense': 'Intense', 'min': 'Minimum', 'max': 'Maximum',
    'extreme': 'Extreme', 'custom': 'Personnalise', 'custom_water_flow': 'Debit personnalise',
    'smart_mode': 'Auto',
}
ROUTE_LABELS = {
    'standard': 'Standard', 'deep': 'Profond', 'deep_plus': 'Profond+', 'fast': 'Rapide',
    'smart_mode': 'Auto', 'custom': 'Personnalise',
}
DUST_MODE_LABELS = {'smart': 'Intelligent', 'light': 'Leger', 'balanced': 'Equilibre', 'max': 'Maximum'}
WASH_MODE_LABELS = {'light': 'Leger', 'balanced': 'Equilibre', 'deep': 'Profond',
                    'super_deep': 'Tres profond', 'smart': 'Intelligent'}

FINISH_REASON_LABELS = [
    ('finished_cl', 'Termine'),
    ('manual_interrupt', "Interrompu par l'utilisateur"),
    ('cleanup_interrupted', 'Nettoyage interrompu'),
    ('breakpoint', 'Impossible de continuer'),
    ('locate_fail', 'Echec de localisation'),
    ('area_unreachable', 'Zone inaccessible'),
    ('washing_error', 'Erreur de lavage'),
    ('back_to_wash_failure', 'Echec du retour a la station'),
    ('patrol', 'Patrouille'),
    ('pet_patrol', 'Patrouille animaux'),
]

CLEANING_STATES = {5, 11, 16, 17, 18, 33, 34, 6301, 6302, 6303, 6304, 6305, 6306, 6307, 6308, 6309}
DOCKED_STATES   = {3, 8, 15, 22, 23, 25, 26, 100, 202}
AT_BASE_STATES  = {8, 22, 23, 25, 100, 202, 6310}
STATE_EMPTYING_BIN = 22
STATE_PAUSED       = 10

MAIN_BRUSH_MAX = 1080000; SIDE_BRUSH_MAX = 720000; FILTER_MAX = 540000
SENSOR_MAX = 108000; MOP_ROLLER_MAX = 1080000
STRAINER_MAX = 150; CLEANING_MAX = 300; DUST_COLL_MAX = 90

# DSS : sur la station du G20S Ultra / Saros 10R, 2 = OK (constate), 1/3 = alerte
WATER_ALERT_VALUES = {1, 3}
DUST_BAG_ALERT_VALUES = {1, 3}

# Delais
VERIFY_TIMEOUT_S      = 12   # relecture d'un reglage apres envoi
GUARD_REFRESH_S       = 6    # relecture d'etat avant un ordre de nettoyage
SETTINGS_EVERY_POLLS  = 5    # 5 x 120 s = 10 min : DND, volume, verrou, heures creuses, modes station
SLOW_EVERY_POLLS      = 15   # 15 x 120 s = 30 min : consommables, statistiques
RECONNECT_EVERY_POLLS = 30   # 30 x 120 s = 1 h   : reconnexion MQTT periodique
OFFLINE_RECONNECT_MIN_INTERVAL_S = 600
SUMMARY_RETRY_DELAYS  = [60, 120, 300, 420, 900]  # cumul ~30 min apres fin de nettoyage
REPEAT_MAX = 3
MAP_TIMEOUT_S         = 30   # telechargement de la carte (MQTT, sans quota)
MAP_PARSE_TIMEOUT_S   = 30   # rendu PNG (Pillow) dans un thread
MAP_ACTIVE_EVERY_S    = 60   # carte relue toutes les 60 s pendant un nettoyage
MAP_IDLE_EVERY_S      = 3600 # et toutes les heures au repos
MOVING_STATES = CLEANING_STATES | {6, 15, 16, 26}


class DaemonError(Exception):
    """Erreur fonctionnelle renvoyee telle quelle a Jeedom."""


def setup_logging(lvl_str):
    lvl = {'debug': logging.DEBUG, 'info': logging.INFO, 'warning': logging.WARNING, 'error': logging.ERROR}.get(lvl_str.lower(), logging.INFO)
    logging.basicConfig(level=lvl, format='[%(asctime)s] %(levelname)-5s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    # La librairie est tres bavarde en debug : on la bride sauf en debug
    if lvl > logging.DEBUG:
        logging.getLogger('roborock').setLevel(logging.WARNING)
    return logging.getLogger('roborockd')


def _int(v, default=None):
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _norm(txt):
    txt = unicodedata.normalize('NFKD', str(txt or '')).encode('ascii', 'ignore').decode('ascii')
    txt = re.sub(r'[^0-9a-zA-Z]+', ' ', txt)
    return re.sub(r'\s+', ' ', txt).strip().lower()


def _fmt_ts(ts):
    try:
        ts = int(ts)
        if ts <= 0:
            return ''
        return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return ''


def parse_time_range(text):
    """'22:00-08:00', '22h00 a 8h', '22:00;08:00' -> (sh, sm, eh, em)"""
    m = re.search(r'(\d{1,2})\s*[:hH]\s*(\d{2})?\s*(?:-|;|,|/|a|à|to|\s)+\s*(\d{1,2})\s*[:hH]?\s*(\d{2})?', str(text or ''))
    if not m:
        raise DaemonError("Plage horaire invalide : attendu HH:MM-HH:MM (ex. 22:00-08:00)")
    sh, sm, eh, em = int(m.group(1)), int(m.group(2) or 0), int(m.group(3)), int(m.group(4) or 0)
    if not (0 <= sh <= 23 and 0 <= eh <= 23 and 0 <= sm <= 59 and 0 <= em <= 59):
        raise DaemonError("Plage horaire invalide : heures 0-23, minutes 0-59")
    return sh, sm, eh, em


def parse_repeat(raw):
    """Nombre de passages (champ Titre). Vide -> 1 ; 1..3 -> valeur ; sinon erreur explicite."""
    if raw is None or str(raw).strip() == '':
        return 1
    s = str(raw).strip()
    if not re.fullmatch(r'\d{1,2}', s):
        raise DaemonError("Nombre de passages invalide : entier de 1 a 3 attendu")
    n = int(s)
    if not 1 <= n <= REPEAT_MAX:
        raise DaemonError("Nombre de passages invalide : entier de 1 a 3 attendu")
    return n


def finish_reason_label(reason):
    if reason is None:
        return ''
    name = getattr(reason, 'name', str(reason))
    for prefix, label in FINISH_REASON_LABELS:
        if name.startswith(prefix):
            return label
    return name


class JeedomCallback:
    def __init__(self, url, key, logger):
        self.url = url; self.key = key; self.logger = logger
        self._session = None

    async def send(self, data):
        try:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession()
            async with self._session.post(f"{self.url}?apikey={self.key}", json=data,
                                          timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    self.logger.warning(f"Callback HTTP {r.status}")
        except Exception as e:
            self.logger.error(f"Callback error: {e}")


class RoborockManager:
    def __init__(self, email, user_data_json, base_url, callback, logger):
        self.email          = email
        self.user_data_json = user_data_json
        self.base_url       = base_url
        self.region         = 'cn' if base_url and 'cn' in base_url.lower() else ('eu' if base_url and 'eu' in base_url.lower() else 'us')
        self.callback       = callback
        self.logger         = logger
        self.device_manager = None
        self.devices        = []
        # Cache partage entre reconnexions : evite de re-telecharger home_data
        # (quota Roborock dur, partage avec l'application mobile)
        self.cache          = InMemoryCache() if InMemoryCache else None
        self._rooms_cache   = {}
        self._reconnect_lock = None
        self._last_reconnect = 0.0
        self._was_cleaning   = {}
        self._summary_tasks  = {}
        self._online         = {}
        self._last_options   = {}
        self._raw_wash_mode  = {}
        self._map_meta       = {}
        self._map_time       = {}
        self._map_locks      = {}
        self._was_moving     = {}

    # ------------------------------------------------------------------ init
    async def initialize(self):
        if self._reconnect_lock is None:
            self._reconnect_lock = asyncio.Lock()
        self.logger.info(f"Connexion au cloud Roborock (region {self.region})...")
        user_data   = UserData.from_dict(json.loads(self.user_data_json))
        user_params = UserParams(username=self.email, user_data=user_data, base_url=self.base_url or None)
        kwargs = {'cache': self.cache} if self.cache is not None else {}
        if MAP_PARSER_CONFIG is not None:
            kwargs['map_parser_config'] = MAP_PARSER_CONFIG
        try:
            self.device_manager = await create_device_manager(user_params, **kwargs)
        except RoborockInvalidCredentials:
            self.logger.error("Identifiants invalides : refaire l'authentification par code e-mail"); raise
        except RoborockException as e:
            self.logger.error(f"Erreur Roborock: {e}"); raise
        self.devices = await self.device_manager.get_devices()
        self.logger.info(f"{len(self.devices)} appareil(s) trouve(s)")
        for d in self.devices:
            self.logger.info(f"  {d.name} ({d.duid}) proto={self._proto(d)}")
            if d.v1_properties is None:
                continue
            try:
                await d.v1_properties.start()
                self.logger.info(f"  Properties demarrees pour {d.duid}")
                await self._refresh_settings(d)
                await self._refresh_slow(d)
                self._register_dps(d)
            except Exception as e:
                self.logger.warning(f"  start() failed pour {d.duid}: {e}")

    def _register_dps(self, d):
        if not (hasattr(d, '_channel') and hasattr(d._channel, 'add_dps_listener')):
            return
        manager, log = self, self.logger
        pending = {'task': None}

        def on_dps(datapoints):
            log.debug(f"DPS push recu: {datapoints}")
            offline_key = RoborockDataProtocol.OFFLINE_STATUS if RoborockDataProtocol else None
            if offline_key is not None and offline_key in datapoints:
                offline = bool(datapoints[offline_key])
                if offline:
                    manager._set_online(d.duid, False)
                    asyncio.ensure_future(manager.callback.send({
                        'device_id': d.duid, 'action': 'update', 'status': 'offline',
                        'online': 0, 'last_update': manager._now()}))
                    asyncio.ensure_future(manager.reconnect('OFFLINE_STATUS', delay=10,
                                                            min_interval=OFFLINE_RECONNECT_MIN_INTERVAL_S))
                    return
                # retour en ligne : on relit l'etat complet
            if pending['task'] and not pending['task'].done():
                pending['task'].cancel()

            async def do_refresh():
                try:
                    await asyncio.sleep(2)  # anti-rebond
                    await manager.push_status(d.duid, refresh=True)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    log.debug(f"DPS refresh error: {e}")
            pending['task'] = asyncio.ensure_future(do_refresh())

        d._channel.add_dps_listener(on_dps)
        self.logger.info(f"  DPS listener enregistre pour {d.duid}")

    async def reconnect(self, reason, delay=0, min_interval=0):
        """Reconnexion MQTT bornee : jamais deux en parallele, intervalle minimal."""
        if delay:
            await asyncio.sleep(delay)
        if self._reconnect_lock is None:
            self._reconnect_lock = asyncio.Lock()
        if self._reconnect_lock.locked():
            self.logger.debug(f"Reconnexion ({reason}) ignoree : deja en cours")
            return False
        async with self._reconnect_lock:
            elapsed = time.monotonic() - self._last_reconnect
            if min_interval and elapsed < min_interval:
                self.logger.info(f"Reconnexion ({reason}) reportee : derniere il y a {int(elapsed)} s")
                return False
            self._last_reconnect = time.monotonic()
            self.logger.info(f"Reconnexion du client MQTT ({reason})")
            try:
                if self.device_manager is not None:
                    await self.device_manager.close()
                await asyncio.sleep(2)
                await self.initialize()
                self.logger.info("Reconnexion OK")
                return True
            except Exception as e:
                self.logger.warning(f"Reconnexion echouee: {e}")
                return False

    # ------------------------------------------------------------ utilitaires
    @staticmethod
    def _now():
        return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def _proto(self, d):
        if d.v1_properties is not None:          return 'v1'
        if getattr(d, 'dyad', None) is not None: return 'dyad'
        if getattr(d, 'zeo',  None) is not None: return 'zeo'
        return 'unknown'

    def _get(self, device_id):
        for d in self.devices:
            if d.duid == device_id: return d
        return None

    def _set_online(self, duid, value):
        self._online[duid] = bool(value)

    async def _ensure_started(self, d):
        if d.v1_properties is None: return False
        if not getattr(d.v1_properties, '_unsub', None):
            try:
                await asyncio.wait_for(d.v1_properties.start(), timeout=5.0)
                self.logger.info(f"Properties demarrees (retry) pour {d.duid}")
            except Exception as e:
                self.logger.debug(f"start() retry failed pour {d.duid}: {e}")
        return True

    async def _safe_refresh(self, prop, name, timeout=8.0):
        if prop is None:
            return False
        try:
            await asyncio.wait_for(prop.refresh(), timeout=timeout)
            self.logger.debug(f"refresh OK: {name}")
            return True
        except Exception as e:
            self.logger.debug(f"refresh {name}: {type(e).__name__} {e}")
            return False

    async def _refresh_status(self, d, timeout=5.0):
        ok = await self._safe_refresh(d.v1_properties.status, 'status', timeout)
        if ok:
            self._set_online(d.duid, True)
        return ok

    async def _refresh_settings(self, d):
        p = d.v1_properties
        await asyncio.gather(*[self._safe_refresh(prop, name) for name, prop in [
            ('child_lock', p.child_lock), ('led_status', p.led_status), ('dnd', p.dnd),
            ('sound_volume', p.sound_volume),
            ('valley_electricity_timer', getattr(p, 'valley_electricity_timer', None)),
            ('dust_collection_mode', getattr(p, 'dust_collection_mode', None)),
            ('wash_towel_mode', getattr(p, 'wash_towel_mode', None)),
        ] if prop is not None])
        if getattr(p, 'wash_towel_mode', None) is None and self._capabilities(d).get('wash_station'):
            await self._read_raw_wash_mode(d)

    async def _read_raw_wash_mode(self, d):
        """Station avec lavage non reconnue par la librairie : lecture directe du mode."""
        try:
            resp = await asyncio.wait_for(d.v1_properties.command.send(RoborockCommand.GET_WASH_TOWEL_MODE), 8.0)
            if isinstance(resp, list) and resp:
                resp = resp[0]
            code = resp.get('wash_mode') if isinstance(resp, dict) else resp
            if isinstance(code, int) and not isinstance(code, bool):
                self._raw_wash_mode[d.duid] = code
        except Exception as e:
            self.logger.debug(f"lecture brute wash_towel_mode: {e}")

    async def _refresh_slow(self, d):
        p = d.v1_properties
        await self._safe_refresh(p.consumables, 'consumables')
        await self._safe_refresh(getattr(p, 'clean_summary', None), 'clean_summary', timeout=15.0)

    # ------------------------------------------------------- modes / options
    def _features(self, d):
        """Capacites du robot, ou None tant que la decouverte n'a pas abouti
        (avant decouverte la librairie met tous les drapeaux a False)."""
        feats = getattr(d.v1_properties, 'device_features', None)
        if feats is None:
            return None
        try:
            from dataclasses import fields as _fields
            if not any(getattr(feats, f.name, False) is True for f in _fields(feats)):
                return None
        except Exception:
            pass
        return feats

    def _fan_options(self, d):
        """[(code, cle, libelle)] des puissances d'aspiration supportees par CE robot."""
        feats = self._features(d)
        out = []
        if feats is not None and get_clean_modes is not None:
            try:
                for m in get_clean_modes(feats):
                    key = FAN_MAPPING.get(m.code, str(m.value))
                    if m.code == 105 and str(m.value) == 'gentle':
                        key = 'gentle'
                    out.append((m.code, key, FAN_LABELS.get(key, str(m.value))))
            except Exception as e:
                self.logger.debug(f"fan options: {e}")
        if not out:
            out = [(c, k, FAN_LABELS.get(k, k)) for c, k in FAN_MAPPING.items() if c != 109]
        return out

    def _water_options(self, d):
        feats = self._features(d)
        out = []
        if feats is not None and get_water_mode_mapping is not None:
            try:
                for code, value in get_water_mode_mapping(feats).items():
                    key = WATER_MAPPING.get(code, str(value))
                    out.append((code, key, WATER_LABELS.get(key, str(value))))
            except Exception as e:
                self.logger.debug(f"water options: {e}")
        if not out:
            out = [(c, k, WATER_LABELS.get(k, k)) for c, k in WATER_MAPPING.items()]
        return out

    def _route_options(self, d):
        feats = self._features(d)
        out = []
        if feats is not None and get_clean_routes is not None:
            try:
                for r in get_clean_routes(feats, self.region):
                    key = str(r.value)
                    out.append((r.code, key, ROUTE_LABELS.get(key, key)))
            except Exception as e:
                self.logger.debug(f"route options: {e}")
        if not out:
            out = [(c, k, ROUTE_LABELS.get(k, k)) for c, k in MOP_MAPPING.items() if c != 305]
        return out

    def _dust_mode_options(self, d):
        if RoborockDockDustCollectionModeCode is None:
            return []
        return [(int(m), m.name, DUST_MODE_LABELS.get(m.name, m.name))
                for m in RoborockDockDustCollectionModeCode if m.name != 'unknown']

    def _wash_mode_options(self, d):
        feats = self._features(d)
        if feats is None or get_wash_towel_modes is None:
            return []
        try:
            return [(m.code, str(m.value), WASH_MODE_LABELS.get(str(m.value), str(m.value)))
                    for m in get_wash_towel_modes(feats)]
        except Exception:
            return []

    @staticmethod
    def _key_for(code, options, legacy):
        if code is None:
            return ''
        for c, k, _ in options:
            if c == code:
                return k
        return legacy.get(code, str(code))

    @staticmethod
    def _code_for(value, options, legacy_reverse):
        """Cle (ou code numerique) -> code. Les options du robot sont prioritaires."""
        v = str(value).strip()
        for c, k, _ in options:
            if k == v:
                return c
        if v.isdigit():
            return int(v)
        if v in legacy_reverse:
            return legacy_reverse[v]
        raise DaemonError(f"Valeur '{v}' non supportee par ce robot")

    def _options_payload(self, d):
        if self._features(d) is None:
            return {}  # listes inconnues : on ne touche pas aux listes de Jeedom
        def lv(opts):
            seen, out = set(), []
            for _c, k, label in opts:
                if k in seen:
                    continue
                seen.add(k)
                out.append([k, label])
            return out
        caps = self._capabilities(d)
        payload = {
            'fan_speed': lv(self._fan_options(d)),
            'mop_intensity': lv(self._water_options(d)) if caps.get('mop', True) else [],
            'mop_mode': lv(self._route_options(d)) if caps.get('mop', True) else [],
        }
        if caps.get('dust_mode'):
            payload['dust_collection_mode'] = lv(self._dust_mode_options(d))
        if caps.get('wash_mode'):
            payload['wash_towel_mode'] = lv(self._wash_mode_options(d))
        return payload

    def _dock_type(self, d):
        return getattr(d.v1_properties.status, 'dock_type', None)

    def _capabilities(self, d):
        """Capacites declarees par le robot (None = inconnu -> ne rien masquer)."""
        p = d.v1_properties
        feats = self._features(d)
        dock_type = self._dock_type(d)
        caps = {}
        if dock_type is not None and is_valid_dock is not None:
            caps['has_dock'] = bool(is_valid_dock(dock_type))
            caps['wash_station'] = bool(is_wash_n_fill_dock(dock_type)) or _int(dock_type) in EXTRA_WASH_DOCKS \
                or bool(_int(getattr(p.status, 'dss', None), 0))
        if feats is not None:
            for name, attr in [('child_lock', 'is_set_child_supported'),
                               ('valley', 'is_supported_valley_electricity'),
                               ('mop', 'is_support_water_mode')]:
                v = getattr(feats, attr, None)
                if v is not None:
                    caps[name] = bool(v)
        caps['dust_mode'] = getattr(p, 'dust_collection_mode', None) is not None
        caps['wash_mode'] = getattr(p, 'wash_towel_mode', None) is not None or bool(caps.get('wash_station'))
        caps['led'] = getattr(p, 'led_status', None) is not None
        st = p.status
        if st is not None and getattr(st, 'state', None) is not None:
            caps['repeat'] = getattr(st, 'repeat', None) is not None
        c = p.consumables
        if c is not None and getattr(c, 'main_brush_work_time', None) is not None:
            caps['cleaning_brush'] = getattr(c, 'cleaning_brush_work_times', None) is not None
            caps['strainer'] = getattr(c, 'strainer_work_times', None) is not None
            caps['dust_bag'] = getattr(c, 'dust_collection_work_times', None) is not None
        return caps

    # ------------------------------------------------------------ inventaire
    def get_devices_list(self):
        out = []
        for d in self.devices:
            out.append({
                'device_id': d.duid,
                'name':      d.name or f'Roborock {d.duid[:8]}',
                'model':     d.product.model if d.product else 'unknown',
                'ip':        getattr(d, 'localIP', '') or '',
                'firmware':  getattr(d.device_info, 'fv', '') if d.device_info else '',
                'serial':    getattr(d, 'sn', d.duid) or d.duid,
                'protocol':  self._proto(d),
            })
        return out

    # ----------------------------------------------------------------- etat
    async def get_status(self, device_id, refresh=False, full=False):
        d = self._get(device_id)
        if not d: return {'error': f'Device {device_id} not found'}
        if d.v1_properties is None: return {'device_id': device_id, 'error': 'not_v1'}
        try:
            await self._ensure_started(d)
            if refresh:
                ok = await self._refresh_status(d)
                if not ok:
                    self._set_online(d.duid, False)
            if full:
                await self._refresh_settings(d)
                await self._refresh_slow(d)
            return self._parse(device_id, d)
        except Exception as e:
            self.logger.error(f"get_status {device_id}: {e}")
            return {'device_id': device_id, 'error': str(e)}

    async def push_status(self, device_id, refresh=False, full=False):
        data = await self.get_status(device_id, refresh=refresh, full=full)
        if data.get('error'):
            return data
        self._track_cleaning(device_id, data)
        data['action'] = 'update'
        await self.callback.send(data)
        return data

    def _track_cleaning(self, duid, data):
        """Detecte la fin d'un nettoyage pour relire le journal (dernier nettoyage)."""
        now_cleaning = bool(data.get('is_cleaning'))
        was = self._was_cleaning.get(duid)
        self._was_cleaning[duid] = now_cleaning
        if was and not now_cleaning:
            task = self._summary_tasks.get(duid)
            if task and not task.done():
                task.cancel()
            self._summary_tasks[duid] = asyncio.ensure_future(self._follow_summary(duid))

    async def _follow_summary(self, duid):
        d = self._get(duid)
        if not d or d.v1_properties is None:
            return
        cs = getattr(d.v1_properties, 'clean_summary', None)
        if cs is None:
            return
        previous = (cs.records or [None])[0] if getattr(cs, 'records', None) else None
        for delay in SUMMARY_RETRY_DELAYS:
            await asyncio.sleep(delay)
            d = self._get(duid)  # l'objet peut changer apres une reconnexion
            if not d or d.v1_properties is None:
                return
            cs = d.v1_properties.clean_summary
            if await self._safe_refresh(cs, 'clean_summary', timeout=15.0):
                first = (cs.records or [None])[0] if cs.records else None
                if first is not None and first != previous:
                    self.logger.info(f"Journal mis a jour pour {duid} (nettoyage {first})")
                    await self.push_status(duid)
                    return
        self.logger.info(f"Journal : pas de nouveau nettoyage enregistre pour {duid} apres 30 min")

    def _parse(self, device_id, d):
        props = d.v1_properties
        data = {'device_id': device_id, 'last_update': self._now()}
        online = self._online.get(d.duid)
        if online is not None:
            data['online'] = 1 if online else 0
        state_int = 0
        try:
            s = props.status
            if s is not None and getattr(s, 'state', None) is not None:
                state_int = _int(s.state, 0)
                data['status']  = STATE_NAMES.get(state_int, f'state_{state_int}')
                data['battery'] = _int(getattr(s, 'battery', 0), 0)

                fan_int   = _int(getattr(s, 'fan_power', None))
                water_int = _int(getattr(s, 'water_box_mode', None))
                mop_int   = _int(getattr(s, 'mop_mode', None))
                data['fan_speed']     = self._key_for(fan_int, self._fan_options(d), FAN_MAPPING)
                data['mop_intensity'] = self._key_for(water_int, self._water_options(d), WATER_MAPPING)
                data['mop_mode']      = self._key_for(mop_int, self._route_options(d), MOP_MAPPING)

                mop_carriage = _int(getattr(s, 'water_box_carriage_status', 0), 0)
                water_box    = _int(getattr(s, 'water_box_status', 0), 0)
                data['mop_attached']       = 1 if (mop_carriage and water_box) else 0
                data['water_box_attached'] = water_box
                data['water_shortage']     = _int(getattr(s, 'water_shortage_status', 0), 0)

                if water_int is None or water_int == 200:
                    data['clean_type'] = 'vacuum'
                elif fan_int in (105, 109):
                    data['clean_type'] = 'mop'
                else:
                    data['clean_type'] = 'vac_and_mop'

                error_val = getattr(s, 'error_code', None)
                error_int = _int(error_val, 0)
                error_name = getattr(error_val, 'name', str(error_int)) if error_val is not None else 'none'
                data['vacuum_error']       = error_int
                data['vacuum_error_label'] = ERROR_CODES.get(error_int, error_name)
                data['vacuum_has_error']   = 1 if error_int != 0 else 0

                dock_err_val = getattr(s, 'dock_error_status', None)
                dock_err_int = _int(dock_err_val, 0)
                dock_err_name = getattr(dock_err_val, 'name', str(dock_err_int)) if dock_err_val is not None else 'ok'
                data['dock_error']       = dock_err_int
                data['dock_error_label'] = DOCK_ERROR_CODES.get(dock_err_int, f'Erreur de station non reconnue ({dock_err_name})')
                data['dock_has_error']   = 1 if dock_err_int != 0 else 0

                self._parse_dss(s, state_int, dock_err_int, data)

                data['is_charging']  = 1 if state_int in (8, 100) else 0
                data['is_cleaning']  = 1 if state_int in CLEANING_STATES else 0
                data['is_paused']    = 1 if state_int == STATE_PAUSED else 0
                data['in_returning'] = _int(getattr(s, 'in_returning', 0), 0)
                data['charge_status']   = _int(getattr(s, 'charge_status', 0), 0)
                data['dry_status']      = _int(getattr(s, 'dry_status', 0), 0)
                data['wash_status']     = _int(getattr(s, 'wash_status', 0), 0)
                data['dust_collection'] = _int(getattr(s, 'dust_collection_status', 0), 0)

                data['cleaning_area']     = round(_int(getattr(s, 'clean_area', 0), 0) / 1000000, 2)
                data['cleaning_time']     = round(_int(getattr(s, 'clean_time', 0), 0) / 60, 1)
                data['cleaning_progress'] = _int(getattr(s, 'clean_percent', None), 0)
                dnd_val = getattr(s, 'dnd_enabled', None)
                if dnd_val is not None:
                    data['do_not_disturb'] = _int(dnd_val, 0)

                last_t = _int(getattr(s, 'last_clean_t', None))
                clean_time_s = _int(getattr(s, 'clean_time', 0), 0)
                if last_t and last_t > 0:
                    data['last_clean_end'] = _fmt_ts(last_t)
                    if clean_time_s > 0:
                        data['last_clean_begin'] = _fmt_ts(last_t - clean_time_s)
        except Exception as e:
            self.logger.warning(f"parse status: {e}")

        self._parse_consumables(props, data)
        self._parse_settings(props, data)
        if 'wash_towel_mode' not in data and d.duid in self._raw_wash_mode:
            code = self._raw_wash_mode[d.duid]
            data['wash_towel_mode'] = self._key_for(code, self._wash_mode_options(d), {})
        self._parse_summary(props, data)

        try:
            data['options'] = self._options_payload(d)
            data['capabilities'] = self._capabilities(d)
        except Exception as e:
            self.logger.debug(f"options/capabilities: {e}")
        return data

    def _parse_dss(self, s, state_int, dock_err_int, data):
        try:
            dss_int = _int(getattr(s, 'dss', None), 0)
            if dss_int <= 0:
                return
            clear_water = (dss_int >> 2) & 3
            dirty_water = (dss_int >> 4) & 3
            dust_bag    = (dss_int >> 6) & 3
            data['dock_clear_water_status'] = clear_water
            data['dock_dirty_water_status'] = dirty_water
            data['dock_dust_bag_status']    = dust_bag
            # Les bits DSS ne sont fiables que robot a la base : sinon on garde la derniere valeur
            if state_int not in DOCKED_STATES:
                return
            data['clear_water_empty'] = 1 if clear_water in WATER_ALERT_VALUES else 0
            data['dirty_water_full']  = 1 if dirty_water in WATER_ALERT_VALUES else 0
            data['dust_bag_alert']    = 1 if dust_bag in DUST_BAG_ALERT_VALUES else 0
            if dock_err_int == 0:
                problems = []
                if data['clear_water_empty']: problems.append('Reservoir eau propre vide ou absent')
                if data['dirty_water_full']:  problems.append('Bac eau sale plein ou absent')
                if data['dust_bag_alert']:    problems.append('Sac a poussiere absent')
                if problems:
                    data['dock_has_error']   = 1
                    data['dock_error_label'] = ', '.join(problems)
                    data['dock_error']       = dss_int
        except Exception as e:
            self.logger.debug(f"parse dss: {e}")

    def _parse_consumables(self, props, data):
        try:
            c = props.consumables
            if c is None or getattr(c, 'main_brush_work_time', None) is None:
                return
            def h(v): return round(int(v or 0) / 3600, 1)
            def left_h(w, m): return round(max(0, (m - int(w or 0)) / 3600), 1)
            def pct(w, m): return round(max(0, 100 - (int(w or 0) / m * 100)), 1) if m > 0 else 0
            mbt = c.main_brush_work_time or 0
            sbt = getattr(c, 'side_brush_work_time', 0) or 0
            ft  = getattr(c, 'filter_work_time', 0) or 0
            sdt = getattr(c, 'sensor_dirty_time', 0) or 0
            data['main_brush_work_time'] = h(mbt)
            data['side_brush_work_time'] = h(sbt)
            data['filter_work_time']     = h(ft)
            data['sensor_dirty_time']    = h(sdt)
            data['main_brush_time_left'] = left_h(mbt, MAIN_BRUSH_MAX)
            data['side_brush_time_left'] = left_h(sbt, SIDE_BRUSH_MAX)
            data['filter_time_left']     = left_h(ft,  FILTER_MAX)
            data['sensor_time_left']     = left_h(sdt, SENSOR_MAX)
            data['main_brush_pct']       = pct(mbt, MAIN_BRUSH_MAX)
            data['side_brush_pct']       = pct(sbt, SIDE_BRUSH_MAX)
            data['filter_pct']           = pct(ft,  FILTER_MAX)
            data['sensor_pct']           = pct(sdt, SENSOR_MAX)
            mrt = getattr(c, 'moproller_work_time', None)
            if mrt is not None:
                data['moproller_work_time'] = h(mrt)
                data['moproller_time_left'] = left_h(mrt, MOP_ROLLER_MAX)
                data['moproller_pct']       = pct(mrt, MOP_ROLLER_MAX)
            # Consommables de station : publies seulement si le robot remonte le compteur
            for raw, work_key, pct_key, mx in [
                ('strainer_work_times',        'strainer_work_times',        'strainer_pct',  STRAINER_MAX),
                ('dust_collection_work_times', 'dust_collection_work_times', 'dust_coll_pct', DUST_COLL_MAX),
                ('cleaning_brush_work_times',  'cleaning_brush_work_times',  'cleaning_pct',  CLEANING_MAX),
            ]:
                v = getattr(c, raw, None)
                if v is not None:
                    data[work_key] = int(v)
                    data[pct_key]  = pct(v, mx)
        except Exception as e:
            self.logger.warning(f"parse consumables: {e}")

    def _parse_settings(self, props, data):
        def timer(t, prefix):
            if t is None or getattr(t, 'enabled', None) is None:
                return
            data[prefix] = 1 if t.enabled == 1 else 0
            if t.start_hour is not None:
                data[prefix + '_begin'] = f"{int(t.start_hour):02d}:{int(t.start_minute or 0):02d}"
                data[prefix + '_end']   = f"{int(t.end_hour or 0):02d}:{int(t.end_minute or 0):02d}"
        try:
            timer(props.dnd, 'do_not_disturb')
            timer(getattr(props, 'valley_electricity_timer', None), 'valley')
        except Exception as e:
            self.logger.warning(f"parse timers: {e}")
        try:
            sv = props.sound_volume
            if sv is not None and getattr(sv, 'volume', None) is not None:
                data['volume'] = int(sv.volume)
        except Exception as e:
            self.logger.warning(f"parse sound_volume: {e}")
        try:
            cl = props.child_lock
            if cl is not None and getattr(cl, 'lock_status', None) is not None:
                data['child_lock'] = 1 if cl.lock_status == 1 else 0
        except Exception as e:
            self.logger.warning(f"parse child_lock: {e}")
        try:
            led = props.led_status
            if led is not None and getattr(led, 'status', None) is not None:
                data['led_status'] = int(led.status)
        except Exception as e:
            self.logger.warning(f"parse led_status: {e}")
        try:
            dm = getattr(props, 'dust_collection_mode', None)
            if dm is not None and getattr(dm, 'mode', None) is not None:
                name = getattr(dm.mode, 'name', str(dm.mode))
                data['dust_collection_mode'] = name if name != 'unknown' else f'mode_{int(dm.mode)}'
            wm = getattr(props, 'wash_towel_mode', None)
            if wm is not None and getattr(wm, 'wash_mode', None) is not None:
                data['wash_towel_mode'] = str(getattr(wm.wash_mode, 'value', wm.wash_mode))
        except Exception as e:
            self.logger.warning(f"parse station modes: {e}")

    def _parse_summary(self, props, data):
        try:
            cs = getattr(props, 'clean_summary', None)
            if cs is None or getattr(cs, 'clean_time', None) is None:
                return
            data['total_clean_time'] = round(int(cs.clean_time or 0) / 3600, 1)
            if isinstance(cs.clean_area, int):
                data['total_clean_area'] = round(cs.clean_area / 1000000, 1)
            if cs.clean_count is not None:
                data['total_clean_count'] = int(cs.clean_count)
            if getattr(cs, 'dust_collection_count', None) is not None:
                data['total_dust_collection_count'] = int(cs.dust_collection_count)
            rec = getattr(cs, 'last_clean_record', None)
            if rec is not None and rec.begin:
                data['last_clean_begin'] = _fmt_ts(rec.begin)
                if rec.end:
                    data['last_clean_end'] = _fmt_ts(rec.end)
                if rec.duration is not None:
                    data['last_clean_duration'] = round(int(rec.duration) / 60, 1)
                if rec.area is not None:
                    data['last_clean_area'] = round(int(rec.area) / 1000000, 1)
                data['last_clean_finish_reason'] = finish_reason_label(rec.finish_reason) or ('Termine' if rec.complete else '')
                if rec.complete is not None:
                    data['last_clean_complete'] = 1 if rec.complete else 0
                err = _int(rec.error, 0)
                data['last_clean_error'] = ERROR_CODES.get(err, str(err)) if err else 'Aucune erreur'
        except Exception as e:
            self.logger.warning(f"parse clean_summary: {e}")

    # ------------------------------------------------------------------ carte
    def map_paths(self, duid):
        safe = re.sub(r'[^0-9A-Za-z_-]', '', duid)
        return os.path.join(DATA_DIR, f'map_{safe}.png'), os.path.join(DATA_DIR, f'map_{safe}.json')

    @staticmethod
    def _affine(calibration):
        """3 points de calibration (vacuum mm -> pixel image) -> coefficients
        px = a*x + b*y + c ; py = d*x + e*y + f"""
        (v0, m0), (v1, m1), (v2, m2) = [((p['vacuum']['x'], p['vacuum']['y']), (p['map']['x'], p['map']['y']))
                                         for p in calibration[:3]]
        dx = v1[0] - v0[0]
        dy = v2[1] - v0[1]
        if not dx or not dy:
            raise ValueError('calibration degeneree')
        a = (m1[0] - m0[0]) / dx; d = (m1[1] - m0[1]) / dx
        b = (m2[0] - m0[0]) / dy; e = (m2[1] - m0[1]) / dy
        c = m0[0] - a * v0[0] - b * v0[1]
        f = m0[1] - d * v0[0] - e * v0[1]
        return [a, b, c, d, e, f]

    def _room_names(self, duid):
        names = {}
        for r in self._rooms_cache.get(duid, []) or []:
            names[int(r['segment_id'])] = r['name']
        return names

    async def refresh_map(self, duid, reason=''):
        d = self._get(duid)
        if not d or d.v1_properties is None:
            raise DaemonError('Robot inconnu')
        trait = getattr(d.v1_properties, 'map_content', None)
        if trait is None or not hasattr(getattr(trait, 'converter', None), 'parse_map_content'):
            raise DaemonError('Carte non disponible avec cette version de python-roborock')
        lock = self._map_locks.setdefault(duid, asyncio.Lock())
        if lock.locked():
            return self._map_meta.get(duid, {})
        async with lock:
            try:
                raw = await asyncio.wait_for(trait.rpc_channel.send_command(trait.command), MAP_TIMEOUT_S)
            except asyncio.TimeoutError:
                raise DaemonError('Carte : le robot ne repond pas (delai depasse)')
            if not isinstance(raw, (bytes, bytearray)) or not raw:
                raise DaemonError('Carte : reponse vide du robot')
            try:
                content = await asyncio.wait_for(
                    asyncio.to_thread(trait.converter.parse_map_content, bytes(raw)), MAP_PARSE_TIMEOUT_S)
            except Exception as e:
                raise DaemonError(f'Carte illisible ({type(e).__name__})')
            png = content.image_content
            md = content.map_data
            if not png or md is None:
                raise DaemonError('Carte illisible (image vide)')
            try:
                png, crop = await asyncio.to_thread(self._crop_png, png)
            except Exception as e:
                self.logger.debug(f"recadrage carte: {e}")
                crop = (0, 0)
            if not self._rooms_cache.get(duid):
                try:
                    await self.get_rooms(duid, force=True)
                except Exception:
                    pass
            meta = self._build_map_meta(d, md, png, crop)
            os.makedirs(DATA_DIR, exist_ok=True)
            png_path, json_path = self.map_paths(duid)
            for path, payload in ((png_path, png), (json_path, json.dumps(meta).encode())):
                tmp = path + '.tmp'
                with open(tmp, 'wb') as fh:
                    fh.write(payload)
                os.replace(tmp, path)
            self._map_meta[duid] = meta
            self._map_time[duid] = time.monotonic()
            self.logger.debug(f"Carte {duid} mise a jour ({reason}) {meta.get('width')}x{meta.get('height')}")
            return meta

    @staticmethod
    def _crop_png(png, margin=20):
        """Recadre l'image sur la zone utile (le fond uni est retire). Retourne (png, (dx, dy))."""
        import io
        from PIL import Image, ImageChops
        img = Image.open(io.BytesIO(png))
        img.load()
        rgb = img.convert('RGB')
        bg = Image.new('RGB', rgb.size, rgb.getpixel((0, 0)))
        box = ImageChops.difference(rgb, bg).getbbox()
        if not box:
            return png, (0, 0)
        left = max(0, box[0] - margin); top = max(0, box[1] - margin)
        right = min(img.width, box[2] + margin); bottom = min(img.height, box[3] + margin)
        if (right - left) * (bottom - top) >= img.width * img.height * 0.95:
            return png, (0, 0)
        out = io.BytesIO()
        img.crop((left, top, right, bottom)).save(out, format='PNG', optimize=True)
        return out.getvalue(), (left, top)

    def _build_map_meta(self, d, md, png, crop=(0, 0)):
        import struct
        width = height = None
        if png[:8] == b'\x89PNG\r\n\x1a\n':
            width, height = struct.unpack('>II', png[16:24])
        meta = {'ts': int(time.time()), 'updated': self._now(), 'width': width, 'height': height,
                'affine': None, 'robot': None, 'charger': None, 'rooms': [],
                'current_room': None, 'current_segment': None, 'no_go': [], 'walls': []}
        try:
            cal = md.calibration()
            if cal:
                aff = self._affine(cal)
                aff[2] -= crop[0]
                aff[5] -= crop[1]
                meta['affine'] = aff
        except Exception as e:
            self.logger.debug(f"calibration: {e}")
        for key, attr in (('robot', 'vacuum_position'), ('charger', 'charger')):
            pt = getattr(md, attr, None)
            if pt is not None and getattr(pt, 'x', None) is not None:
                meta[key] = {'x': round(pt.x), 'y': round(pt.y), 'a': getattr(pt, 'a', None)}
        names = self._room_names(d.duid)
        for num, room in (getattr(md, 'rooms', None) or {}).items():
            meta['rooms'].append({
                'segment_id': int(num), 'name': names.get(int(num), f'Piece {num}'),
                'x0': round(room.x0), 'y0': round(room.y0), 'x1': round(room.x1), 'y1': round(room.y1)})
        for area in (getattr(md, 'no_go_areas', None) or []) + (getattr(md, 'no_mopping_areas', None) or []):
            try:
                meta['no_go'].append([round(v) for v in area.as_list()])
            except Exception:
                pass
        # Piece courante : segment sous le robot, seulement si le robot est dans le cadre de l'image
        seg = getattr(md, 'vacuum_room', None)
        inside = False
        if meta['affine'] and meta['robot'] and width and height:
            a, b, c, dd, e, f = meta['affine']
            px = a * meta['robot']['x'] + b * meta['robot']['y'] + c
            py = dd * meta['robot']['x'] + e * meta['robot']['y'] + f
            inside = 0 <= px < width and 0 <= py < height
        if inside and isinstance(seg, int) and not isinstance(seg, bool):
            meta['current_segment'] = seg
            meta['current_room'] = names.get(seg, f'Piece {seg}')
        elif inside and seg is None and meta['rooms']:
            meta['current_room'] = 'Aucune piece'
        else:
            meta['current_room'] = 'Piece inconnue'
        return meta

    async def map_tick(self, duid, state_int):
        """Relit la carte : 60 s pendant un deplacement, une fois a l'arret, 1 h au repos."""
        moving = state_int in MOVING_STATES
        was = self._was_moving.get(duid, False)
        self._was_moving[duid] = moving
        last = self._map_time.get(duid)
        age = (time.monotonic() - last) if last else None
        due = (age is None or (moving and age >= MAP_ACTIVE_EVERY_S)
               or (was and not moving) or age >= MAP_IDLE_EVERY_S)
        if not due:
            return
        try:
            meta = await self.refresh_map(duid, 'auto')
            await self.callback.send({'device_id': duid, 'action': 'update',
                                      'current_room': meta.get('current_room') or '',
                                      'map_update': meta.get('updated', '')})
        except DaemonError as e:
            self.logger.info(f"Carte {duid}: {e}")
            self._map_time[duid] = time.monotonic()  # pas de rafale de tentatives
        except Exception as e:
            self.logger.warning(f"Carte {duid}: {type(e).__name__} {e}")
            self._map_time[duid] = time.monotonic()

    # --------------------------------------------------------------- routines
    async def get_routines(self, device_id):
        d = self._get(device_id)
        if not d or d.v1_properties is None: return {'routines': []}
        try:
            routines = await d.v1_properties.routines.get_routines()
            return {'routines': [{'id': r.id, 'name': getattr(r, 'name', None) or f'Routine {r.id}'} for r in routines]}
        except Exception as e:
            self.logger.error(f"get_routines {device_id}: {e}")
            return {'routines': [], 'error': str(e)}

    # ----------------------------------------------------------------- pieces
    async def get_rooms(self, device_id, force=True):
        d = self._get(device_id)
        if not d or d.v1_properties is None:
            return []
        if not force and self._rooms_cache.get(device_id):
            return self._rooms_cache[device_id]
        rooms = []
        try:
            await asyncio.wait_for(d.v1_properties.rooms.refresh(), timeout=20.0)
            for r in d.v1_properties.rooms.rooms or []:
                rooms.append({'segment_id': int(r.segment_id), 'name': r.name})
        except Exception as e:
            self.logger.warning(f"rooms.refresh {device_id}: {e} - repli sur GET_ROOM_MAPPING")
            try:
                mapping = await d.v1_properties.command.send(RoborockCommand.GET_ROOM_MAPPING)
                for item in mapping or []:
                    if isinstance(item, (list, tuple)) and item:
                        rooms.append({'segment_id': int(item[0]), 'name': f'Piece {item[0]}'})
            except Exception as e2:
                self.logger.error(f"get_rooms {device_id}: {e2}")
                raise DaemonError(f"Lecture des pieces impossible (robot en ligne ?) : {e2}")
        if rooms:
            self._rooms_cache[device_id] = rooms
        return rooms

    async def get_maps(self, device_id):
        """Compatibilite avec l'ancien format attendu par l'ajax syncRooms."""
        try:
            rooms = await self.get_rooms(device_id, force=True)
        except DaemonError as e:
            return {'maps': [], 'error': str(e)}
        out = []
        if rooms:
            out.append({'flag': 0, 'name': 'Carte principale',
                        'rooms': {str(r['segment_id']): r['name'] for r in rooms}})
        return {'maps': out}

    async def _segments_from_names(self, device_id, names_text):
        names = [n.strip() for n in re.split(r'[,;]', str(names_text or '')) if n.strip()]
        if not names:
            raise DaemonError("Aucune piece indiquee (noms separes par des virgules)")
        for attempt in (False, True):
            rooms = await self.get_rooms(device_id, force=attempt)
            index = {_norm(r['name']): r['segment_id'] for r in rooms}
            segs, unknown = [], []
            for n in names:
                if n.isdigit():
                    segs.append(int(n)); continue
                sid = index.get(_norm(n))
                if sid is None:
                    unknown.append(n)
                else:
                    segs.append(sid)
            if not unknown:
                return segs
        raise DaemonError(f"Piece(s) inconnue(s) : {', '.join(unknown)}. Resynchronisez les pieces.")

    # ------------------------------------------------------------- gardes
    async def _guard_cleaning_order(self, d):
        """Relit l'etat (best effort) et refuse un ordre de nettoyage pendant le vidage du bac.
        Retourne True si l'etat a ete relu."""
        ok = await self._refresh_status(d, timeout=GUARD_REFRESH_S)
        if ok and _int(getattr(d.v1_properties.status, 'state', None)) == STATE_EMPTYING_BIN:
            raise DaemonError("Le robot vide son bac a poussiere : l'ordre de nettoyage n'a pas ete envoye. "
                              "Reessayez quand le vidage sera termine.")
        return ok

    async def _guard_at_base(self, d, what):
        ok = await self._refresh_status(d, timeout=GUARD_REFRESH_S)
        if not ok:
            return
        s = d.v1_properties.status
        state_int = _int(getattr(s, 'state', None), 0)
        charging = _int(getattr(s, 'charge_status', None)) == 1
        if state_int not in AT_BASE_STATES and state_int not in DOCKED_STATES and not charging:
            raise DaemonError(f"{what} : le robot doit etre a sa base (etat actuel : "
                              f"{STATE_NAMES.get(state_int, state_int)})")

    async def _guard_repeat(self, d, repeat, refreshed):
        if repeat <= 1:
            return
        if refreshed and getattr(d.v1_properties.status, 'repeat', None) is None:
            raise DaemonError("Ce robot ne gere pas le nombre de passages")

    async def _verify(self, d, attr, expected, label):
        """Relit le statut jusqu'a VERIFY_TIMEOUT_S pour confirmer qu'un reglage est applique."""
        deadline = time.monotonic() + VERIFY_TIMEOUT_S
        await asyncio.sleep(1)
        while True:
            if await self._refresh_status(d, timeout=4.0):
                if _int(getattr(d.v1_properties.status, attr, None)) == expected:
                    return {'success': True, 'message': f'{label} applique'}
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(2)
        current = _int(getattr(d.v1_properties.status, attr, None))
        self.logger.warning(f"{label} non confirme (attendu {expected}, relu {current})")
        return {'success': True, 'warning': f'{label} transmis au robot (application non confirmee)'}

    # ------------------------------------------------------------- commandes
    async def execute_command(self, device_id, action, params):
        d = self._get(device_id)
        if not d:
            return {'error': f'Device {device_id} not found'}
        if d.v1_properties is None:
            return {'error': 'not_v1'}
        try:
            result = await self._execute(d, action, params)
        except DaemonError as e:
            self.logger.info(f"cmd {action} refusee: {e}")
            return {'error': str(e)}
        except Exception as e:
            self.logger.error(f"cmd {action}: {type(e).__name__} {e}")
            return {'error': f"{type(e).__name__}: {e}" if str(e) else type(e).__name__}
        # Publication de l'etat apres action (sans bloquer la reponse)
        asyncio.ensure_future(self.push_status(device_id, refresh=action not in ('refresh',)))
        return result or {'success': True}

    async def _execute(self, d, action, params):
        p   = d.v1_properties
        cmd = p.command
        simple = {
            'pause':                 RoborockCommand.APP_PAUSE,
            'stop':                  RoborockCommand.APP_STOP,
            'dock':                  RoborockCommand.APP_CHARGE,
            'locate':                RoborockCommand.FIND_ME,
            'stop_dust_collection':  RoborockCommand.APP_STOP_COLLECT_DUST,
            'stop_wash':             RoborockCommand.APP_STOP_WASH,
        }
        resets = {
            'reset_main_brush':      'main_brush_work_time',
            'reset_side_brush':      'side_brush_work_time',
            'reset_filter':          'filter_work_time',
            'reset_sensor':          'sensor_dirty_time',
            'reset_moproller':       'moproller_work_time',
            'reset_strainer':        'strainer_work_times',
            'reset_cleaning_brush':  'cleaning_brush_work_times',
            'reset_dust_collection': 'dust_collection_work_times',
        }

        if action == 'refresh':
            await self.push_status(d.duid, refresh=True, full=True)
            return {'success': True}

        if action == 'refresh_map':
            meta = await self.refresh_map(d.duid, 'manuel')
            await self.callback.send({'device_id': d.duid, 'action': 'update',
                                      'current_room': meta.get('current_room') or '',
                                      'map_update': meta.get('updated', '')})
            return {'success': True, 'message': 'Carte mise a jour'}

        if action in ('start', 'resume'):
            refreshed = await self._guard_cleaning_order(d)
            in_cleaning = _int(getattr(p.status, 'in_cleaning', None), 0) if refreshed else 0
            state_int = _int(getattr(p.status, 'state', None), 0)
            if in_cleaning == 3:
                await cmd.send(RoborockCommand.RESUME_SEGMENT_CLEAN)
                return {'success': True, 'message': 'Reprise du nettoyage par piece'}
            if in_cleaning == 2:
                await cmd.send(RoborockCommand.RESUME_ZONED_CLEAN)
                return {'success': True, 'message': 'Reprise du nettoyage de zone'}
            if action == 'resume' and state_int != STATE_PAUSED and in_cleaning == 0 and refreshed:
                self.logger.info("resume : aucun nettoyage interrompu, lancement d'un nettoyage complet")
            await cmd.send(RoborockCommand.APP_START)
            return {'success': True}

        if action in simple:
            await cmd.send(simple[action])
            return {'success': True}

        if action == 'spot_clean':
            await self._guard_cleaning_order(d)
            await cmd.send(RoborockCommand.APP_SPOT)
            return {'success': True}

        # --- Station (robot a la base uniquement)
        if action == 'start_dust_collection':
            await self._guard_at_base(d, 'Vidage du bac')
            await cmd.send(RoborockCommand.APP_START_COLLECT_DUST)
            return {'success': True}
        if action == 'start_wash':
            await self._guard_at_base(d, 'Lavage de la serpilliere')
            await cmd.send(RoborockCommand.APP_START_WASH)
            return {'success': True}
        if action == 'start_dry':
            await self._guard_at_base(d, 'Sechage de la serpilliere')
            await cmd.send(RoborockCommand.APP_SET_DRYER_STATUS, {'status': 1})
            return {'success': True}
        if action == 'stop_dry':
            await cmd.send(RoborockCommand.APP_SET_DRYER_STATUS, {'status': 0})
            return {'success': True}

        # --- Reglages avec verification
        if action == 'set_fan_speed':
            code = self._code_for(params.get('value', ''), self._fan_options(d), {v: k for k, v in FAN_MAPPING.items()})
            await cmd.send(RoborockCommand.SET_CUSTOM_MODE, [code])
            return await self._verify(d, 'fan_power', code, "Puissance d'aspiration")
        if action == 'set_mop_intensity':
            code = self._code_for(params.get('value', ''), self._water_options(d), {v: k for k, v in WATER_MAPPING.items()})
            await cmd.send(RoborockCommand.SET_WATER_BOX_CUSTOM_MODE, [code])
            return await self._verify(d, 'water_box_mode', code, "Debit d'eau")
        if action == 'set_mop_mode':
            code = self._code_for(params.get('value', ''), self._route_options(d), {v: k for k, v in MOP_MAPPING.items() if k != 305})
            await cmd.send(RoborockCommand.SET_MOP_MODE, [code])
            return await self._verify(d, 'mop_mode', code, 'Itineraire de serpilliere')
        if action == 'set_clean_type':
            return await self._set_clean_type(d, str(params.get('value', 'vac_and_mop')))

        if action == 'set_volume':
            vol = max(0, min(100, _int(params.get('value'), 50)))
            if p.sound_volume is not None:
                await p.sound_volume.set_volume(vol)
            else:
                await cmd.send(RoborockCommand.CHANGE_SOUND_VOLUME, [vol])
            await self._safe_refresh(p.sound_volume, 'sound_volume')
            return {'success': True}

        # --- Interrupteurs
        if action in ('child_lock_on', 'child_lock_off'):
            on = action.endswith('_on')
            if p.child_lock is not None:
                await (p.child_lock.enable() if on else p.child_lock.disable())
            else:
                await cmd.send(RoborockCommand.SET_CHILD_LOCK_STATUS, {'lock_status': 1 if on else 0})
            await self._safe_refresh(p.child_lock, 'child_lock')
            return {'success': True}
        if action in ('led_on', 'led_off'):
            on = action.endswith('_on')
            if p.led_status is not None:
                await (p.led_status.enable() if on else p.led_status.disable())
            else:
                await cmd.send(RoborockCommand.SET_LED_STATUS, [1 if on else 0])
            return {'success': True}

        # --- Ne pas deranger / heures creuses
        if action in ('dnd_on', 'dnd_off', 'dnd_set_range'):
            return await self._timer_action(d, p.dnd, action[4:], RoborockCommand.SET_DND_TIMER,
                                            RoborockCommand.CLOSE_DND_TIMER, params, 'Ne pas deranger', (22, 0, 8, 0))
        if action in ('valley_on', 'valley_off', 'valley_set_range'):
            trait = getattr(p, 'valley_electricity_timer', None)
            if trait is None:
                raise DaemonError("Ce robot ne gere pas la recharge en heures creuses")
            return await self._timer_action(d, trait, action[7:], RoborockCommand.SET_VALLEY_ELECTRICITY_TIMER,
                                            RoborockCommand.CLOSE_VALLEY_ELECTRICITY_TIMER, params, 'Heures creuses', (22, 0, 6, 0))

        # --- Modes de la station
        if action == 'set_dust_collection_mode':
            trait = getattr(p, 'dust_collection_mode', None)
            if trait is None:
                raise DaemonError("Cette station ne gere pas le mode de vidage")
            code = self._code_for(params.get('value', ''), self._dust_mode_options(d), {})
            await cmd.send(RoborockCommand.SET_DUST_COLLECTION_MODE, {'mode': code})
            await self._safe_refresh(trait, 'dust_collection_mode')
            return {'success': True}
        if action == 'set_wash_towel_mode':
            trait = getattr(p, 'wash_towel_mode', None)
            if trait is None and not self._capabilities(d).get('wash_station'):
                raise DaemonError("Cette station ne gere pas le mode de lavage")
            code = self._code_for(params.get('value', ''), self._wash_mode_options(d), {})
            await cmd.send(RoborockCommand.SET_WASH_TOWEL_MODE, {'wash_mode': code})
            if trait is not None:
                await self._safe_refresh(trait, 'wash_towel_mode')
            else:
                await self._read_raw_wash_mode(d)
            return {'success': True}

        # --- Consommables
        if action in resets:
            await cmd.send(RoborockCommand.RESET_CONSUMABLE, [resets[action]])
            await self._safe_refresh(p.consumables, 'consumables')
            return {'success': True}

        # --- Nettoyages cibles
        if action in ('clean_segment', 'clean_rooms'):
            repeat = parse_repeat(params.get('repeat'))
            if action == 'clean_rooms':
                segments = await self._segments_from_names(d.duid, params.get('rooms', ''))
            else:
                segments = [int(x) for x in params.get('segments', []) if str(x).strip().lstrip('-').isdigit()]
            if not segments:
                raise DaemonError("Aucune piece a nettoyer")
            refreshed = await self._guard_cleaning_order(d)
            await self._guard_repeat(d, repeat, refreshed)
            self.logger.info(f"clean_segment: segments={segments} repeat={repeat}")
            await cmd.send(RoborockCommand.APP_SEGMENT_CLEAN, [{'segments': segments, 'repeat': repeat}])
            return {'success': True}

        if action == 'clean_zone':
            repeat = parse_repeat(params.get('repeat'))
            zones = self._parse_zones(params.get('zones', ''))
            refreshed = await self._guard_cleaning_order(d)
            await self._guard_repeat(d, repeat, refreshed)
            await cmd.send(RoborockCommand.APP_ZONED_CLEAN, [{'repeats': repeat, 'zones': zones}])
            return {'success': True}

        if action == 'goto_position':
            await cmd.send(RoborockCommand.APP_GOTO_TARGET, [_int(params.get('x'), 25500), _int(params.get('y'), 25500)])
            return {'success': True}

        if action == 'execute_routine':
            await p.routines.execute_routine(int(params.get('routine_id', 0)))
            return {'success': True}

        raise DaemonError(f'Action inconnue : {action}')

    @staticmethod
    def _parse_zones(raw):
        """'x1,y1,x2,y2' ou plusieurs zones separees par ';' -> [[x1,y1,x2,y2], ...]"""
        if isinstance(raw, list):
            raw = ';'.join(','.join(str(v) for v in z) if isinstance(z, (list, tuple)) else str(z) for z in raw)
        zones = []
        for part in str(raw or '').split(';'):
            nums = [int(float(n)) for n in re.findall(r'-?\d+(?:\.\d+)?', part)]
            if not nums:
                continue
            if len(nums) != 4:
                raise DaemonError("Zone invalide : attendu x1,y1,x2,y2 (en mm), zones separees par ';'")
            x1, y1, x2, y2 = nums
            zones.append([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)])
        if not zones:
            raise DaemonError("Zone invalide : attendu x1,y1,x2,y2 (en mm)")
        return zones

    async def _timer_action(self, d, trait, op, set_cmd, close_cmd, params, label, default):
        cmd = d.v1_properties.command
        if op == 'off':
            await cmd.send(close_cmd)
        else:
            if op == 'set_range':
                sh, sm, eh, em = parse_time_range(params.get('value', ''))
            else:
                if trait is not None and getattr(trait, 'start_hour', None) is None:
                    await self._safe_refresh(trait, label)
                if trait is not None and getattr(trait, 'start_hour', None) is not None:
                    sh, sm, eh, em = trait.start_hour, trait.start_minute or 0, trait.end_hour or 0, trait.end_minute or 0
                else:
                    sh, sm, eh, em = default
            await cmd.send(set_cmd, [sh, sm, eh, em])
        await asyncio.sleep(1)
        await self._safe_refresh(trait, label)
        return {'success': True}

    async def _set_clean_type(self, d, val):
        cmd = d.v1_properties.command
        st  = d.v1_properties.status
        fan_opts   = self._fan_options(d)
        water_opts = self._water_options(d)
        fan_codes   = [c for c, _, _ in fan_opts]
        water_codes = [c for c, _, _ in water_opts if c != 200]
        off_fan = 109 if 109 in fan_codes else 105
        cur_fan   = _int(getattr(st, 'fan_power', None))
        cur_water = _int(getattr(st, 'water_box_mode', None))

        def mid_water():
            if cur_water and cur_water != 200:
                return cur_water
            for pref in (245, 235, 202, 201):
                if pref in water_codes:
                    return pref
            return water_codes[len(water_codes) // 2] if water_codes else 202

        def normal_fan():
            if cur_fan and cur_fan not in (105, 109):
                return cur_fan
            return 102

        if val == 'vacuum':
            await cmd.send(RoborockCommand.SET_CUSTOM_MODE, [normal_fan()])
            await asyncio.sleep(1)
            await cmd.send(RoborockCommand.SET_WATER_BOX_CUSTOM_MODE, [200])
            return await self._verify(d, 'water_box_mode', 200, 'Mode aspiration seule')
        if val == 'mop':
            if off_fan not in fan_codes:
                raise DaemonError("Ce robot ne gere pas le lavage seul")
            await cmd.send(RoborockCommand.SET_WATER_BOX_CUSTOM_MODE, [mid_water()])
            await asyncio.sleep(1)
            await cmd.send(RoborockCommand.SET_CUSTOM_MODE, [off_fan])
            return await self._verify(d, 'fan_power', off_fan, 'Mode lavage seul')
        fan = normal_fan()
        await cmd.send(RoborockCommand.SET_CUSTOM_MODE, [fan])
        await asyncio.sleep(1)
        await cmd.send(RoborockCommand.SET_WATER_BOX_CUSTOM_MODE, [mid_water()])
        return await self._verify(d, 'fan_power', fan, 'Mode aspiration et lavage')


class SocketServer:
    def __init__(self, port, manager, logger):
        self.port = port; self.manager = manager; self.logger = logger
        self.running = False; self.loop = None

    def start(self, loop):
        self.loop = loop; self.running = True
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('127.0.0.1', self.port)); srv.listen(5); srv.settimeout(1.0)
        self.logger.info(f"Socket en ecoute port {self.port}")
        while self.running:
            try:
                conn, _ = srv.accept()
                threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
            except socket.timeout: continue
            except Exception as e:
                if self.running: self.logger.error(f"Socket error: {e}")
        srv.close()

    def _handle(self, conn):
        try:
            conn.settimeout(10)
            buf = b''
            while True:
                chunk = conn.recv(4096)
                if not chunk: break
                buf += chunk
                if b'\n' in buf: break
            if not buf: conn.close(); return
            payload = json.loads(buf.decode().strip())
            future  = asyncio.run_coroutine_threadsafe(self._dispatch(payload), self.loop)
            result  = future.result(timeout=45)
            conn.sendall((json.dumps(result) + '\n').encode())
        except Exception as e:
            self.logger.error(f"Handle error: {type(e).__name__} {e}")
            try: conn.sendall((json.dumps({'error': f'Delai depasse ou erreur demon ({type(e).__name__})'}) + '\n').encode())
            except Exception: pass
        finally: conn.close()

    async def _dispatch(self, payload):
        action = payload.get('action', ''); device_id = payload.get('device_id', '')
        try:
            if action == 'get_devices':    return {'devices': self.manager.get_devices_list()}
            elif action == 'get_status':   return await self.manager.get_status(device_id)
            elif action == 'get_maps':     return await self.manager.get_maps(device_id)
            elif action == 'get_rooms':
                try:
                    return {'rooms': await self.manager.get_rooms(device_id, force=True)}
                except DaemonError as e:
                    return {'rooms': [], 'error': str(e)}
            elif action == 'get_routines': return await self.manager.get_routines(device_id)
            else:                          return await self.manager.execute_command(device_id, action, payload)
        except Exception as e:
            self.logger.error(f"Dispatch [{action}]: {e}"); return {'error': str(e)}


async def polling_loop(manager, logger):
    counter = 0
    while True:
        await asyncio.sleep(120)
        counter += 1
        if counter % RECONNECT_EVERY_POLLS == 0:
            await manager.reconnect('periodique')
            await asyncio.sleep(3)
        for device in list(manager.devices):
            if device.v1_properties is None: continue
            try:
                ok = await manager._refresh_status(device)
                if not ok:
                    manager._set_online(device.duid, False)
                if ok and counter % SETTINGS_EVERY_POLLS == 0:
                    await manager._refresh_settings(device)
                if ok and counter % SLOW_EVERY_POLLS == 0:
                    await manager._refresh_slow(device)
                await manager.push_status(device.duid)
            except Exception as e:
                logger.warning(f"Polling {device.duid}: {e}")


async def map_loop(manager, logger):
    await asyncio.sleep(20)
    while True:
        for device in list(manager.devices):
            if device.v1_properties is None or not manager._online.get(device.duid, True):
                continue
            state_int = _int(getattr(device.v1_properties.status, 'state', None), 0)
            await manager.map_tick(device.duid, state_int)
        await asyncio.sleep(30)


async def async_main(args):
    logger = setup_logging(args.loglevel)
    logger.info("=== Demon Roborock Jeedom v2.1 ===")
    os.makedirs(os.path.dirname(args.pid), exist_ok=True)
    with open(args.pid, 'w') as f: f.write(str(os.getpid()))
    callback = JeedomCallback(args.apiurl, args.apikey, logger)
    manager  = RoborockManager(email=args.email, user_data_json=args.userdata,
                                base_url=args.baseurl if args.baseurl else None,
                                callback=callback, logger=logger)
    await manager.initialize()
    loop = asyncio.get_running_loop()
    srv  = SocketServer(args.socketport, manager, logger)
    srv.start(loop)
    await callback.send({'action': 'log', 'level': 'info',
                         'message': f'Demon demarre, {len(manager.devices)} appareil(s)'})
    for d in manager.devices:
        if d.v1_properties is not None:
            manager._set_online(d.duid, True)
            await manager.push_status(d.duid)
    asyncio.ensure_future(map_loop(manager, logger))
    await polling_loop(manager, logger)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--socketport', type=int, default=55666)
    p.add_argument('--apiurl',     required=True)
    p.add_argument('--apikey',     required=True)
    p.add_argument('--pid',        required=True)
    p.add_argument('--loglevel',   default='info')
    p.add_argument('--email',      required=True)
    p.add_argument('--userdata',   required=True)
    p.add_argument('--baseurl',    default='')
    args = p.parse_args()

    def stop(sig, frame):
        logging.getLogger('roborockd').info("Arret")
        if os.path.exists(args.pid): os.remove(args.pid)
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT,  stop)
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        pass
    finally:
        if os.path.exists(args.pid): os.remove(args.pid)

if __name__ == '__main__':
    main()
