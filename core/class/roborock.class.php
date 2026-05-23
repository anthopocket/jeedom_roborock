<?php
require_once __DIR__ . '/../../../../core/php/core.inc.php';

class roborock extends eqLogic {

    const DAEMON_SOCKET_PORT = 55666;

    public static function dependancy_info() {
        $return = [];
        $return['log']           = log::getPathToLog(__CLASS__ . '_dependance');
        $return['progress_file'] = jeedom::getTmpFolder(__CLASS__) . '/dependance';
        if (file_exists($return['progress_file'])) {
            $return['state'] = 'in_progress';
            return $return;
        }
        $venvPython = __DIR__ . '/../../resources/venv/bin/python3';
        if (!file_exists($venvPython)) {
            $return['state'] = 'nok';
            return $return;
        }
        exec($venvPython . ' -c "import roborock; import aiohttp" 2>&1', $out, $rc);
        $return['state'] = ($rc === 0) ? 'ok' : 'nok';
        return $return;
    }

    public static function dependancy_install() {
        log::remove(__CLASS__ . '_dependance');
        return [
            'script' => __DIR__ . '/../../resources/install_apt.sh ' . jeedom::getTmpFolder(__CLASS__) . '/dependance',
            'log'    => log::getPathToLog(__CLASS__ . '_dependance'),
        ];
    }

    public static function deamon_info() {
        $return = ['log' => __CLASS__, 'state' => 'nok', 'launchable' => 'ok'];
        $pid_file = jeedom::getTmpFolder(__CLASS__) . '/daemon.pid';
        if (file_exists($pid_file)) {
            $pid = trim(file_get_contents($pid_file));
            if (is_numeric($pid) && posix_kill(intval($pid), 0)) {
                $return['state'] = 'ok';
            } else {
                unlink($pid_file);
            }
        }
        $userData = config::byKey('roborock_user_data', __CLASS__);
        if (empty($userData)) {
            $return['launchable']         = 'nok';
            $return['launchable_message'] = __('Authentification requise', __FILE__);
        }
        return $return;
    }

    public static function deamon_start($_automatic = false) {
        self::deamon_stop();
        $deamon_info = self::deamon_info();
        if ($deamon_info['launchable'] != 'ok') {
            throw new Exception(__('Authentifiez-vous dans la configuration du plugin', __FILE__));
        }
        $path    = __DIR__ . '/../../resources';
        $python3 = $path . '/venv/bin/python3';
        $script  = $path . '/roborockd.py';
        if (!file_exists($python3)) throw new Exception('Python venv introuvable: ' . $python3);
        if (!file_exists($script))  throw new Exception('Script demon introuvable: ' . $script);

        $pid_file    = jeedom::getTmpFolder(__CLASS__) . '/daemon.pid';
        $apiUrl      = network::getNetworkAccess('internal', 'proto:127.0.0.1:port:comp') . '/plugins/roborock/core/php/jeeRoborock.php';
        $callbackKey = jeedom::getApiKey(__CLASS__);
        $logLevel    = log::convertLogLevel(log::getLogLevel(__CLASS__));
        $userData    = config::byKey('roborock_user_data', __CLASS__);
        if (is_array($userData)) $userData = json_encode($userData);
        $userData = strval($userData);
        $email    = config::byKey('roborock_email',  __CLASS__);
        $baseUrl  = config::byKey('roborock_region', __CLASS__, '');

        $cmd  = $python3 . ' ' . $script;
        $cmd .= ' --socketport ' . self::DAEMON_SOCKET_PORT;
        $cmd .= ' --apiurl '     . escapeshellarg($apiUrl);
        $cmd .= ' --apikey '     . $callbackKey;
        $cmd .= ' --pid '        . $pid_file;
        $cmd .= ' --loglevel '   . $logLevel;
        $cmd .= ' --email '      . escapeshellarg($email);
        $cmd .= ' --userdata '   . escapeshellarg($userData);
        if (!empty($baseUrl)) $cmd .= ' --baseurl ' . escapeshellarg($baseUrl);

        log::add(__CLASS__, 'info', 'Demarrage demon: ' . $cmd);
        exec($cmd . ' >> ' . log::getPathToLog(__CLASS__) . ' 2>&1 &');

        $i = 0;
        while ($i++ < 30) {
            sleep(1);
            if (self::deamon_info()['state'] == 'ok') {
                log::add(__CLASS__, 'info', 'Demon demarre');
                return;
            }
        }
        throw new Exception(__('Impossible de demarrer le demon (timeout 30s)', __FILE__));
    }

