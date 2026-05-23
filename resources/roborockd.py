#!/usr/bin/env python3
import sys, os, json, asyncio, argparse, logging, signal, socket, threading, datetime

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

# Monkey-patch: desactive la connexion locale
try:
    from roborock.devices.rpc import v1_channel
    async def _disabled_local_connect(self, *, prefer_cache=True): pass
    async def _disabled_background_reconnect(self): pass
    v1_channel.V1Channel._local_connect = _disabled_local_connect
    v1_channel.V1Channel._background_reconnect = _disabled_background_reconnect
except Exception: pass

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
    100: 'charging', 101: 'offline', 103: 'locked',
    6301: 'mopping', 6302: 'clean_mop_cleaning', 6303: 'clean_mop_mopping',
    6304: 'segment_mopping', 6305: 'segment_clean_mop_cleaning',
    6306: 'segment_clean_mop_mopping', 6307: 'zoned_mopping',
    6308: 'zoned_clean_mop_cleaning', 6309: 'zoned_clean_mop_mopping',
    6310: 'back_to_dock_washing',
}

FAN_MAPPING = {
    101: 'quiet', 102: 'balanced', 103: 'turbo', 104: 'max',
    105: 'off', 106: 'custom', 108: 'max_plus', 110: 'smart_mode',
}
MOP_MAPPING = {
    300: 'standard', 301: 'deep', 302: 'custom',
    303: 'deep_plus', 304: 'fast', 306: 'smart_mode',
}
WATER_MAPPING = {
    200: 'off', 201: 'low', 202: 'medium', 203: 'high', 204: 'custom',
    207: 'custom_water_flow', 209: 'smart_mode', 221: 'slight',
    225: 'low_slide', 235: 'medium_slide', 245: 'moderate',
    248: 'high_slide', 250: 'extreme',
}

FAN_REVERSE   = {v: k for k, v in FAN_MAPPING.items()}
MOP_REVERSE   = {v: k for k, v in MOP_MAPPING.items()}
WATER_REVERSE = {v: k for k, v in WATER_MAPPING.items()}
WATER_REVERSE['low']    = 201
WATER_REVERSE['medium'] = 202
WATER_REVERSE['high']   = 203

CLEANING_STATES = {5, 11, 16, 17, 18, 33, 34, 6301, 6302, 6303, 6304, 6305, 6306, 6307, 6308, 6309}
DOCKED_STATES   = {3, 8, 15, 22, 23, 25, 26, 100}

MAIN_BRUSH_MAX = 1080000; SIDE_BRUSH_MAX = 720000; FILTER_MAX = 540000
SENSOR_MAX = 108000; MOP_ROLLER_MAX = 1080000
STRAINER_MAX = 150; CLEANING_MAX = 300; DUST_COLL_MAX = 90

CLEAR_WATER_LABELS = {0: 'OK', 1: 'Reservoir eau propre vide ou absent', 2: 'OK', 3: 'Reservoir eau propre vide ou absent'}
DIRTY_WATER_LABELS = {0: 'OK', 1: 'Reservoir eau sale plein ou absent', 2: 'OK', 3: 'Reservoir eau sale plein ou absent'}
DUST_BAG_LABELS    = {0: 'OK', 1: 'Bac poussiere absent', 2: 'OK', 3: 'Bac poussiere absent', 34: 'Bac poussiere plein'}
CLEAR_WATER_ERRORS = {1, 3}
DIRTY_WATER_ERRORS = {1, 3}
DUST_BAG_ERRORS    = {1, 3, 34}

