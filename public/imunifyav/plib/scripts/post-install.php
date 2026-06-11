<?php

use \Imunify360\ImunifyHelper;
use \Imunify360\MovePermissions;

ImunifyHelper::deploy();

MovePermissions::migrate();

ImunifyHelper::disableRevisiumAntivirus();

// Apply a fix for Ubuntu 24 repos
pm_ApiCli::callSbin('ubuntu24-hot-fix.sh', []);
