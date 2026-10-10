<?php
// ImunifyEmailClient — HS256 JWT minter and URL builder.
//
// Run:
//   php src/asyncclient/ui/agent/plugins/generic/tests/test_imunifyemail_client.php

declare(strict_types=1);

require_once __DIR__ . '/../../common/classes/autoloader.php';

$loader = new Imunify360Psr4Autoloader();
$loader->addNamespace('Imunify360', __DIR__ . '/../../common/classes');
$loader->addNamespace('Imunify360', __DIR__ . '/../classes');

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

function b64url_decode(string $s): string
{
    return base64_decode(strtr($s, '-_', '+/')
        . str_repeat('=', (4 - strlen($s) % 4) % 4));
}

function write_secret(string $value): string
{
    $path = tempnam(sys_get_temp_dir(), 'iejwt');
    file_put_contents($path, $value);
    chmod($path, 0600);
    return $path;
}

const TEST_SECRET = 'super-secret-key-for-unit-tests-only';

test('mintJwt emits a well-formed HS256 token with sub/role/iat/exp', function () {
    $secret_path = write_secret(TEST_SECRET);
    $client = new \Imunify360\ImunifyEmailClient($secret_path);
    $before = time();
    $jwt = $client->mintJwt('alice', 'user');
    $after = time();
    unlink($secret_path);

    $parts = explode('.', $jwt);
    assert_eq(3, count($parts), 'JWT has three dot-separated segments');

    $header = json_decode(b64url_decode($parts[0]), true);
    assert_eq('HS256', $header['alg'] ?? null, 'alg = HS256');
    assert_eq('JWT', $header['typ'] ?? null, 'typ = JWT');

    $payload = json_decode(b64url_decode($parts[1]), true);
    assert_eq('alice', $payload['sub'] ?? null, 'sub = alice');
    assert_eq('user', $payload['role'] ?? null, 'role = user');
    global $passed, $failures;
    if (isset($payload['iat']) && $payload['iat'] >= $before && $payload['iat'] <= $after) {
        $passed++;
        fwrite(STDOUT, "  ok  iat is current time\n");
    } else {
        $failures++;
        fwrite(STDERR, "  FAIL iat is current time (got " . var_export($payload['iat'] ?? null, true) . ", expected $before..$after)\n");
    }
    if (isset($payload['exp']) && $payload['exp'] > $payload['iat'] && $payload['exp'] <= $payload['iat'] + 600) {
        $passed++;
        fwrite(STDOUT, "  ok  exp is in the near future (<= 10 min)\n");
    } else {
        $failures++;
        fwrite(STDERR, "  FAIL exp is in the near future (got " . var_export($payload['exp'] ?? null, true) . ")\n");
    }

    $expected_sig = hash_hmac('sha256', $parts[0] . '.' . $parts[1], TEST_SECRET, true);
    $actual_sig = b64url_decode($parts[2]);
    assert_eq($expected_sig, $actual_sig, 'HMAC signature matches');
});

test('mintJwt with role=admin uses sub=root', function () {
    $secret_path = write_secret(TEST_SECRET);
    $client = new \Imunify360\ImunifyEmailClient($secret_path);
    $jwt = $client->mintJwt('root', 'admin');
    unlink($secret_path);

    $parts = explode('.', $jwt);
    $payload = json_decode(b64url_decode($parts[1]), true);
    assert_eq('root', $payload['sub'] ?? null, 'sub = root');
    assert_eq('admin', $payload['role'] ?? null, 'role = admin');
});

test('mintJwt rejects unknown role values', function () {
    $secret_path = write_secret(TEST_SECRET);
    $client = new \Imunify360\ImunifyEmailClient($secret_path);
    $threw = false;
    try {
        $client->mintJwt('alice', 'superadmin');
    } catch (\InvalidArgumentException $e) {
        $threw = true;
    }
    unlink($secret_path);
    assert_eq(true, $threw, 'unknown role throws InvalidArgumentException');
});

test('mintJwt fails when the secret file is missing or empty', function () {
    $missing = '/tmp/definitely-not-here-' . uniqid();
    $client = new \Imunify360\ImunifyEmailClient($missing);
    $threw = false;
    try {
        $client->mintJwt('alice', 'user');
    } catch (\RuntimeException $e) {
        $threw = true;
    }
    assert_eq(true, $threw, 'missing secret file throws RuntimeException');

    $empty = write_secret('');
    $client = new \Imunify360\ImunifyEmailClient($empty);
    $threw = false;
    try {
        $client->mintJwt('alice', 'user');
    } catch (\RuntimeException $e) {
        $threw = true;
    }
    unlink($empty);
    assert_eq(true, $threw, 'empty secret file throws RuntimeException');
});

