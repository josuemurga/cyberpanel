<?php
// Defence-in-depth whitelist of IE-quarantine paths for user-role
// requests on the plugin side, before the request reaches IE. IE-quarantine
// also enforces scope isolation (isPermit) — this is the second
// line of defence.
//
// Run:
//   php src/asyncclient/ui/agent/plugins/generic/tests/test_user_method_whitelist.php

declare(strict_types=1);

require_once __DIR__ . '/../../common/classes/autoloader.php';

$loader = new Imunify360Psr4Autoloader();
$loader->addNamespace('Imunify360', __DIR__ . '/../../common/classes');
$loader->addNamespace('Imunify360', __DIR__ . '/../classes');

$_SERVER['REMOTE_ADDR'] = '203.0.113.7';
$_POST = [];

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

class MockImunifyEmailClient extends \Imunify360\ImunifyEmailClient
{
    public $lastCall = null;
    public function __construct()
    {
        // Bypass parent — we don't want to read a real secret in tests.
    }
    public function call($accountName, $role, array $command, $httpMethod, array $params, $body = null)
    {
        $this->lastCall = [
            'accountName' => $accountName,
            'role' => $role,
            'command' => $command,
            'httpMethod' => $httpMethod,
            'params' => $params,
            'body' => $body,
        ];
        return ['http_status' => 200, 'body' => '{"items":[]}'];
    }
}

class HarnessPanel extends \Imunify360\panels\Generic
{
    public $mockClient;
    public $renderedSuccess = null;
    public $renderedError = null;
    public $renderedHttpStatus = null;

