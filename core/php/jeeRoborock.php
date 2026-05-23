<?php
require_once __DIR__ . '/../../../../core/php/core.inc.php';
if (!jeedom::apiAccess(init('apikey'), 'roborock')) {
    echo json_encode(['result' => 'error', 'message' => 'Cle API invalide']);
    die();
}
$data = json_decode(file_get_contents('php://input'), true);
if (!is_array($data)) {
    echo json_encode(['result' => 'error', 'message' => 'JSON invalide']);
    die();
}
log::add('roborock', 'debug', 'Callback: ' . json_encode($data));
try {
    switch ($data['action'] ?? '') {
        case 'update':
            roborock::callbackFromDaemon($data);
            break;
        case 'log':
            log::add('roborock', $data['level'] ?? 'debug', '[daemon] ' . ($data['message'] ?? ''));
            break;
    }
    echo json_encode(['result' => 'ok']);
} catch (Exception $e) {
    log::add('roborock', 'error', 'Callback error: ' . $e->getMessage());
    echo json_encode(['result' => 'error', 'message' => $e->getMessage()]);
}