    public static function deamon_stop() {
        $pid_file = jeedom::getTmpFolder(__CLASS__) . '/daemon.pid';
        if (file_exists($pid_file)) {
            $pid = trim(file_get_contents($pid_file));
            if (is_numeric($pid)) { exec('kill -TERM ' . intval($pid) . ' 2>&1'); usleep(500000); }
            unlink($pid_file);
        }
        exec("pkill -f 'roborockd.py' 2>&1");
    }

    public static function synchronize() {
        log::add(__CLASS__, 'info', 'Synchronisation...');
        $response = self::sendToDaemon(['action' => 'get_devices']);
        if (empty($response['devices'])) throw new Exception('Aucun appareil retourne.');
        $count = 0;
        foreach ($response['devices'] as $device) {
            $deviceId = $device['device_id'];
            $eqLogic  = self::byLogicalId($deviceId, __CLASS__);
            if (!is_object($eqLogic)) {
                $eqLogic = new self();
                $eqLogic->setLogicalId($deviceId);
                $eqLogic->setEqType_name(__CLASS__);
                $eqLogic->setIsEnable(1);
                $eqLogic->setIsVisible(1);
            }
            $eqLogic->setName($device['name']);
            $eqLogic->setConfiguration('device_id', $deviceId);
            $eqLogic->setConfiguration('model',    $device['model']    ?? '');
            $eqLogic->setConfiguration('ip',       $device['ip']       ?? '');
            $eqLogic->setConfiguration('firmware', $device['firmware'] ?? '');
            $eqLogic->setConfiguration('serial',   $device['serial']   ?? '');
            $eqLogic->setConfiguration('protocol', $device['protocol'] ?? 'v1');
            $eqLogic->save();
            $eqLogic->createCommands();
            $count++;
        }
        log::add(__CLASS__, 'info', $count . ' appareil(s) synchronise(s)');
        return $count;
    }

    public static function callbackFromDaemon($_data) {
        if (empty($_data['device_id'])) return;
        $eq = self::byLogicalId($_data['device_id'], __CLASS__);
        if (!is_object($eq)) return;
        $eq->updateFromData($_data);
    }

    public function updateFromData($_data) {
        $fields = [
            'status', 'battery', 'fan_speed', 'mop_mode', 'mop_intensity', 'clean_type',
            'vacuum_error', 'vacuum_error_label', 'vacuum_has_error',
            'dock_error', 'dock_error_label', 'dock_has_error',
            'is_charging', 'is_cleaning', 'is_paused', 'in_returning',
            'mop_attached', 'water_box_attached', 'water_shortage',
            'child_lock', 'led_status', 'do_not_disturb',
            'do_not_disturb_begin', 'do_not_disturb_end',
            'cleaning_area', 'cleaning_time', 'cleaning_progress',
            'last_clean_begin', 'last_clean_end',
            'main_brush_work_time', 'side_brush_work_time', 'filter_work_time',
            'sensor_dirty_time', 'moproller_work_time',
            'strainer_work_times', 'dust_collection_work_times', 'cleaning_brush_work_times',
            'main_brush_time_left', 'side_brush_time_left', 'filter_time_left',
            'sensor_time_left', 'moproller_time_left',
            'main_brush_pct', 'side_brush_pct', 'filter_pct', 'sensor_pct',
            'moproller_pct', 'strainer_pct', 'dust_coll_pct', 'cleaning_pct',
            'charge_status', 'dry_status', 'wash_status', 'dust_collection',
            'volume', 'map_image','dock_clear_water_status', 'dock_dirty_water_status', 'dock_dust_bag_status',
        ];
        foreach ($fields as $f) {
            if (!array_key_exists($f, $_data)) continue;
            $cmd = $this->getCmd('info', $f);
            if (is_object($cmd)) $cmd->event($_data[$f]);
        }
    }

