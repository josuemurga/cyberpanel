<?php

use \Imunify360\ImunifyLog;

$ext = pm_Extension::getById('imunify360');

if ($ext->isActive()) {
    ImunifyLog::info('Extension enabled, restoring imunify360 services');
    pm_ApiCli::callSbin('manage-services.sh', ['enable']);
} else {
    ImunifyLog::info('Extension disabled, stopping imunify360 services');
    pm_ApiCli::callSbin('manage-services.sh', ['disable']);
}
