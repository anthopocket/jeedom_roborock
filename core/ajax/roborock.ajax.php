<?php
set_time_limit(60);
require_once __DIR__ . '/../../../../core/php/core.inc.php';
ajax::init();

if (init('action') == 'get') {
    $eq = roborock::byId(init('id'));
    if (!is_object($eq)) ajax::error('Equipement introuvable');
    $humanTypes = ['action' => 'Action', 'info' => 'Info'];
    $return = array(
        'id'            => $eq->getId(),
        'name'          => $eq->getName(),
        'isEnable'      => $eq->getIsEnable(),
        'isVisible'     => $eq->getIsVisible(),
        'object_id'     => $eq->getObject_id(),
        'category'      => $eq->getCategory(),
        'configuration' => $eq->getConfiguration(),
        'cmds'          => array(),
    );
    foreach ($eq->getCmd() as $cmd) {
        $cmdVal = '';
        try {
            if ($cmd->getType() == 'info') $cmdVal = $cmd->execCmd();
        } catch (Exception $e) {}
        $return['cmds'][] = array(
            'id'            => $cmd->getId(),
            'name'          => $cmd->getName(),
            'logicalId'     => $cmd->getLogicalId(),
            'type'          => $cmd->getType(),
            'subType'       => $cmd->getSubType(),
            'humanType'     => $humanTypes[$cmd->getType()] ?? $cmd->getType(),
            'unite'         => $cmd->getUnite(),
            'isVisible'     => $cmd->getIsVisible(),
            'isHistorized'  => $cmd->getIsHistorized(),
            'currentValue'  => $cmdVal,
            'configuration' => $cmd->getConfiguration(),
        );
    }
    ajax::success($return);
}

if (init('action') == 'saveEqLogic') {
    $eq = roborock::byId(init('id'));
    if (!is_object($eq)) ajax::error('Equipement introuvable');
    $name = init('name');
    if (empty($name)) ajax::error('Le nom ne peut pas etre vide');
    $eq->setName($name);
    $eq->setIsEnable(init('isEnable'));
    $eq->setIsVisible(init('isVisible'));
    $objId = init('object_id');
    $eq->setObject_id(!empty($objId) ? $objId : null);
    $cat = json_decode(init('category'), true);
    if (is_array($cat)) {
        foreach ($cat as $key => $value) {
            $eq->setCategory($key, $value);
        }
    }
    $eq->save();
    ajax::success('Sauvegarde OK');
}

if (init('action') == 'recreateCommands') {
    $eq = roborock::byId(init('id'));
    if (!is_object($eq)) ajax::error('Equipement introuvable');
    $eq->createCommands();
    ajax::success('Commandes recreees');
}

if (init('action') == 'syncRoutines') {
    $eq = roborock::byId(init('id'));
    if (!is_object($eq)) ajax::error('Equipement introuvable');
    $res      = roborock::sendToDaemon([
        'action'    => 'get_routines',
        'device_id' => $eq->getConfiguration('device_id'),
    ]);
    $routines = $res['routines'] ?? [];
    foreach ($routines as $routine) {
        $logicalId = 'routine_' . $routine['id'];
        $cmd = $eq->getCmd('action', $logicalId);
        if (!is_object($cmd)) {
            $cmd = new roborockCmd();
            $cmd->setLogicalId($logicalId);
            $cmd->setEqLogic_id($eq->getId());
        }
        $cmd->setName('Routine: ' . $routine['name']);
        $cmd->setType('action');
        $cmd->setSubType('other');
        $cmd->setOrder(200 + intval($routine['id']));
        $cmd->setConfiguration('routine_id', $routine['id']);
        $cmd->save();
    }
    ajax::success(count($routines) . ' routine(s) synchronisee(s)');
}

