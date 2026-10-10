<?php

// alt-php ships display_errors=stderr, and PHP honours "stderr" only for the
// cli/cgi/phpdbg SAPIs — under FPM it falls through to stdout, interleaving
// diagnostics into the response body ahead of the JSON the SPA parses.
// Errors still reach the PHP error log via log_errors.
ini_set('display_errors', '0');

require_once __DIR__ . '/autoloader.php';

$loader = new Imunify360Psr4Autoloader();
$loader->addNamespace('Imunify360', __DIR__);

// The Apache vhost is expected to set IMUNIFY360_ROLE per location:
//   - /i360/admin/  → SetEnv IMUNIFY360_ROLE admin   (htpasswd-gated)
//   - /i360/user/   → SetEnv IMUNIFY360_ROLE user    (PAM-gated against system users)
// Role resolution (REDIRECT_ prefix handling, admin-as-opt-in, historical
// admin-only default) lives in Generic::resolveIsAdmin so it is unit-tested.
$isAdmin = \Imunify360\panels\Generic::resolveIsAdmin($_SERVER);

$panel = new \Imunify360\panels\Generic($isAdmin);