test('buildUrl substitutes {account_name} and url-encodes it', function () {
    $secret_path = write_secret(TEST_SECRET);
    $client = new \Imunify360\ImunifyEmailClient($secret_path);
    unlink($secret_path);

    assert_eq(
        '/quarantine/api/v1/accounts/alice/emails',
        $client->buildUrl(['accounts', '{account_name}', 'emails'], 'alice'),
        'plain substitution'
    );
    assert_eq(
        '/quarantine/api/v1/accounts/root/emails/42',
        $client->buildUrl(['accounts', '{account_name}', 'emails', '42'], 'root'),
        'preserves trailing segments'
    );
    // No placeholder: leave path intact (admin-only paths without {account_name}).
    assert_eq(
        '/quarantine/api/v1/users',
        $client->buildUrl(['users'], 'root'),
        'no placeholder = no substitution'
    );
});

test('buildUrl rejects framing-break / path-traversal segments', function () {
    $secret_path = write_secret(TEST_SECRET);
    $client = new \Imunify360\ImunifyEmailClient($secret_path);
    unlink($secret_path);

    $bad = [
        [['..'], 'alice'],
        [['accounts', '{account_name}', '..'], 'alice'],
        [['accounts', '{account_name}', 'a/b'], 'alice'],
        [['accounts', '{account_name}', "a\nb"], 'alice'],
        [['accounts', '{account_name}', "emails\n"], 'alice'],
        [['accounts', '{account_name}', 'a b'], 'alice'],
        [['accounts', '{account_name}', '?foo'], 'alice'],
        [['accounts', '{account_name}', ''], 'alice'],
        [[], 'alice'],                                  // empty command
        [['accounts'], 'a/b'],                          // bad accountName
        [['accounts'], "alice\n"],                      // trailing newline
        [['accounts'], '..'],                           // bad accountName
        [['accounts'], ''],                             // empty accountName
    ];
    foreach ($bad as list($command, $accountName)) {
        $threw = false;
        try {
            $client->buildUrl($command, $accountName);
        } catch (\InvalidArgumentException $e) {
            $threw = true;
        }
        assert_eq(true, $threw,
            'rejects command=' . json_encode($command)
            . ' accountName=' . json_encode($accountName));
    }
});

test('buildQueryDoseq mirrors Python urlencode(doseq=True)', function () {
    $m = new \ReflectionMethod(\Imunify360\ImunifyEmailClient::class, 'buildQueryDoseq');
    $m->setAccessible(true);

    // List values: `k=v1&k=v2`, NOT PHP's default `k[0]=v1&k[1]=v2`.
    assert_eq(
        'ids=1&ids=2&ids=3',
        $m->invoke(null, ['ids' => [1, 2, 3]]),
        'list-valued param uses repeated key'
    );

    // Mixed scalar + list, order preserved.
    assert_eq(
        'limit=25&ids=1&ids=2&sort=desc',
        $m->invoke(null, ['limit' => 25, 'ids' => [1, 2], 'sort' => 'desc']),
        'scalar + list combined'
    );

    // Empty arrays produce nothing for that key.
    assert_eq(
        'limit=25',
        $m->invoke(null, ['limit' => 25, 'ids' => []]),
        'empty list omits the key'
    );

    // Booleans serialise as 1/0 (matches urlencode bool fallback).
    assert_eq('flag=1&off=0', $m->invoke(null, ['flag' => true, 'off' => false]),
        'booleans 1/0');

    // null serialises as empty value, not as the literal "null".
    assert_eq('x=', $m->invoke(null, ['x' => null]), 'null is empty');

    // RFC 3986-style %-encoding of value characters.
    assert_eq('q=a%20b%26c', $m->invoke(null, ['q' => 'a b&c']), 'spaces and & encoded');

    // Make sure we are NOT using PHP's default http_build_query bracket form.
    $out = $m->invoke(null, ['items' => ['a', 'b']]);
    assert_eq(false, strpos($out, '%5B') !== false,
        'no `[` in encoded output (would be %5B)');
    assert_eq(false, strpos($out, '[') !== false, 'no literal `[` in output');
});

test('encodeBody emits a JSON object, empty params => {} not []', function () {
    $m = new \ReflectionMethod(\Imunify360\ImunifyEmailClient::class, 'encodeBody');
    $m->setAccessible(true);

    // Empty params must be {}, matching execute.py's json.dumps({}); [] would
    // fail decoding on the IE side where an object is expected.
    assert_eq('{}', $m->invoke(null, []), 'empty params => {}');
    assert_eq('{"limit":25}', $m->invoke(null, ['limit' => 25]), 'scalar => object');
    assert_eq('{"ids":[1,2]}', $m->invoke(null, ['ids' => [1, 2]]), 'nested list stays an array');
});

test('HTTP_METHODS_ALLOWED constant contains exactly the safe verbs', function () {
    $expected = ['GET', 'POST', 'PATCH', 'PUT', 'DELETE'];
    sort($expected);
    $actual = \Imunify360\ImunifyEmailClient::HTTP_METHODS_ALLOWED;
    sort($actual);
    assert_eq($expected, $actual, 'whitelist exactly matches expected verbs');
});

fwrite(STDOUT, "\n--- {$passed} passed, {$failures} failed ---\n");
exit($failures === 0 ? 0 : 1);
