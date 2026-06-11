<?php

require_once __DIR__ . '/autoloader.php';

$loader = new Imunify360Psr4Autoloader();
$loader->addNamespace('Imunify360', __DIR__);

$panel = new \Imunify360\panels\Generic();