    public function createCommands() {
        $defs = [
            // === ACTIONS VACUUM ===
            ['Demarrer',               'start',                  'action', 'other',   1],
            ['Pause',                  'pause',                  'action', 'other',   2],
            ['Reprendre',              'resume',                 'action', 'other',   3],
            ['Arreter',                'stop',                   'action', 'other',   4],
            ['Rentrer base',           'dock',                   'action', 'other',   5],
            ['Localiser',              'locate',                 'action', 'other',   6],
            ['Nettoyage ponctuel',     'spot_clean',             'action', 'other',   7],
            ['Synchroniser',           'sync',                   'action', 'other',   8],

            // === ACTIONS PARAMETRES ===
            ['Regler vitesse ventil',  'set_fan_speed',          'action', 'select',  10,
                'listValue' => 'quiet|Silencieux;balanced|Equilibre;turbo|Turbo;max|Maximum;off|Arret;max_plus|Maximum+;smart_mode|Auto', 'value' => 'fan_speed'],
            ['Regler intensite mop', 'set_mop_intensity', 'action', 'select', 11,
    'listValue' => 'off|Arret;slight|Tres faible;low|Faible;medium_slide|Moyen slide;moderate|Modere;high_slide|Eleve slide;extreme|Extreme;smart_mode|Auto', 'value' => 'mop_intensity'],
            ['Regler mode mop',        'set_mop_mode',           'action', 'select',  12,
                'listValue' => 'standard|Standard;deep|Profond;deep_plus|Profond+;fast|Rapide;smart_mode|Auto', 'value' => 'mop_mode'],
            ['Regler volume',          'set_volume',             'action', 'slider',  13,
                'minValue' => 0, 'maxValue' => 100],
            ['Type nettoyage',         'set_clean_type',         'action', 'select',  14,
                'listValue' => 'vacuum|Aspiration seule;vac_and_mop|Aspiration et lavage;mop|Lavage seul', 'value' => 'clean_type'],

            // === ACTIONS SWITCHES ===
            ['Verr. enfant On',        'child_lock_on',          'action', 'other',   20],
            ['Verr. enfant Off',       'child_lock_off',         'action', 'other',   21],
            ['LED On',                 'led_on',                 'action', 'other',   22],
            ['LED Off',                'led_off',                'action', 'other',   23],
            ['NDD On',                 'dnd_on',                 'action', 'other',   24],
            ['NDD Off',                'dnd_off',                'action', 'other',   25],

          // === DOCK DSS ===
['Eau propre dock',        'dock_clear_water_status', 'info', 'numeric', 94],
['Eau sale dock',          'dock_dirty_water_status', 'info', 'numeric', 95],
['Bac poussiere dock',     'dock_dust_bag_status',    'info', 'numeric', 96],
          
            // === ACTIONS DOCK ===
            ['Vider le bac',           'start_dust_collection',  'action', 'other',   26],
            ['Arreter vidage bac',     'stop_dust_collection',   'action', 'other',   27],
            ['Laver serpilliere',      'start_wash',             'action', 'other',   28],
            ['Arreter lavage',         'stop_wash',              'action', 'other',   29],
            ['Demarrer sechage',       'start_dry',              'action', 'other',   30],
            ['Arreter sechage',        'stop_dry',               'action', 'other',   31],

            // === RESET CONSOMMABLES ===
            ['Reset brosse princ.',    'reset_main_brush',       'action', 'other',   40],
            ['Reset brosse lat.',      'reset_side_brush',       'action', 'other',   41],
            ['Reset filtre',           'reset_filter',           'action', 'other',   42],
            ['Reset capteurs',         'reset_sensor',           'action', 'other',   43],
            ['Reset rouleau mop',      'reset_moproller',        'action', 'other',   44],
            ['Reset filtre eau',       'reset_strainer',         'action', 'other',   45],
            ['Reset coll. poussiere',  'reset_dust_collection',  'action', 'other',   46],

            // === NETTOYAGE AVANCE ===

            // === STATUT ===
            ['Statut',                 'status',                 'info', 'string',   50, 'generic_type' => 'VACUUM_STATE'],
            ['Batterie',               'battery',                'info', 'numeric',  51, 'generic_type' => 'BATTERY', 'unite' => '%'],
            ['En charge',              'is_charging',            'info', 'binary',   52],
            ['En nettoyage',           'is_cleaning',            'info', 'binary',   53],
            ['En retour base',         'in_returning',           'info', 'binary',   54],
            ['En pause',               'is_paused',              'info', 'binary',   55],
            ['Type nettoyage (val)',    'clean_type',             'info', 'string',   56],

            // === ALERTES ERREURS ===
            ['Erreur aspirateur (code)',  'vacuum_error',        'info', 'numeric',  57],
            ['Erreur aspirateur (label)', 'vacuum_error_label',  'info', 'string',   58],
            ['Aspirateur en erreur',      'vacuum_has_error',    'info', 'binary',   59],
            ['Erreur dock (code)',         'dock_error',         'info', 'numeric',  60],
            ['Erreur dock (label)',        'dock_error_label',   'info', 'string',   61],
            ['Dock en erreur',             'dock_has_error',     'info', 'binary',   62],

            // === NETTOYAGE ===
            ['Surface nettoyee',       'cleaning_area',          'info', 'numeric',  63, 'unite' => 'm2'],
            ['Duree nettoyage',        'cleaning_time',          'info', 'numeric',  64, 'unite' => 'min'],
            ['Progression',            'cleaning_progress',      'info', 'numeric',  65, 'unite' => '%'],
            ['Dernier debut',          'last_clean_begin',       'info', 'string',   69],
            ['Derniere fin',           'last_clean_end',         'info', 'string',   70],

            // === PARAMETRES ===
            ['Vitesse ventil.',        'fan_speed',              'info', 'string',   71],
            ['Intensite mop',          'mop_intensity',          'info', 'string',   72],
            ['Mode mop',               'mop_mode',               'info', 'string',   73],
            ['Volume',                 'volume',                 'info', 'numeric',  74, 'unite' => '%'],

            // === CAPTEURS ===
            ['Serpilliere attachee',   'mop_attached',           'info', 'binary',   80],
            ['Reservoir eau attache',  'water_box_attached',     'info', 'binary',   81],
            ['Manque eau',             'water_shortage',         'info', 'binary',   82],
            ['Verr. enfant',           'child_lock',             'info', 'binary',   83],
            ['LED',                    'led_status',             'info', 'binary',   84],
            ['Ne pas deranger',        'do_not_disturb',         'info', 'binary',   85],
            ['NDD debut',              'do_not_disturb_begin',   'info', 'string',   86],
            ['NDD fin',                'do_not_disturb_end',     'info', 'string',   87],

            // === DOCK ===
            ['Statut charge',          'charge_status',          'info', 'numeric',  90],
            ['Statut sechage',         'dry_status',             'info', 'numeric',  91],
            ['Statut lavage',          'wash_status',            'info', 'numeric',  92],
            ['Collecte poussiere',     'dust_collection',        'info', 'numeric',  93],

            // === CONSOMMABLES (heures utilisees) ===
            ['Brosse princ. (h util)', 'main_brush_work_time',   'info', 'numeric', 100, 'unite' => 'h'],
            ['Brosse lat. (h util)',   'side_brush_work_time',   'info', 'numeric', 101, 'unite' => 'h'],
            ['Filtre (h util)',        'filter_work_time',       'info', 'numeric', 102, 'unite' => 'h'],
            ['Capteurs (h util)',      'sensor_dirty_time',      'info', 'numeric', 103, 'unite' => 'h'],
            ['Rouleau mop (h util)',   'moproller_work_time',    'info', 'numeric', 104, 'unite' => 'h'],
            ['Filtre eau (util)',      'strainer_work_times',    'info', 'numeric', 105],
            ['Coll. poussi. (util)',   'dust_collection_work_times', 'info', 'numeric', 106],
            ['Brosse nett. (util)',    'cleaning_brush_work_times',  'info', 'numeric', 107],

            // === CONSOMMABLES (heures restantes) ===
            ['Brosse princ. (h rest)', 'main_brush_time_left',   'info', 'numeric', 110, 'unite' => 'h'],
            ['Brosse lat. (h rest)',   'side_brush_time_left',   'info', 'numeric', 111, 'unite' => 'h'],
            ['Filtre (h rest)',        'filter_time_left',       'info', 'numeric', 112, 'unite' => 'h'],
            ['Capteurs (h rest)',      'sensor_time_left',       'info', 'numeric', 113, 'unite' => 'h'],
            ['Rouleau mop (h rest)',   'moproller_time_left',    'info', 'numeric', 114, 'unite' => 'h'],

            // === CONSOMMABLES (% restant) ===
            ['Brosse princ. (%)',      'main_brush_pct',         'info', 'numeric', 115, 'unite' => '%'],
            ['Brosse lat. (%)',        'side_brush_pct',         'info', 'numeric', 116, 'unite' => '%'],
            ['Filtre (%)',             'filter_pct',             'info', 'numeric', 117, 'unite' => '%'],
            ['Capteurs (%)',           'sensor_pct',             'info', 'numeric', 118, 'unite' => '%'],
            ['Rouleau mop (%)',        'moproller_pct',          'info', 'numeric', 119, 'unite' => '%'],
            ['Filtre eau (%)',         'strainer_pct',           'info', 'numeric', 120, 'unite' => '%'],
            ['Coll. poussiere (%)',    'dust_coll_pct',          'info', 'numeric', 121, 'unite' => '%'],
            ['Brosse nettoyage (%)',   'cleaning_pct',           'info', 'numeric', 122, 'unite' => '%'],
        ];

        foreach ($defs as $d) {
            $cmd = $this->getCmd($d[2], $d[1]);
            if (!is_object($cmd)) {
                $cmd = new roborockCmd();
                $cmd->setLogicalId($d[1]);
                $cmd->setEqLogic_id($this->getId());
            }
            $cmd->setName($d[0]);
            $cmd->setType($d[2]);
            $cmd->setSubType($d[3]);
          $cmd->setOrder($d[4]);
            if (!empty($d['generic_type'])) $cmd->setGeneric_type($d['generic_type']);
            if (!empty($d['unite']))        $cmd->setUnite($d['unite']);
            if (!empty($d['listValue']))    $cmd->setConfiguration('listValue', $d['listValue']);
            if (isset($d['minValue']))      $cmd->setConfiguration('minValue', $d['minValue']);
            if (isset($d['maxValue']))      $cmd->setConfiguration('maxValue', $d['maxValue']);
            if (!$cmd->getId())             $cmd->setIsVisible(1);
            $cmd->save();
        }
        // Lier les commandes action aux infos correspondantes
        $valueMap = [
            'set_fan_speed'     => 'fan_speed',
            'set_mop_intensity' => 'mop_intensity',
            'set_mop_mode'      => 'mop_mode',
            'set_clean_type'    => 'clean_type',
        ];
        foreach ($valueMap as $actionId => $infoId) {
            $cmdAction = $this->getCmd('action', $actionId);
            $cmdInfo   = $this->getCmd('info',   $infoId);
            if (is_object($cmdAction) && is_object($cmdInfo)) {
                $cmdAction->setValue($cmdInfo->getId());
                $cmdAction->save();
            }
        }
    }