    protected function getImunifyEmailClient()
    {
        return $this->mockClient;
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

function build_panel(bool $isAdmin, ?string $remoteUser): HarnessPanel
{
    if ($remoteUser === null) {
        unset($_SERVER['REMOTE_USER']);
    } else {
        $_SERVER['REMOTE_USER'] = $remoteUser;
    }
    $panel = new HarnessPanel($isAdmin);
    $panel->mockClient = new MockImunifyEmailClient();
    return $panel;
}

function run_ie_request(HarnessPanel $panel, array $method_path, array $params): void
{
    $panel->jsonInput = json_encode([
        'command' => 'commandIE',
        'method' => $method_path,
        'params' => $params,
    ]);
    $panel->request = (object) json_decode($panel->jsonInput);
    $panel->imunifyEmailAction();
}

test('admin can hit any IE path', function () {
    foreach ([
        ['accounts', '{account_name}', 'emails'],
        ['users'],
        ['admin', 'config'],
        ['verilock'],
    ] as $path) {
        $panel = build_panel(true, null);
        run_ie_request($panel, $path, ['request_method' => 'get']);
        assert_eq(false, $panel->mockClient->lastCall === null, 'admin → ' . implode('/', $path) . ' was sent');
        assert_eq('admin', $panel->mockClient->lastCall['role'], 'role=admin');
        assert_eq('root', $panel->mockClient->lastCall['accountName'], 'accountName=root');
    }
});

test('user can hit accounts/{account_name}/* paths only', function () {
    foreach ([
        ['accounts', '{account_name}', 'emails'],
        ['accounts', '{account_name}', 'emails', '42', 'release'],
        ['accounts', '{account_name}', 'verilock'],
    ] as $path) {
        $panel = build_panel(false, 'alice');
        run_ie_request($panel, $path, ['request_method' => 'get']);
        assert_eq(false, $panel->mockClient->lastCall === null, 'user → ' . implode('/', $path) . ' was sent');
        assert_eq('user', $panel->mockClient->lastCall['role'], 'role=user');
        assert_eq('alice', $panel->mockClient->lastCall['accountName'], 'accountName=alice');
    }
});

test('user cannot hit admin-only IE paths => 403, no IE call', function () {
    foreach ([
        ['users'],
        ['admin', 'config'],
        ['verilock'],                              // top-level, not under accounts/*
        ['accounts'],                              // listing all accounts
        ['accounts', 'bob', 'emails'],             // literal other-user (no placeholder)
        ['emails'],                                // not under accounts/*
    ] as $path) {
        $panel = build_panel(false, 'alice');
        run_ie_request($panel, $path, ['request_method' => 'get']);
        assert_eq(null, $panel->mockClient->lastCall, 'user → ' . implode('/', $path) . ' was NOT sent');
        assert_eq(403, $panel->renderedHttpStatus, '403 returned');
    }
});

test('user with missing REMOTE_USER => error, no IE call', function () {
    $panel = build_panel(false, null);
    run_ie_request($panel, ['accounts', '{account_name}', 'emails'], ['request_method' => 'get']);
    assert_eq(null, $panel->mockClient->lastCall, 'no IE call when REMOTE_USER missing');
    assert_eq(false, $panel->renderedError === null, 'error rendered');
});

test('client cannot override account_name via params (server forces it)', function () {
    $panel = build_panel(false, 'alice');
    run_ie_request(
        $panel,
        ['accounts', '{account_name}', 'emails'],
        ['request_method' => 'get', 'account_name' => 'bob', 'username' => 'bob']
    );
    assert_eq('alice', $panel->mockClient->lastCall['accountName'], 'accountName forced to alice');
    assert_eq('user', $panel->mockClient->lastCall['role'], 'role=user (cannot be elevated)');
});

// BugBot Medium (7bd8be20): request_method is the SPA-side routing meta-
// field; it must not be forwarded to IE in the query/body, where it is
// an unknown field that may trigger validation errors.
test('request_method is consumed locally and stripped from params before IE call', function () {
    foreach ([
        ['request_method' => 'get'],
        ['request_method' => 'POST', 'limit' => 25],
        ['limit' => 25, 'request_method' => 'PATCH', 'sort' => 'desc'],
    ] as $clientParams) {
        $panel = build_panel(true, null);
        run_ie_request($panel, ['accounts', '{account_name}', 'emails'], $clientParams);
        $sentParams = $panel->mockClient->lastCall['params'];
        assert_eq(false, array_key_exists('request_method', $sentParams),
            'request_method stripped from params: ' . json_encode($clientParams));
        // Other params survive untouched.
        foreach ($clientParams as $k => $v) {
            if ($k === 'request_method') continue;
            assert_eq($v, $sentParams[$k] ?? null,
                "param $k preserved: " . json_encode($clientParams));
        }
        // HTTP method propagated correctly to the call.
        $expected = strtoupper($clientParams['request_method']);
        assert_eq($expected, strtoupper($panel->mockClient->lastCall['httpMethod']),
            "httpMethod=$expected on the call");
    }
});

// Path-traversal / framing-break attempts in tail segments. The user-role
// whitelist only inspects the first two segments, so the rest is the
// IE-client's responsibility — but in user role we still want to fail
// at the whitelist (403, no IE call) rather than pass through to the
// 400-validation downstream.
test('user role: tail segments with .. / / control chars => 403 at whitelist', function () {
    foreach ([
        ['accounts', '{account_name}', '..'],
        ['accounts', '{account_name}', '..', 'users'],
        ['accounts', '{account_name}', 'a/b'],
        ['accounts', '{account_name}', "a\nb"],
        ['accounts', '{account_name}', 'a b'],
        ['accounts', '{account_name}', '?foo=bar'],
        ['accounts', '{account_name}', ''],
    ] as $path) {
        $panel = build_panel(false, 'alice');
        run_ie_request($panel, $path, ['request_method' => 'get']);
        assert_eq(null, $panel->mockClient->lastCall, 'no IE call for tail-segment ' . json_encode($path));
        assert_eq(403, $panel->renderedHttpStatus, '403 for tail-segment ' . json_encode($path));
    }
});

// Admin can hit arbitrary path-segments (no user-role whitelist gating),
// but the IE-client must still reject path-traversal / framing-break
// segments — return 400, not 502 (502 is reserved for transport failures).
test('admin role: invalid tail segment => 400 from client validation, no IE call', function () {
    foreach ([
        ['accounts', '{account_name}', '..'],
        ['accounts', '{account_name}', 'a/b'],
        ['accounts', '{account_name}', "a\nb"],
        ['users', '..'],
    ] as $path) {
        $panel = build_panel(true, null);
        // The base client must be installed (not the mock), so wire a
        // bypass: real client with a non-existent secret path raises
        // RuntimeException on JWT mint — to keep this test focused on
        // segment validation, use a mock subclass that delegates to real
        // buildUrl but never touches the network.
        $panel->mockClient = new class extends MockImunifyEmailClient {
            public function __construct() {}
            public function call($accountName, $role, array $command, $httpMethod, array $params, $body = null) {
                $this->buildUrl($command, $accountName);
                return parent::call($accountName, $role, $command, $httpMethod, $params, $body);
            }
        };
        run_ie_request($panel, $path, ['request_method' => 'get']);
        assert_eq(null, $panel->mockClient->lastCall, 'no IE call for ' . json_encode($path));
        assert_eq(400, $panel->renderedHttpStatus, '400 from client for ' . json_encode($path));
    }
});

// BugBot Medium (740ac3e4): DirectAdmin::renderError used to ignore the
// $http_status arg and only checked `error` key, so error envelopes from
// imunifyEmailAction (`{result:'error', http_status:403}`) silently fell
// through into renderSuccess → SPA saw 200 OK for IE rejections.
test('DirectAdmin::renderError signature accepts $http_status', function () {
    $r = new \ReflectionMethod(\Imunify360\panels\DirectAdmin::class, 'renderError');
    assert_eq(2, $r->getNumberOfParameters(), 'renderError takes 2 parameters');
    $params = $r->getParameters();
    assert_eq('http_status', $params[1]->getName(), 'second param is http_status');
    assert_eq(true, $params[1]->isOptional(), 'http_status is optional');
    assert_eq(502, $params[1]->getDefaultValue(), 'default http_status is 502 (legacy)');
});

test('DirectAdmin recognises imunifyEmailAction error envelopes via dataHasError', function () {
    $da = new \Imunify360\panels\DirectAdmin(true);
    $errorEnvelopes = [
        json_encode(['result' => 'error', 'messages' => 'forbidden', 'http_status' => 403, 'data' => []]),
        json_encode(['result' => 'error', 'http_status' => 502]),
        // Legacy error format used by other DA actions:
        json_encode(['error' => 'boom']),
    ];
    foreach ($errorEnvelopes as $e) {
        assert_eq(true, $da->dataHasError($e), 'detected as error: ' . $e);
    }

    $successEnvelopes = [
        json_encode(['result' => 'success', 'http_status' => 201, 'data' => ['items' => []]]),
        json_encode(['data' => ['items' => []]]),
        json_encode(['items' => []]),
    ];
    foreach ($successEnvelopes as $e) {
        assert_eq(false, $da->dataHasError($e), 'not detected as error: ' . $e);
    }
});

// BugBot Medium: buildImunifyEmailEnvelope used strict $status === 200
// and so produced result:'error' for legitimate 2xx responses (201, 204).
// renderSuccess saw the envelope error flag and re-routed through
// renderError() WITHOUT the http_status arg → default 502 reached the SPA.
// Fix: any status < 400 is success. Lock it down with a regression test.
test('non-200 2xx IE responses still come back as success envelopes', function () {
    foreach ([200, 201, 204] as $code) {
        $panel = build_panel(true, null);
        $panel->mockClient = new class($code) extends MockImunifyEmailClient {
            private $code;
            public function __construct($code) { $this->code = $code; }
            public function call($accountName, $role, array $command, $httpMethod, array $params, $body = null) {
                $this->lastCall = compact('accountName','role','command','httpMethod','params','body');
                return ['http_status' => $this->code, 'body' => ''];
            }
        };
        run_ie_request($panel, ['accounts', '{account_name}', 'emails'], ['request_method' => 'get']);
        assert_eq(null, $panel->renderedError, "no error rendered for status $code");
        $env = json_decode($panel->renderedSuccess, true);
        assert_eq('success', $env['result'] ?? null, "envelope result=success for status $code");
        assert_eq($code, $env['http_status'] ?? null, "envelope http_status=$code");
    }
});

test('4xx/5xx IE responses come back as error envelopes with the same status', function () {
    foreach ([400, 401, 403, 404, 500, 502, 504] as $code) {
        $panel = build_panel(true, null);
        $panel->mockClient = new class($code) extends MockImunifyEmailClient {
            private $code;
            public function __construct($code) { $this->code = $code; }
            public function call($accountName, $role, array $command, $httpMethod, array $params, $body = null) {
                $this->lastCall = compact('accountName','role','command','httpMethod','params','body');
                return ['http_status' => $this->code, 'body' => '{"error":"upstream"}'];
            }
        };
        run_ie_request($panel, ['accounts', '{account_name}', 'emails'], ['request_method' => 'get']);
        assert_eq($code, $panel->renderedHttpStatus, "renderError used IE status $code, not default 502");
        $env = json_decode($panel->renderedError, true);
        assert_eq('error', $env['result'] ?? null, "envelope result=error for status $code");
        assert_eq($code, $env['http_status'] ?? null, "envelope http_status=$code");
    }
});

// 207 Multi-Status is a partial bulk release/delete failure: a 2xx code that
// must be surfaced as an error (not a success), with its real status.
test('207 Multi-Status => error envelope with status 207, never success', function () {
    $panel = build_panel(true, null);
    $panel->mockClient = new class extends MockImunifyEmailClient {
        public function __construct() {}
        public function call($accountName, $role, array $command, $httpMethod, array $params, $body = null) {
            $this->lastCall = compact('accountName', 'role', 'command', 'httpMethod', 'params', 'body');
            return ['http_status' => 207, 'body' => '{"items":[]}'];
        }
    };
    run_ie_request($panel, ['accounts', '{account_name}', 'emails'], ['request_method' => 'post']);
    assert_eq(null, $panel->renderedSuccess, '207 not rendered as success');
    assert_eq(207, $panel->renderedHttpStatus, 'renderError used status 207');
    $env = json_decode($panel->renderedError, true);
    assert_eq('error', $env['result'] ?? null, '207 => result=error');
    assert_eq(207, $env['http_status'] ?? null, 'envelope http_status=207');
});

// HTTP method whitelist. CRLF injection in request_method is the
// classic exploit — the client must reject anything outside
// {GET,POST,PATCH,PUT,DELETE}.
test('admin role: bogus HTTP method => 400 from client validation', function () {
    foreach ([
        'UNKNOWN',
        'GET /etc/passwd HTTP/1.1',
        "GET\r\nX-Injected:",
        '',
        'GET POST',
    ] as $method) {
        $panel = build_panel(true, null);
        $panel->mockClient = new class extends MockImunifyEmailClient {
            public function __construct() {}
            public function call($accountName, $role, array $command, $httpMethod, array $params, $body = null) {
                // Mirror the real method-whitelist check before recording.
                $upper = strtoupper((string) $httpMethod);
                if (!in_array($upper, \Imunify360\ImunifyEmailClient::HTTP_METHODS_ALLOWED, true)) {
                    throw new \InvalidArgumentException("bad method: $httpMethod");
                }
                return parent::call($accountName, $role, $command, $httpMethod, $params, $body);
            }
        };
        run_ie_request(
            $panel,
            ['accounts', '{account_name}', 'emails'],
            ['request_method' => $method]
        );
        assert_eq(null, $panel->mockClient->lastCall, 'no IE call for method ' . json_encode($method));
        assert_eq(400, $panel->renderedHttpStatus, '400 for method ' . json_encode($method));
    }
});

// BugBot HIGH: Plesk(false) / DirectAdmin(false) inherit AbstractPanel
// without overriding getImunifyEmailAccountName. Default base must
// fail-closed in user role so we don't end up minting JWTs with
// sub=root, role=user from those panels.
class BasePanelHarness extends \Imunify360\panels\AbstractPanel
{
    public $mockClient;
    public $jsonInput = '';
    public $renderedHttpStatus = null;
    public $renderedError = null;
    public $renderedSuccess = null;

    public function getJson() { return $this->jsonInput; }
    public function adminAction() {}
    public function userAction() {}
    public function execute($data, $action = 'execute') { return ''; }
    protected function getImunifyEmailClient() { return $this->mockClient; }
    public function renderError($data, $http_status = 502)
    {
        $this->renderedError = $data;
        $this->renderedHttpStatus = $http_status;
    }
    public function renderSuccess($data)
    {
        $this->renderedSuccess = $data;
    }
}

test('non-generic panel in user role rejects IE without ever calling IE', function () {
    $panel = new BasePanelHarness(false);
    $panel->mockClient = new MockImunifyEmailClient();
    $panel->jsonInput = json_encode([
        'command' => 'commandIE',
        'method' => ['accounts', '{account_name}', 'emails'],
        'params' => ['request_method' => 'get'],
    ]);
    $panel->request = (object) json_decode($panel->jsonInput);
    $panel->imunifyEmailAction();
    assert_eq(null, $panel->mockClient->lastCall, 'IE was NOT called');
    assert_eq(403, $panel->renderedHttpStatus, '403 returned at entry point');
});

test('non-generic panel in admin role still works through base default', function () {
    $panel = new BasePanelHarness(true);
    $panel->mockClient = new MockImunifyEmailClient();
    $panel->jsonInput = json_encode([
        'command' => 'commandIE',
        'method' => ['accounts', '{account_name}', 'emails'],
        'params' => ['request_method' => 'get'],
    ]);
    $panel->request = (object) json_decode($panel->jsonInput);
    $panel->imunifyEmailAction();
    assert_eq(false, $panel->mockClient->lastCall === null, 'admin path still works');
    assert_eq('root', $panel->mockClient->lastCall['accountName'], 'accountName=root (base default)');
    assert_eq('admin', $panel->mockClient->lastCall['role'], 'role=admin');
});

fwrite(STDOUT, "\n--- {$passed} passed, {$failures} failed ---\n");
exit($failures === 0 ? 0 : 1);
