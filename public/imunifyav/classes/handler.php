<?php
require_once __DIR__ . '/init.php';

$request = new \Imunify360\Request($panel);
$request->handle();