def setup_logging(lvl_str):
    lvl = {'debug': logging.DEBUG, 'info': logging.INFO, 'warning': logging.WARNING, 'error': logging.ERROR}.get(lvl_str.lower(), logging.INFO)
    logging.basicConfig(level=lvl, format='[%(asctime)s] %(levelname)-5s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    return logging.getLogger('roborockd')

class JeedomCallback:
    def __init__(self, url, key, logger):
        self.url = url; self.key = key; self.logger = logger

    async def send(self, data):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{self.url}?apikey={self.key}", json=data, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status != 200:
                        self.logger.warning(f"Callback HTTP {r.status}")
        except Exception as e:
            self.logger.error(f"Callback error: {e}")

class RoborockManager:
    def __init__(self, email, user_data_json, base_url, callback, logger):
        self.email          = email
        self.user_data_json = user_data_json
        self.base_url       = base_url
        self.callback       = callback
        self.logger         = logger
        self.device_manager = None
        self.devices        = []
        self.cmd_lock       = None  # initialise dans initialize()
        self._rooms_cache   = {}

    async def initialize(self):
        self.cmd_lock = asyncio.Lock()
        self.logger.info("Connexion au cloud Roborock...")
        user_data   = UserData.from_dict(json.loads(self.user_data_json))
        user_params = UserParams(username=self.email, user_data=user_data, base_url=self.base_url or None)
        try:
            self.device_manager = await create_device_manager(user_params)
        except RoborockInvalidCredentials:
            self.logger.error("Identifiants invalides"); raise
        except RoborockException as e:
            self.logger.error(f"Erreur Roborock: {e}"); raise
        self.devices = await self.device_manager.get_devices()
        self.logger.info(f"{len(self.devices)} appareil(s) trouve(s)")
        for d in self.devices:
            self.logger.info(f"  {d.name} ({d.duid}) proto={self._proto(d)}")
            if d.v1_properties is not None:
                try:
                    await d.v1_properties.start()
                    self.logger.info(f"  Properties demarrees pour {d.duid}")
                    await self._initial_refresh(d)
                except Exception as e:
                    self.logger.warning(f"  start() failed pour {d.duid}: {e}")

    def _proto(self, d):
        if d.v1_properties is not None:          return 'v1'
        if getattr(d, 'dyad', None) is not None: return 'dyad'
        if getattr(d, 'zeo',  None) is not None: return 'zeo'
        return 'unknown'

    def _get(self, device_id):
        for d in self.devices:
            if d.duid == device_id: return d
        return None

    async def _ensure_started(self, d):
        if d.v1_properties is None: return False
        if not getattr(d.v1_properties, '_unsub', None):
            try:
                await asyncio.wait_for(d.v1_properties.start(), timeout=5.0)
                self.logger.info(f"Properties demarrees (retry) pour {d.duid}")
            except Exception as e:
                self.logger.debug(f"start() retry failed pour {d.duid}: {e}")
        return True

    async def _initial_refresh(self, d):
        async def safe_refresh(prop, name):
            try:
                await asyncio.wait_for(prop.refresh(), timeout=8.0)
                self.logger.debug(f"Initial refresh OK: {name}")
            except Exception as e:
                self.logger.debug(f"Initial refresh {name}: {e}")
        props = d.v1_properties
        for name, prop in [
            ('child_lock',   props.child_lock),
            ('led_status',   props.led_status),
            ('dnd',          props.dnd),
            ('sound_volume', props.sound_volume),
            ('consumables',  props.consumables),
        ]:
            if prop: await safe_refresh(prop, name)

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

    async def get_status(self, device_id):
        d = self._get(device_id)
        if not d: return {'error': f'Device {device_id} not found'}
        if d.v1_properties is None: return {'device_id': device_id, 'error': 'not_v1'}
        try:
            await self._ensure_started(d)
            return self._parse(device_id, d.v1_properties)
        except Exception as e:
            self.logger.error(f"get_status {device_id}: {e}")
            return {'device_id': device_id, 'error': str(e)}

    def _parse(self, device_id, props):
        data = {'device_id': device_id}
        try:
            s = props.status
            if s:
                state_val = getattr(s, 'state', None)
                state_int = int(state_val) if state_val is not None else 0
                data['status']  = STATE_NAMES.get(state_int, f'state_{state_int}')
                data['battery'] = int(getattr(s, 'battery', 0) or 0)

                fan_val = getattr(s, 'fan_power', None)
                fan_int = int(fan_val) if fan_val is not None else None
                data['fan_speed'] = FAN_MAPPING.get(fan_int, str(fan_int)) if fan_int is not None else ''

                mop_val = getattr(s, 'mop_mode', None)
                mop_int = int(mop_val) if mop_val is not None else None
                data['mop_mode'] = MOP_MAPPING.get(mop_int, str(mop_int)) if mop_int is not None else ''

                water_val = getattr(s, 'water_box_mode', None)
                water_int = int(water_val) if water_val is not None else None
                data['mop_intensity'] = WATER_MAPPING.get(water_int, str(water_int)) if water_int is not None else ''

                mop_carriage = int(getattr(s, 'water_box_carriage_status', 0) or 0)
                water_box    = int(getattr(s, 'water_box_status', 0) or 0)
                data['mop_attached']       = 1 if (mop_carriage and water_box) else 0
                data['water_box_attached'] = water_box
                data['water_shortage']     = int(getattr(s, 'water_shortage_status', 0) or 0)

                if water_int is None or water_int == 200:
                    data['clean_type'] = 'vacuum'
                elif fan_int == 105:
                    data['clean_type'] = 'mop'
                else:
                    data['clean_type'] = 'vac_and_mop'

                error_val = getattr(s, 'error_code', None)
                if error_val is not None:
                    error_int  = int(error_val)
                    error_name = getattr(error_val, 'name', str(error_int))
                else:
                    error_int = 0; error_name = 'none'
                data['vacuum_error']       = error_int
                data['vacuum_error_label'] = ERROR_CODES.get(error_int, error_name)
                data['vacuum_has_error']   = 1 if error_int != 0 else 0

                dock_err_val = getattr(s, 'dock_error_status', None)
                if dock_err_val is not None:
                    dock_err_int  = int(dock_err_val)
                    dock_err_name = getattr(dock_err_val, 'name', str(dock_err_int))
                else:
                    dock_err_int = 0; dock_err_name = 'ok'
                data['dock_error']       = dock_err_int
                data['dock_error_label'] = DOCK_ERROR_CODES.get(dock_err_int, dock_err_name)
                data['dock_has_error']   = 1 if dock_err_int != 0 else 0

                try:
                    dss = getattr(s, 'dss', None)
                    if dss and int(dss) > 0:
                        dss_int     = int(dss)
                        clear_water = (dss_int >> 2) & 3
                        dirty_water = (dss_int >> 4) & 3
                        dust_bag    = (dss_int >> 6) & 3
                        data['dock_clear_water_status'] = clear_water
                        data['dock_dirty_water_status'] = dirty_water
                        data['dock_dust_bag_status']    = dust_bag
                        robot_is_docked = state_int in DOCKED_STATES
                        robot_is_away   = state_int in CLEANING_STATES or state_int in {6, 15, 16, 10, 29}
                        if dock_err_int == 0 and robot_is_docked and not robot_is_away:
                            dock_errors = []
                            if clear_water in CLEAR_WATER_ERRORS:
                                dock_errors.append(CLEAR_WATER_LABELS.get(clear_water, f'Eau propre {clear_water}'))
                            if dirty_water in DIRTY_WATER_ERRORS:
                                dock_errors.append(DIRTY_WATER_LABELS.get(dirty_water, f'Eau sale {dirty_water}'))
                            if dust_bag in DUST_BAG_ERRORS:
                                dock_errors.append(DUST_BAG_LABELS.get(dust_bag, f'Bac {dust_bag}'))
                            if dock_errors:
                                data['dock_has_error']   = 1
                                data['dock_error_label'] = ', '.join(dock_errors)
                                data['dock_error']       = dss_int
                    else:
                        data['dock_clear_water_status'] = 0
                        data['dock_dirty_water_status'] = 0
                        data['dock_dust_bag_status']    = 0
                except Exception as e:
                    self.logger.debug(f"parse dss: {e}")

                data['is_charging']  = 1 if state_int in [8, 100] else 0
                data['is_cleaning']  = 1 if state_int in CLEANING_STATES else 0
                data['is_paused']    = 1 if state_int == 10 else 0
                data['in_returning'] = int(getattr(s, 'in_returning', 0) or 0)
                data['charge_status']   = int(getattr(s, 'charge_status', 0) or 0)
                data['dry_status']      = int(getattr(s, 'dry_status', 0) or 0)
                data['wash_status']     = int(getattr(s, 'wash_status', 0) or 0)
                data['dust_collection'] = int(getattr(s, 'dust_collection_status', 0) or 0)

                area = getattr(s, 'clean_area', 0) or 0
                data['cleaning_area']     = round(int(area) / 1000000, 2)
                t = getattr(s, 'clean_time', 0) or 0
                data['cleaning_time']     = round(int(t) / 60, 1)
                pct = getattr(s, 'clean_percent', None)
                data['cleaning_progress'] = int(pct) if pct is not None else 0
                dnd_val = getattr(s, 'dnd_enabled', None)
                data['do_not_disturb']    = int(dnd_val) if dnd_val is not None else 0

                # Calculer last_clean_begin = last_clean_t - clean_time
                try:
                    last_t = getattr(s, 'last_clean_t', None)
                    clean_time_s = int(getattr(s, 'clean_time', 0) or 0)
                    if last_t and int(last_t) > 0:
                        data['last_clean_end'] = str(datetime.datetime.fromtimestamp(int(last_t)))
                        if clean_time_s > 0:
                            data['last_clean_begin'] = str(datetime.datetime.fromtimestamp(int(last_t) - clean_time_s))
                except: pass

        except Exception as e:
            self.logger.warning(f"parse status: {e}")

        try:
            c = props.consumables
            if c:
                def h(v): return round(int(v or 0) / 3600, 1)
                def left_h(w, m): return round(max(0, (m - int(w or 0)) / 3600), 1)
                def pct_h(w, m): return round(max(0, 100 - (int(w or 0) / m * 100)), 1) if m > 0 else 0
                def pct_n(w, m): return round(max(0, 100 - (int(w or 0) / m * 100)), 1) if m > 0 else 0
                mbt  = getattr(c, 'main_brush_work_time', 0) or 0
                sbt  = getattr(c, 'side_brush_work_time', 0) or 0
                ft   = getattr(c, 'filter_work_time', 0) or 0
                sdt  = getattr(c, 'sensor_dirty_time', 0) or 0
                mrt  = getattr(c, 'moproller_work_time', 0) or 0
                str_ = getattr(c, 'strainer_work_times', 0) or 0
                dct  = getattr(c, 'dust_collection_work_times', 0) or 0
                cbt  = getattr(c, 'cleaning_brush_work_times', 0) or 0
                data['main_brush_work_time']       = h(mbt)
                data['side_brush_work_time']       = h(sbt)
                data['filter_work_time']           = h(ft)
                data['sensor_dirty_time']          = h(sdt)
                data['moproller_work_time']        = h(mrt)
                data['strainer_work_times']        = int(str_)
                data['dust_collection_work_times'] = int(dct)
                data['cleaning_brush_work_times']  = int(cbt)
                data['main_brush_time_left']       = left_h(mbt, MAIN_BRUSH_MAX)
                data['side_brush_time_left']       = left_h(sbt, SIDE_BRUSH_MAX)
                data['filter_time_left']           = left_h(ft,  FILTER_MAX)
                data['sensor_time_left']           = left_h(sdt, SENSOR_MAX)
                data['moproller_time_left']        = left_h(mrt, MOP_ROLLER_MAX)
                data['main_brush_pct']             = pct_h(mbt, MAIN_BRUSH_MAX)
                data['side_brush_pct']             = pct_h(sbt, SIDE_BRUSH_MAX)
                data['filter_pct']                 = pct_h(ft,  FILTER_MAX)
                data['sensor_pct']                 = pct_h(sdt, SENSOR_MAX)
                data['moproller_pct']              = pct_h(mrt, MOP_ROLLER_MAX)
                data['strainer_pct']               = pct_n(str_, STRAINER_MAX)
                data['dust_coll_pct']              = pct_n(dct,  DUST_COLL_MAX)
                data['cleaning_pct']               = pct_n(cbt,  CLEANING_MAX)
        except Exception as e:
            self.logger.warning(f"parse consumables: {e}")

        try:
            dnd = props.dnd
            if dnd:
                data['do_not_disturb']       = 1 if getattr(dnd, 'enabled', False) else 0
                sh = int(getattr(dnd, 'start_hour',   0) or 0)
                sm = int(getattr(dnd, 'start_minute', 0) or 0)
                eh = int(getattr(dnd, 'end_hour',     0) or 0)
                em = int(getattr(dnd, 'end_minute',   0) or 0)
                data['do_not_disturb_begin'] = f"{sh:02d}:{sm:02d}"
                data['do_not_disturb_end']   = f"{eh:02d}:{em:02d}"
        except Exception as e:
            self.logger.warning(f"parse dnd: {e}")

        try:
            sv = props.sound_volume
            if sv: data['volume'] = int(getattr(sv, 'volume', 0) or 0)
        except Exception as e:
            self.logger.warning(f"parse sound_volume: {e}")

        try:
            cl = props.child_lock
            if cl: data['child_lock'] = int(getattr(cl, 'lock_status', 0) or 0)
        except Exception as e:
            self.logger.warning(f"parse child_lock: {e}")

        try:
            led = props.led_status
            if led: data['led_status'] = int(getattr(led, 'status', 0) or 0)
        except Exception as e:
            self.logger.warning(f"parse led_status: {e}")

        return data

    async def get_routines(self, device_id):
        d = self._get(device_id)
        if not d or d.v1_properties is None: return {'routines': []}
        try:
            routines = await d.v1_properties.routines.get_routines()
            return {'routines': [{'id': r.id, 'name': getattr(r, 'name', None) or f'Routine {r.id}'} for r in routines]}
        except Exception as e:
            self.logger.error(f"get_routines {device_id}: {e}")
            return {'routines': [], 'error': str(e)}

    async def get_maps(self, device_id):
        d = self._get(device_id)
        if not d or d.v1_properties is None: return {'maps': []}
        cache_key = f'rooms_{device_id}'
        if cache_key in self._rooms_cache:
            return self._rooms_cache[cache_key]
        try:
            cmd = d.v1_properties.command
            room_mapping = await cmd.send(RoborockCommand.GET_ROOM_MAPPING)
            self.logger.debug(f"GET_ROOM_MAPPING: {room_mapping}")
            rooms_dict = {}
            if room_mapping:
                for item in room_mapping:
                    if isinstance(item, (list, tuple)) and len(item) >= 1:
                        rooms_dict[str(item[0])] = f'Piece {item[0]}'
            out = []
            if rooms_dict:
                out.append({'flag': 0, 'name': 'Carte principale', 'rooms': rooms_dict})
            result = {'maps': out}
            self._rooms_cache[cache_key] = result
            return result
        except Exception as e:
            self.logger.error(f"get_maps {device_id}: {e}")
            return {'maps': [], 'error': str(e)}

    async def execute_command(self, device_id, action, params):
        d = self._get(device_id)
        if not d:
            return {'error': f'Device {device_id} not found'}
        if d.v1_properties is None:
            return {'error': 'not_v1'}
        cmd = d.v1_properties.command
        try:
            simple = {
                'start':               RoborockCommand.APP_START,
                'pause':               RoborockCommand.APP_PAUSE,
                'stop':                RoborockCommand.APP_STOP,
                'dock':                RoborockCommand.APP_CHARGE,
                'locate':              RoborockCommand.FIND_ME,
                'spot_clean':          RoborockCommand.APP_SPOT,
                'start_dust_collection': RoborockCommand.APP_START_COLLECT_DUST,
                'stop_dust_collection':  RoborockCommand.APP_STOP_COLLECT_DUST,
                'start_wash':          RoborockCommand.APP_START_WASH,
                'stop_wash':           RoborockCommand.APP_STOP_WASH,
            }
            if action == 'resume':
                # Reprendre selon le contexte : segment si in_cleaning=3, sinon APP_START
                s = d.v1_properties.status
                in_cleaning = int(getattr(s, 'in_cleaning', 0) or 0) if s else 0
                if in_cleaning == 3:
                    await cmd.send(RoborockCommand.RESUME_SEGMENT_CLEAN)
                else:
                    await cmd.send(RoborockCommand.APP_START)
            elif action in simple:
                await cmd.send(simple[action])
            elif action == 'set_fan_speed':
                val = params.get('value', 'balanced')
                await cmd.send(RoborockCommand.SET_CUSTOM_MODE, [FAN_REVERSE.get(val, int(val) if str(val).isdigit() else 102)])
            elif action == 'set_mop_intensity':
                val = params.get('value', 'moderate')
                await cmd.send(RoborockCommand.SET_WATER_BOX_CUSTOM_MODE, [WATER_REVERSE.get(val, int(val) if str(val).isdigit() else 245)])
            elif action == 'set_mop_mode':
                val = params.get('value', 'standard')
                await cmd.send(RoborockCommand.SET_MOP_MODE, [MOP_REVERSE.get(val, int(val) if str(val).isdigit() else 300)])
            elif action == 'set_clean_type':
                val = params.get('value', 'vac_and_mop')
                if val == 'vacuum':
                    await cmd.send(RoborockCommand.SET_CUSTOM_MODE, [102])
                    await asyncio.sleep(2)
                    await cmd.send(RoborockCommand.SET_WATER_BOX_CUSTOM_MODE, [200])
                elif val == 'mop':
                    await cmd.send(RoborockCommand.SET_WATER_BOX_CUSTOM_MODE, [245])
                    await asyncio.sleep(2)
                    await cmd.send(RoborockCommand.SET_CUSTOM_MODE, [105])
                else:
                    await cmd.send(RoborockCommand.SET_CUSTOM_MODE, [102])
                    await asyncio.sleep(1)
                    await cmd.send(RoborockCommand.SET_WATER_BOX_CUSTOM_MODE, [245])
            elif action == 'set_volume':
                await cmd.send(RoborockCommand.CHANGE_SOUND_VOLUME, [int(params.get('value', 50))])
            elif action == 'child_lock_on':
                cl = d.v1_properties.child_lock
                await cl.enable() if cl else await cmd.send(RoborockCommand.SET_CHILD_LOCK_STATUS, {'lock_status': 1})
            elif action == 'child_lock_off':
                cl = d.v1_properties.child_lock
                await cl.disable() if cl else await cmd.send(RoborockCommand.SET_CHILD_LOCK_STATUS, {'lock_status': 0})
            elif action == 'led_on':
                led = d.v1_properties.led_status
                await led.enable() if led else await cmd.send(RoborockCommand.SET_LED_STATUS, [1])
            elif action == 'led_off':
                led = d.v1_properties.led_status
                await led.disable() if led else await cmd.send(RoborockCommand.SET_LED_STATUS, [0])
            elif action == 'dnd_on':
                dnd = d.v1_properties.dnd
                await dnd.enable() if dnd else await cmd.send(RoborockCommand.SET_DND_TIMER, {'start_hour':22,'start_minute':0,'end_hour':8,'end_minute':0,'enabled':1})
            elif action == 'dnd_off':
                dnd = d.v1_properties.dnd
                await dnd.disable() if dnd else await cmd.send(RoborockCommand.CLOSE_DND_TIMER)
            elif action == 'reset_main_brush':
                await cmd.send(RoborockCommand.RESET_CONSUMABLE, ['main_brush_work_time'])
            elif action == 'reset_side_brush':
                await cmd.send(RoborockCommand.RESET_CONSUMABLE, ['side_brush_work_time'])
            elif action == 'reset_filter':
                await cmd.send(RoborockCommand.RESET_CONSUMABLE, ['filter_work_time'])
            elif action == 'reset_sensor':
                await cmd.send(RoborockCommand.RESET_CONSUMABLE, ['sensor_dirty_time'])
            elif action == 'reset_moproller':
                await cmd.send(RoborockCommand.RESET_CONSUMABLE, ['moproller_work_time'])
            elif action == 'reset_strainer':
                await cmd.send(RoborockCommand.RESET_CONSUMABLE, ['strainer_work_times'])
            elif action == 'reset_dust_collection':
                await cmd.send(RoborockCommand.RESET_CONSUMABLE, ['dust_collection_work_times'])
            elif action == 'clean_segment':
                segments = params.get('segments', [])
                repeat   = int(params.get('repeat', 1))
                self.logger.info(f"clean_segment: segments={segments} repeat={repeat}")
                await cmd.send(RoborockCommand.APP_SEGMENT_CLEAN, [{'segments': segments, 'repeat': repeat}])
            elif action == 'clean_zone':
                await cmd.send(RoborockCommand.APP_ZONED_CLEAN, [{'repeats': int(params.get('repeat', 1)), 'zones': params.get('zones', [])}])
            elif action == 'goto_position':
                await cmd.send(RoborockCommand.APP_GOTO_TARGET, [params.get('x', 25500), params.get('y', 25500)])
            elif action == 'start_dry':
                await cmd.send(RoborockCommand.APP_SET_DRYER_STATUS, {'status': 1})
            elif action == 'stop_dry':
                await cmd.send(RoborockCommand.APP_SET_DRYER_STATUS, {'status': 0})
            elif action == 'execute_routine':
                await d.v1_properties.routines.execute_routine(int(params.get('routine_id', 0)))
            else:
                return {'error': f'Unknown action: {action}'}
            return {'success': True}
        except Exception as e:
            self.logger.error(f"cmd {action}: {e}")
            return {'error': str(e)}

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
            buf = b''
            while True:
                chunk = conn.recv(4096)
                if not chunk: break
                buf += chunk
                if b'\n' in buf: break
            if not buf: conn.close(); return
            payload = json.loads(buf.decode().strip())
            future  = asyncio.run_coroutine_threadsafe(self._dispatch(payload), self.loop)
            result  = future.result(timeout=30)
            conn.sendall((json.dumps(result) + '\n').encode())
        except Exception as e:
            self.logger.error(f"Handle error: {e}")
            try: conn.sendall((json.dumps({'error': str(e)}) + '\n').encode())
            except: pass
        finally: conn.close()

    async def _dispatch(self, payload):
        action = payload.get('action', ''); device_id = payload.get('device_id', '')
        try:
            if action == 'get_devices':    return {'devices': self.manager.get_devices_list()}
            elif action == 'get_status':   return await self.manager.get_status(device_id)
            elif action == 'get_maps':     return await self.manager.get_maps(device_id)
            elif action == 'get_routines': return await self.manager.get_routines(device_id)
            else:                          return await self.manager.execute_command(device_id, action, payload)
        except Exception as e:
            self.logger.error(f"Dispatch [{action}]: {e}"); return {'error': str(e)}

async def polling_loop(manager, callback, logger):
    slow_counter = 0
    while True:
        await asyncio.sleep(30)
        slow_counter += 1
        do_slow_refresh = (slow_counter % 10 == 0)
        for device in manager.devices:
            if device.v1_properties is None: continue
            try:
                try:
                    await asyncio.wait_for(device.v1_properties.status.refresh(), timeout=5.0)
                except Exception as e:
                    logger.debug(f"Polling status refresh: {e}")
                if do_slow_refresh:
                    await manager._initial_refresh(device)
                status = await manager.get_status(device.duid)
                status['action'] = 'update'
                await callback.send(status)
            except Exception as e:
                logger.warning(f"Polling {device.duid}: {e}")

async def async_main(args):
    logger = setup_logging(args.loglevel)
    logger.info("=== Demon Roborock Jeedom ===")
    os.makedirs(os.path.dirname(args.pid), exist_ok=True)
    with open(args.pid, 'w') as f: f.write(str(os.getpid()))
    callback = JeedomCallback(args.apiurl, args.apikey, logger)
    manager  = RoborockManager(email=args.email, user_data_json=args.userdata,
                                base_url=args.baseurl if args.baseurl else None,
                                callback=callback, logger=logger)
    await manager.initialize()
    loop = asyncio.get_event_loop()
    srv  = SocketServer(args.socketport, manager, logger)
    srv.start(loop)
    await callback.send({'action': 'log', 'level': 'info',
                         'message': f'Demon demarre, {len(manager.devices)} appareil(s)'})
    await polling_loop(manager, callback, logger)

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