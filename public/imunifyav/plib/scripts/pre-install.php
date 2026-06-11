<?php

// SKIP_PREINSTALL_HOOK is passed from the rpm/deb package to skip hook if install from deb/rpm.
if (!empty(getenv('SKIP_PREINSTALL_HOOK'))) {
    exit(0);
}

// Check if deploy script is running and exit with error message if it is.
// It needed to prevent cases for example while post-uninstall script is still uninstalling the extension
// and we are trying to install the extension again.
$processes = shell_exec("ps ax");
$is_i360_running = strpos($processes, "i360deploy.sh") !== false;
$is_imav_running = strpos($processes, "imav-deploy.sh") !== false;
$logFile = $is_i360_running ? "/var/log/i360deploy.log" : "/var/log/imav-deploy.log";
$installation_process_running_message = "Installation cannot proceed as another install or uninstall process is "
    . "currently in progress. Please wait a few minutes and try again.\n"
    . "Logs can be found in $logFile\n";

if ($is_i360_running || $is_imav_running) {
    echo $installation_process_running_message;
    exit(1);
}

exit(0);