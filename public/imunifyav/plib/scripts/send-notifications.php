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

ImunifyNotificationsBuilder::dispatch($eventObject);
