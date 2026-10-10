<?php
// Request::handle dispatches `commandIE` to imunifyEmailAction
// (which goes through ImunifyEmailClient — exercised by
// test_user_method_whitelist.php). Non-IE traffic still falls through to
// defaultAction → adminAction / userAction, as before.
//
// Run:
//   php src/asyncclient/ui/agent/plugins/generic/tests/test_command_ie_routing.php

declare(strict_types=1);

require_once __DIR__ . '/../../common/classes/autoloader.php';

$loader = new Imunify360Psr4Autoloader();
$loader->addNamespace('Imunify360', __DIR__ . '/../../common/classes');
$loader->addNamespace('Imunify360', __DIR__ . '/../classes');

$_SERVER['REMOTE_ADDR'] = '203.0.113.7';
$_POST = [];

class TrackingPanel extends \Imunify360\panels\AbstractPanel
{
    public $jsonInput = '';
    public $imunifyEmailCalled = false;
    public $lastExecuteAction = null;
    public $renderedSuccess = null;
    public $renderedError = null;
    public $renderedHttpStatus = null;

    public function getJson()
    {
        return $this->jsonInput;
    }
    public function adminAction()
    {
        $this->lastExecuteAction = 'execute';
    }
    public function userAction()
    {
        $this->renderError(json_encode(['result' => 'error', 'messages' => 'user 403']), 403);
    }
    public function execute($data, $action = 'execute')
    {
        $this->lastExecuteAction = $action;
        return '{}';
    }
    public function imunifyEmailAction()
    {
        $this->imunifyEmailCalled = true;
    }
    public function renderSuccess($data)
    {
        $this->renderedSuccess = $data;
    }
    public function renderError($data, $http_status = 502)
    {
        $this->renderedError = $data;
        $this->renderedHttpStatus = $http_status;
    }
}

$failures = 0;
$passed = 0;

function assert_eq($expected, $actual, string $msg): void
{
    global $failures, $passed;
    $eq = (json_encode($expected) === json_encode($actual));
    if ($eq) {
        $passed++;
        fwrite(STDOUT, "  ok  {$msg}\n");
    } else {
        $failures++;
        fwrite(STDERR, "  FAIL {$msg}\n");
        fwrite(STDERR, "       expected: " . json_encode($expected) . "\n");
        fwrite(STDERR, "       actual:   " . json_encode($actual) . "\n");
    }
}

function test(string $name, callable $fn): void
{
    fwrite(STDOUT, "\n== {$name}\n");
    $fn();
}

test('commandIE dispatches to imunifyEmailAction', function () {
    $_SERVER['CONTENT_TYPE'] = 'application/json';
    $panel = new TrackingPanel(true);
    $panel->jsonInput = json_encode([
        'command' => 'commandIE',
        'method' => ['accounts', '{account_name}', 'emails'],
        'params' => ['request_method' => 'get'],
    ]);
    (new \Imunify360\Request($panel))->handle();
    assert_eq(true, $panel->imunifyEmailCalled, 'imunifyEmailAction was called');
    assert_eq(null, $panel->lastExecuteAction, 'execute() was NOT used for IE');
    unset($_SERVER['CONTENT_TYPE']);
});

test('commandIE without application/json => 403 (CSRF screen)', function () {
    foreach ([null, 'application/x-www-form-urlencoded', 'text/plain'] as $ct) {
        if ($ct === null) {
            unset($_SERVER['CONTENT_TYPE']);
        } else {
            $_SERVER['CONTENT_TYPE'] = $ct;
        }
        $panel = new TrackingPanel(true);
        $panel->jsonInput = json_encode([
            'command' => 'commandIE',
            'method' => ['accounts', '{account_name}', 'emails'],
            'params' => ['request_method' => 'get'],
        ]);
        (new \Imunify360\Request($panel))->handle();
        $label = var_export($ct, true);
        assert_eq(false, $panel->imunifyEmailCalled, "IE NOT called for CT={$label}");
        assert_eq(403, $panel->renderedHttpStatus, "403 for CT={$label}");
    }
    unset($_SERVER['CONTENT_TYPE']);
});

test('commandIE via form POST => 403 (CSRF screen)', function () {
    $_SERVER['CONTENT_TYPE'] = 'application/x-www-form-urlencoded';
    $_POST = [
        'command' => 'commandIE',
        'method' => ['accounts', '{account_name}', 'emails'],
        'params' => ['request_method' => 'delete'],
    ];
    $panel = new TrackingPanel(true);
    (new \Imunify360\Request($panel))->handle();
    assert_eq(false, $panel->imunifyEmailCalled, 'IE NOT called for form POST');
    assert_eq(403, $panel->renderedHttpStatus, '403 for form POST');
    $_POST = [];
    unset($_SERVER['CONTENT_TYPE']);
});

test('non-IE command in admin role falls back to adminAction', function () {
    $panel = new TrackingPanel(true);
    $panel->jsonInput = json_encode([
        'method' => ['version'],
        'params' => new stdClass(),
    ]);
    (new \Imunify360\Request($panel))->handle();
    assert_eq('execute', $panel->lastExecuteAction, 'adminAction → execute()');
    assert_eq(false, $panel->imunifyEmailCalled, 'imunifyEmailAction was NOT called');
});

test('non-IE command in user role => 403 via userAction', function () {
    $panel = new TrackingPanel(false);
    $panel->jsonInput = json_encode([
        'method' => ['version'],
        'params' => new stdClass(),
    ]);
    (new \Imunify360\Request($panel))->handle();
    assert_eq(403, $panel->renderedHttpStatus, 'user role 403 for non-IE traffic');
    assert_eq(false, $panel->imunifyEmailCalled, 'imunifyEmailAction was NOT called');
});

fwrite(STDOUT, "\n--- {$passed} passed, {$failures} failed ---\n");
exit($failures === 0 ? 0 : 1);
