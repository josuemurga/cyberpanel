<?php

use \Imunify360\ImunifyHelper;

// Check if deploy script is running and wait before stating the deploy process.
// It needed to prevent cases for example while post-install script is still installing the extension
// and we are trying to uninstall it.
// Except when SKIP_PREUNINSTALL_CHECK is passed from the rpm/deb package
if (empty(getenv('SKIP_PREUNINSTALL_CHECK'))) {
    ImunifyHelper::waitForDeployProcessFinish();
}

pm_ApiCli::callSbin('deploy.sh', array('-u'));