if (init('action') == 'requestCode') {
    $email  = init('email');
    $region = init('region', '');
    if (empty($email)) ajax::error('Email requis');
    $path    = realpath(__DIR__ . '/../../resources');
    $python3 = $path . '/venv/bin/python3';
    $script  = $path . '/roborock_auth.py';
    if (!file_exists($python3)) ajax::error('Python venv introuvable: ' . $python3);
    if (!file_exists($script))  ajax::error('Script auth introuvable: ' . $script);

    // Nettoie les fichiers temporaires
    if (!is_dir('/tmp/roborock')) { mkdir('/tmp/roborock', 0770, true); chown('/tmp/roborock', 'www-data'); }
    @unlink('/tmp/roborock/code_pipe');
    @unlink('/tmp/roborock/auth_state');
    @unlink('/tmp/roborock/auth_result');

    // Lance le process en arriere-plan - il envoie le code et attend
    $cmd  = $python3 . ' ' . $script;
    $cmd .= ' --action request_code';
    $cmd .= ' --email ' . escapeshellarg($email);
    if (!empty($region)) $cmd .= ' --baseurl ' . escapeshellarg($region);
    $logFile = log::getPathToLog('roborock');
    exec($cmd . ' >> ' . $logFile . ' 2>&1 &');

    // Attend que le state soit ecrit = code envoye (max 15s)
    $ok = false;
    for ($i = 0; $i < 30; $i++) {
        usleep(500000); // 0.5s
        if (file_exists('/tmp/roborock/auth_state')) {
            $ok = true;
            break;
        }
        // Verifie si erreur
        if (file_exists('/tmp/roborock/auth_result')) {
            $out = trim(file_get_contents('/tmp/roborock/auth_result'));
            @unlink('/tmp/roborock/auth_result');
            $data = json_decode($out, true);
            if (isset($data['error'])) ajax::error($data['error']);
            break;
        }
    }
    if (!$ok) ajax::error('Timeout envoi code - verifiez les logs roborock');
    log::add('roborock', 'info', 'requestCode: code envoye a ' . $email);
    ajax::success('Code envoye');
}

if (init('action') == 'codeLogin') {
    $email  = init('email');
    $code   = trim(init('code'));
    $region = init('region', '');
    if (empty($email) || empty($code)) ajax::error('Email et code requis');

    // Verifie que request_code a ete appele
    if (!file_exists('/tmp/roborock/auth_state')) {
        ajax::error('Demandez d\'abord un code via le bouton "Envoyer le code"');
    }

    // Nettoie l'ancien resultat
    @unlink('/tmp/roborock/auth_result');

    // Ecrit le code dans le pipe - le process request_code le lit
    file_put_contents('/tmp/roborock/code_pipe', $code);

    // Attend le resultat (max 20s)
    $out = '';
    for ($i = 0; $i < 40; $i++) {
        usleep(500000); // 0.5s
        if (file_exists('/tmp/roborock/auth_result')) {
            $out = trim(file_get_contents('/tmp/roborock/auth_result'));
            @unlink('/tmp/roborock/auth_result');
            break;
        }
    }

    if (empty($out)) ajax::error('Timeout: pas de reponse du serveur Roborock');
    $decoded = json_decode($out, true);
    if (!is_array($decoded)) ajax::error('Reponse invalide: ' . $out);
    if (isset($decoded['error'])) ajax::error($decoded['error']);

    config::save('roborock_email',     $email,  'roborock');
    config::save('roborock_region',    $region, 'roborock');
    config::save('roborock_user_data', $out,    'roborock');
    log::add('roborock', 'info', 'codeLogin: authentification reussie pour ' . $email);
    ajax::success('Authentification reussie');
}

