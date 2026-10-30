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

    /* Fichiers de carte ecrits par le demon (meme regle de nommage que roborockd.py) */
    public static function mapPaths($_deviceId) {
        $safe = preg_replace('/[^0-9A-Za-z_-]/', '', (string) $_deviceId);
        $dir = realpath(__DIR__ . '/../../data');
        if ($dir === false) $dir = __DIR__ . '/../../data';
        return ['png' => $dir . '/map_' . $safe . '.png', 'json' => $dir . '/map_' . $safe . '.json'];
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
            // Remplissage immediat des infos avec l'etat deja connu du demon
            try {
                $res = self::sendToDaemon(['action' => 'get_status', 'device_id' => $deviceId], 15);
                if (is_array($res) && empty($res['error'])) {
                    $res['device_id'] = $deviceId;
                    $eqLogic->updateFromData($res);
                }
            } catch (Exception $e) {
                log::add(__CLASS__, 'warning', 'Etat initial ' . $device['name'] . ': ' . $e->getMessage());
            }
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

    /* Cles du message demon qui ne sont pas des commandes info */
    const RESERVED_KEYS = ['device_id', 'action', 'options', 'capabilities', 'error', 'success', 'message', 'warning'];

    /* Liste demon (options) -> commande action select a mettre a jour */
    const OPTION_TARGETS = [
        'fan_speed'            => 'set_fan_speed',
        'mop_intensity'        => 'set_mop_intensity',
        'mop_mode'             => 'set_mop_mode',
        'dust_collection_mode' => 'set_dust_collection_mode',
        'wash_towel_mode'      => 'set_wash_towel_mode',
    ];

    public function updateFromData($_data) {
        if (isset($_data['capabilities']) && is_array($_data['capabilities'])) {
            $this->applyCapabilities($_data['capabilities']);
        }
        if (isset($_data['options']) && is_array($_data['options'])) {
            $this->applyOptions($_data['options']);
        }
        foreach ($_data as $key => $value) {
            if (in_array($key, self::RESERVED_KEYS, true) || is_array($value)) continue;
            $cmd = $this->getCmd('info', $key);
            if (!is_object($cmd)) continue;
            $this->checkAndUpdateCmd($cmd, $value);
        }
    }

    /* Enregistre les capacites annoncees par le robot ; cree les commandes nouvellement supportees */
    private function applyCapabilities($_caps) {
        ksort($_caps);
        $new = json_encode($_caps);
        $old = $this->getConfiguration('capabilities', '');
        if (is_array($old)) $old = json_encode($old);
        if ($new === $old) return;
        log::add(__CLASS__, 'info', $this->getHumanName() . ' capacites: ' . $new);
        $this->setConfiguration('capabilities', $new);
        $this->save(true);
        $this->createCommands();
    }

    /* Met a jour les listes deroulantes avec les seules valeurs supportees par le robot */
    private function applyOptions($_options) {
        foreach (self::OPTION_TARGETS as $optKey => $cmdLogicalId) {
            if (empty($_options[$optKey]) || !is_array($_options[$optKey])) continue;
            $cmd = $this->getCmd('action', $cmdLogicalId);
            if (!is_object($cmd)) continue;
            $parts = [];
            foreach ($_options[$optKey] as $opt) {
                if (!is_array($opt) || count($opt) < 2) continue;
                $parts[] = str_replace(['|', ';'], ' ', $opt[0]) . '|' . str_replace(['|', ';'], ' ', $opt[1]);
            }
            $listValue = implode(';', $parts);
            if ($listValue !== '' && $cmd->getConfiguration('listValue') !== $listValue) {
                $cmd->setConfiguration('listValue', $listValue);
                $cmd->save();
            }
        }
    }

    private function getCapabilities() {
        $caps = $this->getConfiguration('capabilities', '');
        if (is_array($caps)) return $caps;
        $decoded = json_decode((string) $caps, true);
        return is_array($decoded) ? $decoded : [];
    }

    /*
     * Definition des commandes :
     *  [nom, logicalId, type, subType, ordre, options...]
     *  'cap' => capacite requise (commande non creee si le robot declare ne pas l'avoir ;
     *           creee si la capacite est inconnue). Une commande existante n'est jamais supprimee.
     */
    public static function commandDefinitions() {
        $passages = ['title_placeholder' => 'Passages (1-3)'];
        return [
            // === ACTIONS VACUUM ===
            ['Demarrer',               'start',                  'action', 'other',   1],
            ['Pause',                  'pause',                  'action', 'other',   2],
            ['Reprendre',              'resume',                 'action', 'other',   3],
            ['Arreter',                'stop',                   'action', 'other',   4],
            ['Rentrer base',           'dock',                   'action', 'other',   5],
            ['Localiser',              'locate',                 'action', 'other',   6],
            ['Nettoyage ponctuel',     'spot_clean',             'action', 'other',   7],
            ['Synchroniser',           'sync',                   'action', 'other',   8],
            ['Rafraichir',             'refresh',                'action', 'other',   9],
            ['Rafraichir carte',       'refresh_map',            'action', 'other',  19],

            // === ACTIONS PARAMETRES ===
            ['Regler vitesse ventil',  'set_fan_speed',          'action', 'select',  10,
                'listValue' => 'quiet|Silencieux;balanced|Equilibre;turbo|Turbo;max|Maximum;off|Arret;max_plus|Maximum+;smart_mode|Auto', 'value' => 'fan_speed'],
            ['Regler intensite mop',   'set_mop_intensity',      'action', 'select',  11, 'cap' => 'mop',
                'listValue' => 'off|Arret;slight|Tres faible;low|Faible;medium_slide|Moyen slide;moderate|Modere;high|Eleve;high_slide|Eleve slide;extreme|Extreme;smart_mode|Auto', 'value' => 'mop_intensity'],
            ['Regler mode mop',        'set_mop_mode',           'action', 'select',  12, 'cap' => 'mop',
                'listValue' => 'standard|Standard;deep|Profond;deep_plus|Profond+;fast|Rapide;smart_mode|Auto', 'value' => 'mop_mode'],
            ['Regler volume',          'set_volume',             'action', 'slider',  13,
                'minValue' => 0, 'maxValue' => 100, 'value' => 'volume'],
            ['Type nettoyage',         'set_clean_type',         'action', 'select',  14, 'cap' => 'mop',
                'listValue' => 'vacuum|Aspiration seule;vac_and_mop|Aspiration et lavage;mop|Lavage seul', 'value' => 'clean_type'],

            // === NETTOYAGE CIBLE ===
            ['Nettoyer des pieces',    'clean_rooms',            'action', 'message', 15,
                'display' => $passages + ['message_placeholder' => 'Noms separes par des virgules (ex: Cuisine, Salon)']],
            ['Nettoyer segments',      'clean_segment',          'action', 'message', 16,
                'display' => $passages + ['message_placeholder' => 'Numeros de segments (ex: 16,17)']],
            ['Nettoyer une zone',      'clean_zone',             'action', 'message', 17,
                'display' => $passages + ['message_placeholder' => 'x1,y1,x2,y2 en mm (zones separees par ;)']],
            ['Aller au point',         'goto_position',          'action', 'message', 18,
                'display' => ['title_disable' => 1, 'message_placeholder' => 'x,y en mm']],

            // === ACTIONS SWITCHES / REGLAGES APPAREIL ===
            ['Verr. enfant On',        'child_lock_on',          'action', 'other',   20, 'cap' => 'child_lock'],
            ['Verr. enfant Off',       'child_lock_off',         'action', 'other',   21, 'cap' => 'child_lock'],
            ['LED On',                 'led_on',                 'action', 'other',   22, 'cap' => 'led'],
            ['LED Off',                'led_off',                'action', 'other',   23, 'cap' => 'led'],
            ['NDD On',                 'dnd_on',                 'action', 'other',   24],
            ['NDD Off',                'dnd_off',                'action', 'other',   25],
            ['NDD definir plage',      'dnd_set_range',          'action', 'message', 32,
                'display' => ['title_disable' => 1, 'message_placeholder' => 'HH:MM-HH:MM (ex: 22:00-08:00)']],
            ['Heures creuses On',      'valley_on',              'action', 'other',   33, 'cap' => 'valley'],
            ['Heures creuses Off',     'valley_off',             'action', 'other',   34, 'cap' => 'valley'],
            ['Heures creuses plage',   'valley_set_range',       'action', 'message', 35, 'cap' => 'valley',
                'display' => ['title_disable' => 1, 'message_placeholder' => 'HH:MM-HH:MM (ex: 22:00-06:00)']],

            // === ACTIONS DOCK ===
            ['Vider le bac',           'start_dust_collection',  'action', 'other',   26, 'cap' => 'has_dock'],
            ['Arreter vidage bac',     'stop_dust_collection',   'action', 'other',   27, 'cap' => 'has_dock'],
            ['Laver serpilliere',      'start_wash',             'action', 'other',   28, 'cap' => 'wash_station'],
            ['Arreter lavage',         'stop_wash',              'action', 'other',   29, 'cap' => 'wash_station'],
            ['Demarrer sechage',       'start_dry',              'action', 'other',   30, 'cap' => 'wash_station'],
            ['Arreter sechage',        'stop_dry',               'action', 'other',   31, 'cap' => 'wash_station'],
            ['Regler mode vidage',     'set_dust_collection_mode', 'action', 'select', 36, 'cap' => 'dust_mode',
                'listValue' => 'smart|Intelligent;light|Leger;balanced|Equilibre;max|Maximum', 'value' => 'dust_collection_mode'],
            ['Regler mode lavage',     'set_wash_towel_mode',    'action', 'select',  37, 'cap' => 'wash_mode',
                'listValue' => 'light|Leger;balanced|Equilibre;deep|Profond', 'value' => 'wash_towel_mode'],

            // === RESET CONSOMMABLES ===
            ['Reset brosse princ.',    'reset_main_brush',       'action', 'other',   40],
            ['Reset brosse lat.',      'reset_side_brush',       'action', 'other',   41],
            ['Reset filtre',           'reset_filter',           'action', 'other',   42],
            ['Reset capteurs',         'reset_sensor',           'action', 'other',   43],
            ['Reset rouleau mop',      'reset_moproller',        'action', 'other',   44],
            ['Reset filtre eau',       'reset_strainer',         'action', 'other',   45, 'cap' => 'strainer'],
            ['Reset coll. poussiere',  'reset_dust_collection',  'action', 'other',   46, 'cap' => 'dust_bag'],
            ['Reset brosse nettoyage', 'reset_cleaning_brush',   'action', 'other',   47, 'cap' => 'cleaning_brush'],

            // === STATUT ===
            ['Statut',                 'status',                 'info', 'string',   50, 'generic_type' => 'VACUUM_STATE'],
            ['Batterie',               'battery',                'info', 'numeric',  51, 'generic_type' => 'BATTERY', 'unite' => '%'],
            ['En charge',              'is_charging',            'info', 'binary',   52],
            ['En nettoyage',           'is_cleaning',            'info', 'binary',   53],
            ['En retour base',         'in_returning',           'info', 'binary',   54],
            ['En pause',               'is_paused',              'info', 'binary',   55],
            ['Type nettoyage (val)',   'clean_type',             'info', 'string',   56],
            ['En ligne',               'online',                 'info', 'binary',   48],
            ['Derniere mise a jour',   'last_update',            'info', 'string',   49],
            ['Piece courante',         'current_room',           'info', 'string',   66],
            ['Carte mise a jour',      'map_update',             'info', 'string',   67],

            // === ALERTES ERREURS ===
            ['Erreur aspirateur (code)',  'vacuum_error',        'info', 'numeric',  57],
            ['Erreur aspirateur (label)', 'vacuum_error_label',  'info', 'string',   58],
            ['Aspirateur en erreur',      'vacuum_has_error',    'info', 'binary',   59],
            ['Erreur dock (code)',        'dock_error',          'info', 'numeric',  60],
            ['Erreur dock (label)',       'dock_error_label',    'info', 'string',   61],
            ['Dock en erreur',            'dock_has_error',      'info', 'binary',   62],

            // === NETTOYAGE EN COURS / DERNIER NETTOYAGE ===
            ['Surface nettoyee',       'cleaning_area',          'info', 'numeric',  63, 'unite' => 'm2'],
            ['Duree nettoyage',        'cleaning_time',          'info', 'numeric',  64, 'unite' => 'min'],
            ['Progression',            'cleaning_progress',      'info', 'numeric',  65, 'unite' => '%'],
            ['Dernier debut',          'last_clean_begin',       'info', 'string',   69],
            ['Derniere fin',           'last_clean_end',         'info', 'string',   70],
            ['Dernier nett. duree',    'last_clean_duration',    'info', 'numeric', 123, 'unite' => 'min'],
            ['Dernier nett. surface',  'last_clean_area',        'info', 'numeric', 124, 'unite' => 'm2'],
            ['Dernier nett. fin',      'last_clean_finish_reason', 'info', 'string', 125],
            ['Dernier nett. complet',  'last_clean_complete',    'info', 'binary',  126],
            ['Dernier nett. erreur',   'last_clean_error',       'info', 'string',  127],

            // === STATISTIQUES CUMULEES (historisees) ===
            ['Total duree nettoyage',  'total_clean_time',       'info', 'numeric', 130, 'unite' => 'h',  'history' => 1],
            ['Total surface nettoyee', 'total_clean_area',       'info', 'numeric', 131, 'unite' => 'm2', 'history' => 1],
            ['Total nettoyages',       'total_clean_count',      'info', 'numeric', 132, 'history' => 1],
            ['Total vidages bac',      'total_dust_collection_count', 'info', 'numeric', 133, 'cap' => 'has_dock', 'history' => 1],

            // === PARAMETRES ===
            ['Vitesse ventil.',        'fan_speed',              'info', 'string',   71],
            ['Intensite mop',          'mop_intensity',          'info', 'string',   72, 'cap' => 'mop'],
            ['Mode mop',               'mop_mode',               'info', 'string',   73, 'cap' => 'mop'],
            ['Volume',                 'volume',                 'info', 'numeric',  74, 'unite' => '%'],
            ['Mode vidage',            'dust_collection_mode',   'info', 'string',   75, 'cap' => 'dust_mode'],
            ['Mode lavage',            'wash_towel_mode',        'info', 'string',   76, 'cap' => 'wash_mode'],

            // === CAPTEURS / REGLAGES ===
            ['Serpilliere attachee',   'mop_attached',           'info', 'binary',   80, 'cap' => 'mop'],
            ['Reservoir eau attache',  'water_box_attached',     'info', 'binary',   81, 'cap' => 'mop'],
            ['Manque eau',             'water_shortage',         'info', 'binary',   82, 'cap' => 'mop'],
            ['Verr. enfant',           'child_lock',             'info', 'binary',   83, 'cap' => 'child_lock'],
            ['LED',                    'led_status',             'info', 'binary',   84, 'cap' => 'led'],
            ['Ne pas deranger',        'do_not_disturb',         'info', 'binary',   85],
            ['NDD debut',              'do_not_disturb_begin',   'info', 'string',   86],
            ['NDD fin',                'do_not_disturb_end',     'info', 'string',   87],
            ['Heures creuses',         'valley',                 'info', 'binary',   88, 'cap' => 'valley'],
            ['Heures creuses debut',   'valley_begin',           'info', 'string',   89, 'cap' => 'valley'],
            ['Heures creuses fin',     'valley_end',             'info', 'string',   99, 'cap' => 'valley'],

            // === DOCK ===
            ['Statut charge',          'charge_status',          'info', 'numeric',  90],
            ['Statut sechage',         'dry_status',             'info', 'numeric',  91, 'cap' => 'wash_station'],
            ['Statut lavage',          'wash_status',            'info', 'numeric',  92, 'cap' => 'wash_station'],
            ['Collecte poussiere',     'dust_collection',        'info', 'numeric',  93, 'cap' => 'has_dock'],
            ['Eau propre dock',        'dock_clear_water_status', 'info', 'numeric', 94, 'cap' => 'wash_station'],
            ['Eau sale dock',          'dock_dirty_water_status', 'info', 'numeric', 95, 'cap' => 'wash_station'],
            ['Bac poussiere dock',     'dock_dust_bag_status',   'info', 'numeric',  96, 'cap' => 'has_dock'],
            ['Reservoir eau propre vide', 'clear_water_empty',   'info', 'binary',   97, 'cap' => 'wash_station'],
            ['Bac eau sale plein ou absent', 'dirty_water_full', 'info', 'binary',   98, 'cap' => 'wash_station'],
            ['Sac poussiere absent',   'dust_bag_alert',         'info', 'binary',  108, 'cap' => 'has_dock'],

            // === CONSOMMABLES (heures utilisees) ===
            ['Brosse princ. (h util)', 'main_brush_work_time',   'info', 'numeric', 100, 'unite' => 'h'],
            ['Brosse lat. (h util)',   'side_brush_work_time',   'info', 'numeric', 101, 'unite' => 'h'],
            ['Filtre (h util)',        'filter_work_time',       'info', 'numeric', 102, 'unite' => 'h'],
            ['Capteurs (h util)',      'sensor_dirty_time',      'info', 'numeric', 103, 'unite' => 'h'],
            ['Rouleau mop (h util)',   'moproller_work_time',    'info', 'numeric', 104, 'unite' => 'h'],
            ['Filtre eau (util)',      'strainer_work_times',    'info', 'numeric', 105, 'cap' => 'strainer'],
            ['Coll. poussi. (util)',   'dust_collection_work_times', 'info', 'numeric', 106, 'cap' => 'dust_bag'],
            ['Brosse nett. (util)',    'cleaning_brush_work_times',  'info', 'numeric', 107, 'cap' => 'cleaning_brush'],

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
            ['Filtre eau (%)',         'strainer_pct',           'info', 'numeric', 120, 'unite' => '%', 'cap' => 'strainer'],
            ['Coll. poussiere (%)',    'dust_coll_pct',          'info', 'numeric', 121, 'unite' => '%', 'cap' => 'dust_bag'],
            ['Brosse nettoyage (%)',   'cleaning_pct',           'info', 'numeric', 122, 'unite' => '%', 'cap' => 'cleaning_brush'],
        ];
    }

    public function createCommands() {
        $caps = $this->getCapabilities();
        $created = 0;
        foreach (self::commandDefinitions() as $d) {
            $cmd = $this->getCmd($d[2], $d[1]);
            $isNew = !is_object($cmd);
            if ($isNew) {
                if (!empty($d['cap']) && array_key_exists($d['cap'], $caps) && $caps[$d['cap']] === false) {
                    continue; // capacite absente sur ce robot
                }
                $cmd = new roborockCmd();
                $cmd->setLogicalId($d[1]);
                $cmd->setEqLogic_id($this->getId());
                $cmd->setName($d[0]);
                $cmd->setIsVisible(1);
                if (!empty($d['history'])) $cmd->setIsHistorized(1);
                if (!empty($d['listValue'])) $cmd->setConfiguration('listValue', $d['listValue']);
                $created++;
            }
            $cmd->setType($d[2]);
            $cmd->setSubType($d[3]);
            $cmd->setOrder($d[4]);
            if (!empty($d['generic_type'])) $cmd->setGeneric_type($d['generic_type']);
            if (!empty($d['unite']))        $cmd->setUnite($d['unite']);
            if (isset($d['minValue']))      $cmd->setConfiguration('minValue', $d['minValue']);
            if (isset($d['maxValue']))      $cmd->setConfiguration('maxValue', $d['maxValue']);
            if (!empty($d['display'])) {
                foreach ($d['display'] as $k => $v) $cmd->setDisplay($k, $v);
            }
            $cmd->save();
        }
        // Lier les commandes action a leur info (retour d'etat des listes / curseur)
        foreach (self::commandDefinitions() as $d) {
            if ($d[2] != 'action' || empty($d['value'])) continue;
            $cmdAction = $this->getCmd('action', $d[1]);
            $cmdInfo   = $this->getCmd('info', $d['value']);
            if (is_object($cmdAction) && is_object($cmdInfo) && $cmdAction->getValue() != $cmdInfo->getId()) {
                $cmdAction->setValue($cmdInfo->getId());
                $cmdAction->save();
            }
        }
        return $created;
    }

    /* Cree / renomme les commandes "Nettoyer <piece>" ; conserve un nom personnalise */
    public function syncRooms() {
        $res = self::sendToDaemon([
            'action'    => 'get_rooms',
            'device_id' => $this->getConfiguration('device_id'),
        ]);
        if (!empty($res['error'])) throw new Exception($res['error']);
        $rooms = $res['rooms'] ?? [];
        $count = 0;
        foreach ($rooms as $room) {
            $segId = intval($room['segment_id']);
            $autoName = 'Nettoyer ' . trim($room['name']);
            $logicalId = 'room_' . $segId;
            $cmd = $this->getCmd('action', $logicalId);
            if (!is_object($cmd)) {
                $cmd = new roborockCmd();
                $cmd->setLogicalId($logicalId);
                $cmd->setEqLogic_id($this->getId());
                $cmd->setIsVisible(1);
                $cmd->setName($autoName);
            } else {
                $previousAuto = $cmd->getConfiguration('auto_name', '');
                $current = $cmd->getName();
                // renomme seulement si le nom n'a pas ete personnalise dans Jeedom
                if ($current === $previousAuto || preg_match('/^Piece: Piece \d+$/', $current)) {
                    $cmd->setName($autoName);
                }
            }
            $cmd->setType('action');
            $cmd->setSubType('other');
            $cmd->setOrder(300 + $segId);
            $cmd->setConfiguration('segment_id', $segId);
            $cmd->setConfiguration('room_name', $room['name']);
            $cmd->setConfiguration('auto_name', $autoName);
            try {
                $cmd->save();
            } catch (Exception $e) {
                // nom deja utilise par une autre commande : suffixe le segment
                $cmd->setName($autoName . ' (' . $segId . ')');
                $cmd->save();
            }
            $count++;
        }
        return $count;
    }

    public function executeAction($_cmd, $_options = []) {
        $deviceId = $this->getConfiguration('device_id');
        $lid      = $_cmd->getLogicalId();
        $p        = ['action' => $lid, 'device_id' => $deviceId];
        $message  = trim($_options['message'] ?? '');
        $title    = trim($_options['title'] ?? '');

        if (strpos($lid, 'routine_') === 0) {
            $p['action']     = 'execute_routine';
            $p['routine_id'] = intval($_cmd->getConfiguration('routine_id'));
        } elseif (strpos($lid, 'room_') === 0) {
            $p['action']   = 'clean_segment';
            $p['segments'] = [intval($_cmd->getConfiguration('segment_id'))];
            $p['repeat']   = 1;
        } else {
            switch ($lid) {
                case 'sync':
                    self::synchronize();
                    return;
                case 'set_fan_speed':
                case 'set_mop_intensity':
                case 'set_mop_mode':
                case 'set_clean_type':
                case 'set_dust_collection_mode':
                case 'set_wash_towel_mode':
                    $p['value'] = $_options['select'] ?? '';
                    if ($p['value'] === '') throw new Exception(__('Aucune valeur choisie', __FILE__));
                    break;
                case 'set_volume':
                    $p['value'] = intval($_options['slider'] ?? 50);
                    break;
                case 'clean_rooms':
                    // Message = noms ; Titre = nombre de passages. Message vide : le titre porte les noms.
                    if ($message === '') { $message = $title; $title = ''; }
                    $p['rooms']  = $message;
                    $p['repeat'] = $title;
                    break;
                case 'clean_segment':
                    if ($message === '') { $message = $title; $title = ''; }
                    $p['segments'] = array_values(array_filter(array_map('trim', explode(',', $message)), 'strlen'));
                    $p['repeat']   = $title;
                    break;
                case 'clean_zone':
                    if ($message === '') { $message = $title; $title = ''; }
                    $p['zones']  = $message;
                    $p['repeat'] = $title;
                    break;
                case 'goto_position':
                    $pts = array_map('trim', explode(',', $message !== '' ? $message : $title));
                    if (count($pts) < 2 || !is_numeric($pts[0]) || !is_numeric($pts[1])) {
                        throw new Exception(__('Coordonnees invalides : attendu x,y en mm', __FILE__));
                    }
                    $p['x'] = intval($pts[0]);
                    $p['y'] = intval($pts[1]);
                    break;
                case 'dnd_set_range':
                case 'valley_set_range':
                    $p['value'] = $message !== '' ? $message : $title;
                    break;
            }
        }

        $res = self::sendToDaemon($p);
        if (!is_array($res) || (empty($res) && $lid != 'refresh')) {
            throw new Exception(__('Pas de reponse du demon', __FILE__));
        }
        if (!empty($res['error'])) {
            log::add(__CLASS__, 'warning', $this->getHumanName() . ' ' . $lid . ' : ' . $res['error']);
            throw new Exception($res['error']);
        }
        if (!empty($res['warning'])) {
            log::add(__CLASS__, 'warning', $this->getHumanName() . ' ' . $lid . ' : ' . $res['warning']);
        } elseif (!empty($res['message'])) {
            log::add(__CLASS__, 'info', $this->getHumanName() . ' ' . $lid . ' : ' . $res['message']);
        }
    }

    public static function sendToDaemon($_data, $_timeout = 50) {
        $port = self::DAEMON_SOCKET_PORT;
        $sock = @socket_create(AF_INET, SOCK_STREAM, SOL_TCP);
        if ($sock === false) throw new Exception('socket_create failed');
        socket_set_option($sock, SOL_SOCKET, SO_RCVTIMEO, ['sec' => $_timeout, 'usec' => 0]);
        socket_set_option($sock, SOL_SOCKET, SO_SNDTIMEO, ['sec' => 5, 'usec' => 0]);
        if (!@socket_connect($sock, '127.0.0.1', $port)) {
            socket_close($sock);
            throw new Exception(__('Demon non joignable (port ', __FILE__) . $port . ')');
        }
        $msg = json_encode($_data) . "\n";
        socket_write($sock, $msg, strlen($msg));
        $buf = '';
        while (true) {
            $c = @socket_read($sock, 8192);
            if ($c === false || $c === '') break;
            $buf .= $c;
            if (strpos($buf, "\n") !== false) break;
        }
        socket_close($sock);
        if ($buf === '') throw new Exception(__('Delai depasse : pas de reponse du demon', __FILE__));
        $decoded = json_decode(trim($buf), true);
        return is_array($decoded) ? $decoded : [];
    }

    public static function cron5() {
        if (self::deamon_info()['state'] != 'ok') return;
        foreach (self::byType(__CLASS__, true) as $eq) {
            if (!$eq->getIsEnable()) continue;
            try {
                $res = self::sendToDaemon([
                    'action'    => 'get_status',
                    'device_id' => $eq->getConfiguration('device_id'),
                ], 15);
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