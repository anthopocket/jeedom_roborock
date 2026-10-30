<?php
/*
 * Image et repere de la carte d'un robot (utilisateur Jeedom connecte uniquement).
 *   plugins/roborock/core/php/roborockMap.php?id=<id equipement>          -> PNG
 *   plugins/roborock/core/php/roborockMap.php?id=<id equipement>&meta=1   -> JSON (repere, pieces, robot)
 * Utilisable directement dans un widget / une page HTML perso : <img src="...">
 */
require_once __DIR__ . '/../../../../core/php/core.inc.php';
if (!isConnect()) {
    http_response_code(401);
    die();
}
$eq = roborock::byId(intval(init('id')));
if (!is_object($eq) || $eq->getEqType_name() != 'roborock') {
    http_response_code(404);
    die();
}
$paths = roborock::mapPaths($eq->getConfiguration('device_id'));
$file = init('meta') ? $paths['json'] : $paths['png'];
if (!file_exists($file)) {
    http_response_code(404);
    die();
}
header('Cache-Control: no-cache, must-revalidate');
header('Content-Type: ' . (init('meta') ? 'application/json' : 'image/png'));
header('Content-Length: ' . filesize($file));
readfile($file);