    public function executeAction($_cmd, $_options = []) {
        $deviceId = $this->getConfiguration('device_id');
        $lid      = $_cmd->getLogicalId();
        $p        = ['action' => $lid, 'device_id' => $deviceId];

        if (strpos($lid, 'routine_') === 0) {
            $routineId       = $_cmd->getConfiguration('routine_id');
            $p['action']     = 'execute_routine';
            $p['routine_id'] = intval($routineId);
            self::sendToDaemon($p);
            return;
        }
        if (strpos($lid, 'room_') === 0) {
            $segmentId   = $_cmd->getConfiguration('segment_id');
            $p['action']   = 'clean_segment';
            $p['segments'] = [intval($segmentId)];
            $p['repeat']   = 1;
            self::sendToDaemon($p);
            return;
        }

        switch ($lid) {
            case 'set_fan_speed':
            case 'set_mop_intensity':
            case 'set_mop_mode':
            case 'set_clean_type':
                $p['value'] = $_options['select'] ?? '';
                break;
            case 'set_volume':
                $p['value'] = intval($_options['slider'] ?? 50);
                break;
            case 'clean_segment':
                $p['segments'] = array_map('intval', explode(',', trim($_options['message'] ?? '')));
                $p['repeat']   = 1;
                break;
            case 'clean_zone':
                $p['zones']  = $_options['message'] ?? '';
                $p['repeat'] = 1;
                break;
            case 'goto_position':
                $pts    = explode(',', $_options['message'] ?? '25500,25500');
                $p['x'] = intval($pts[0] ?? 25500);
                $p['y'] = intval($pts[1] ?? 25500);
                break;
            case 'sync':
                self::synchronize();
                return;
        }
        self::sendToDaemon($p);
    }

