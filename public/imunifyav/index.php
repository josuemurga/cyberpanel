<!DOCTYPE html>
<?php # a license notice will be inserted under this line
require_once __DIR__ . '/classes/init.php';
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
        .i360-app { /* centering */
            margin: auto;
        }
    </style>
    <template id="single-spa-layout">
        <single-spa-router mode="hash">
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
        </single-spa-router>
    </template>
    <base href="./">
</head>
<body>
    <div class="i360-app__loader">
        <div class="i360-app__loader-icon"></div>
    </div>
</body>
</html>