if (init('action') == 'passLogin') {
    $email    = init('email');
    $password = init('password');
    $region   = init('region', '');
    if (empty($email) || empty($password)) ajax::error('Email et mot de passe requis');
    $path    = realpath(__DIR__ . '/../../resources');
    $python3 = $path . '/venv/bin/python3';
    $script  = $path . '/roborock_auth.py';

    @unlink('/tmp/roborock/auth_result');

    $cmd  = $python3 . ' ' . $script;
    $cmd .= ' --action pass_login';
    $cmd .= ' --email '    . escapeshellarg($email);
    $cmd .= ' --password ' . escapeshellarg($password);
    if (!empty($region)) $cmd .= ' --baseurl ' . escapeshellarg($region);
    log::add('roborock', 'info', 'passLogin pour ' . $email);

    $output = []; $rc = 0;
    exec($cmd . ' 2>&1', $output, $rc);
    $out = trim(implode("\n", $output));
    log::add('roborock', 'info', 'passLogin rc=' . $rc . ' out=' . substr($out, 0, 200));
    if ($rc !== 0) ajax::error('Erreur auth: ' . $out);
    $decoded = json_decode($out, true);
    if (!is_array($decoded)) ajax::error('Reponse invalide: ' . $out);
    if (isset($decoded['error'])) ajax::error($decoded['error']);
    config::save('roborock_email',     $email,  'roborock');
    config::save('roborock_region',    $region, 'roborock');
    config::save('roborock_user_data', $out,    'roborock');
    ajax::success('Authentification reussie');
}

if (init('action') == 'resetAuth') {
    config::save('roborock_user_data', '', 'roborock');
    if (!is_dir('/tmp/roborock')) { mkdir('/tmp/roborock', 0770, true); chown('/tmp/roborock', 'www-data'); }
    @unlink('/tmp/roborock/code_pipe');
    @unlink('/tmp/roborock/auth_state');
    @unlink('/tmp/roborock/auth_result');
    ajax::success('Auth reinitialise');
}

if (init('action') == 'synchronize') {
    ajax::success(roborock::synchronize());
}

if (init('action') == 'syncRooms') {
    $eq = roborock::byId(init('id'));
    if (!is_object($eq)) ajax::error('Equipement introuvable');
    $res = roborock::sendToDaemon([
        'action'    => 'get_maps',
        'device_id' => $eq->getConfiguration('device_id'),
    ]);
    $maps = $res['maps'] ?? [];
    $count = 0;
    foreach ($maps as $map) {
        foreach ($map['rooms'] as $segId => $roomName) {
            $logicalId = 'room_' . $segId;
            $cmd = $eq->getCmd('action', $logicalId);
            $isNew = !is_object($cmd);
            if ($isNew) {
                $cmd = new roborockCmd();
                $cmd->setLogicalId($logicalId);
                $cmd->setEqLogic_id($eq->getId());
                $cmd->setIsVisible(1);
                $cmd->setName('Piece: ' . $roomName);
            }
            $cmd->setType('action');
            $cmd->setSubType('other');
            $cmd->setOrder(300 + intval($segId));
            $cmd->setConfiguration('segment_id', intval($segId));
            $cmd->save();
            $count++;
        }
    }
    ajax::success($count . ' piece(s) synchronisee(s)');
}

if (init('action') == 'syncRooms') {
    $eq = roborock::byId(init('id'));
    if (!is_object($eq)) ajax::error('Equipement introuvable');
    $res = roborock::sendToDaemon([
        'action'    => 'get_maps',
        'device_id' => $eq->getConfiguration('device_id'),
    ]);
    $maps = $res['maps'] ?? [];
    $count = 0;
    foreach ($maps as $map) {
        foreach ($map['rooms'] as $segId => $roomName) {
            $logicalId = 'room_' . $segId;
            $cmd = $eq->getCmd('action', $logicalId);
            $isNew = !is_object($cmd);
            if ($isNew) {
                $cmd = new roborockCmd();
                $cmd->setLogicalId($logicalId);
                $cmd->setEqLogic_id($eq->getId());
                $cmd->setIsVisible(1);
                $cmd->setName('Piece: ' . $roomName);
            }
            $cmd->setType('action');
            $cmd->setSubType('other');
            $cmd->setOrder(300 + intval($segId));
            $cmd->setConfiguration('segment_id', intval($segId));
            $cmd->save();
            $count++;
        }
    }
    ajax::success($count . ' piece(s) synchronisee(s)');
}

if (init('action') == 'getRooms') {
    $eq = roborock::byId(init('id'));
    if (!is_object($eq)) ajax::error('Equipement introuvable');
    $res = roborock::sendToDaemon([
        'action'    => 'get_maps',
        'device_id' => $eq->getConfiguration('device_id'),
    ]);
    ajax::success($res);
}

ajax::error('Action inconnue : ' . init('action'));