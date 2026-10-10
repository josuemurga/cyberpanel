<!DOCTYPE html>
<?php # a license notice will be inserted under this line
require_once __DIR__ . '/classes/init.php';
$i360ieExist = file_exists('/var/run/imunifyemail/quarantine.sock') ? '1' : '0';
// Only hand the SPA a role when the web server actually declared one: the SPA
// takes a present i360role over the role in the JWT, so emitting the
// admin-by-default would boot a client session as admin on any deployment that
// serves this file without setting IMUNIFY360_ROLE. Absent the global, the SPA
// derives the role from the JWT on its own.
$i360roleDeclared = \Imunify360\panels\Generic::resolveRoleName($_SERVER) !== '';
if ($i360roleDeclared) {
    // The SPA only models admin/client roles; $panel (from init.php) maps the
    // generic user realm onto client. REMOTE_USER is the IE account for that
    // realm (resolved through the REDIRECT_ chain, like the role in init.php).
    $i360role = $panel->getSpaRole();
    $i360userName = \Imunify360\panels\Generic::resolveRemoteUser($_SERVER);
}
?>
<html>
<head>
    <meta http-equiv="Content-Security-Policy" content="default-src *    data: blob: 'unsafe-inline' 'unsafe-eval'; script-src * 'unsafe-inline' 'unsafe-eval'; connect-src * 'unsafe-inline'; img-src * data: blob: 'unsafe-inline'; frame-src *; style-src * data: blob: 'unsafe-inline'; font-src * data: blob: 'unsafe-inline';">
    <meta charset="UTF-8">
    <meta name="robots" content="noindex,nofollow">
    <title>Imunify360</title>
    <link rel="icon" type="image/x-icon" href="./favicon.ico">

    <meta name="importmap-type" content="systemjs-importmap">
    <link rel="stylesheet" type="text/css" href="./assets/static/container.css" />
    <link rel="stylesheet" type="text/css" href="./assets/static/fonts/fonts.css?v1" />

    <script type="text/javascript">
        var I360_PATH_TO_STATIC = "./assets/";
        // The SPA panel service reads these globals unconditionally; without
        // them nav-root/email-root die with ReferenceError. 'noPanel' is the
        // stand-alone flavour, same as the no-cp dev assets.
        var I360_PANEL = "noPanel";
        var IMUNIFY_PACKAGE = "360";
        var i360ieExist = '<?= $i360ieExist ?>';
<?php if ($i360roleDeclared): ?>
        var i360role = <?= json_encode($i360role) ?>;
        var i360userName = <?= json_encode($i360userName) ?>;
<?php endif; ?>
    </script>
    <script src="./assets/static/shared-dependencies/system.min.js"></script>
    <script src="./assets/static/shared-dependencies/amd.min.js"></script>
    <script src="./assets/static/shared-dependencies/named-exports.min.js"></script>
    <script src="./assets/static/shared-dependencies/named-register.min.js"></script>
    <script src="./assets/static/shared-dependencies/zone.min.js"></script>
    <script src="./assets/static/load-scripts-after-zone.js?v2"></script>
    <style>
        html { /* jumping scroll */
            overflow-y: scroll;
            background-color: #E6E6E6;
        }
        body {
            display: flex;
            align-content: flex-start;
            flex-wrap: wrap;
            margin: 0 auto;
            padding: 8px 25px;
            max-width: 1600px;
            background-color: white;
            min-height: calc(100vh - 16px);
        }
        #spa_wrapper { /* fills body so .i360-app inside can center via margin:auto */
            flex: 1 0 100%;
        }
        .i360-app { /* centering */
            margin: auto;
        }
        /*
         * Pin the SPA container to spa_wrapper width. The flex `margin:auto`
         * above lets the .i360-app__container shrink to its content's
         * max-content width on routes whose content is narrow (e.g.
         * Incidents = 889px), then re-stretch on routes whose content is
         * wider (Dashboard with "Poor protection" cards = 974px). The
         * resulting "jump bigger then back" is jarring during route
         * transitions. Force-stretch the outer container so layout width
         * is route-independent; per-page centering remains the route
         * component's responsibility.
         */
        #spa_wrapper > .i360-app__container {
            width: 100%;
            margin: 0;
        }
    </style>
    <template id="single-spa-layout">
        <single-spa-router mode="hash" containerEl="#spa_wrapper">
            <div class="i360-app i360-app-outer i360-app__container">
                <application name="@imunify/nav-root"></application>
                <div class="main-content">
                    <route path="360/:role/email">
                        <application name="@imunify/email-root" loader="loader"></application>
                    </route>
                    <route default>
                        <application name="@imunify/other-root" loader="loader"></application>
                    </route>
                </div>
            </div>
            <div class="i360-app__loader">
                <div class="i360-app__loader-icon"></div>
            </div>
        </single-spa-router>
    </template>
    <base href="./">
</head>
<body>
    <div id="spa_wrapper" class="display-flex-column"></div>
</body>
</html>
