<?php
$moduleId = basename(__DIR__);

pm_Context::init($moduleId);

$application = new pm_Application();
$application->run();
