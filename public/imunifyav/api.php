<?php

require_once __DIR__ . '/classes/init.php';

$request = new \Imunify360\Request($panel);
$request->handle_api();

?>