    public static function sendToDaemon($_data) {
        $port = self::DAEMON_SOCKET_PORT;
        $sock = @socket_create(AF_INET, SOCK_STREAM, SOL_TCP);
        if ($sock === false) throw new Exception('socket_create failed');
        if (!@socket_connect($sock, '127.0.0.1', $port)) {
            socket_close($sock);
            throw new Exception('Demon non joignable port ' . $port);
        }
        $msg = json_encode($_data) . "\n";
        socket_write($sock, $msg, strlen($msg));
        $buf = '';
        while (true) {
            $c = socket_read($sock, 4096);
            if ($c === false || $c === '') break;
            $buf .= $c;
            if (strpos($buf, "\n") !== false) break;
        }
        socket_close($sock);
        return !empty($buf) ? json_decode(trim($buf), true) : [];
    }

    public static function cron5() {
        if (self::deamon_info()['state'] != 'ok') return;
        foreach (self::byType(__CLASS__, true) as $eq) {
            if (!$eq->getIsEnable()) continue;
            try {
                $res = self::sendToDaemon([
                    'action'    => 'get_status',
                    'device_id' => $eq->getConfiguration('device_id'),
                ]);
                if (is_array($res) && empty($res['error'])) {
                    $res['device_id'] = $eq->getLogicalId();
                    $eq->updateFromData($res);
                }
            } catch (Exception $e) {
                log::add(__CLASS__, 'warning', 'cron5 ' . $eq->getName() . ': ' . $e->getMessage());
            }
        }
    }
}

class roborockCmd extends cmd {
    public function execute($_options = []) {
        if ($this->getType() == 'info') return;
        $this->getEqLogic()->executeAction($this, $_options);
    }
}