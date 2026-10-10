<?php

use \Imunify360\ImunifyNotificationsBuilder;
use \Imunify360\ImunifyLog;

// Read JSON input from STDIN
$jsonInput   = file_get_contents('php://stdin');
$eventObject = json_decode($jsonInput);

if (!$eventObject || (!isset($eventObject->event_id) && !isset($eventObject->message_type))) {
    ImunifyLog::err('Imunify: send-notifications.php - event_id or message_type is not defined');
    exit;
}

try {
    ImunifyNotificationsBuilder::dispatch($eventObject);
} catch (\Throwable $e) {
    ImunifyLog::err('Imunify: send-notifications.php - failed to dispatch notification: ' . $e->getMessage());
    // nonzero status so the agent's check_run does not record the
    // notification as delivered and refresh its throttle
    exit(1);
}
