<?php
// Generic admin/user role split + IE account_name resolution.
//
// Run:
//   php src/asyncclient/ui/agent/plugins/generic/tests/test_role_split.php

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

/**
 * Exposes the protected getImunifyEmailAccountName() so the test can call it
 * without going through the full request pipeline.
 */
class GenericProbe extends \Imunify360\panels\Generic
{
    public function probeAccountName(): string
    {
        return $this->getImunifyEmailAccountName();
    }
}

test('admin role => account_name is root regardless of REMOTE_USER', function () {
    unset($_SERVER['REMOTE_USER']);
    $panel = new GenericProbe(true);
    assert_eq('root', $panel->probeAccountName(), 'admin → root with no REMOTE_USER');

    $_SERVER['REMOTE_USER'] = 'alice';
    $panel = new GenericProbe(true);
    assert_eq('root', $panel->probeAccountName(), 'admin → root even if REMOTE_USER=alice');
    unset($_SERVER['REMOTE_USER']);
});

test('user role => account_name == REMOTE_USER for valid UNIX usernames', function () {
    $_SERVER['REMOTE_USER'] = 'alice';
    $panel = new GenericProbe(false);
    assert_eq('alice', $panel->probeAccountName(), 'user → alice');

    $_SERVER['REMOTE_USER'] = 'site_42';
    $panel = new GenericProbe(false);
    assert_eq('site_42', $panel->probeAccountName(), 'user → site_42 (digits + underscore)');

    $_SERVER['REMOTE_USER'] = 'a-b-c';
    $panel = new GenericProbe(false);
    assert_eq('a-b-c', $panel->probeAccountName(), 'user → a-b-c (hyphens allowed)');
    unset($_SERVER['REMOTE_USER']);
});

test('user role => account_name survives REDIRECT_ prefix on REMOTE_USER', function () {
    unset($_SERVER['REMOTE_USER']);
    $_SERVER['REDIRECT_REMOTE_USER'] = 'alice';
    $panel = new GenericProbe(false);
    assert_eq('alice', $panel->probeAccountName(), 'REDIRECT_REMOTE_USER honoured');

    unset($_SERVER['REDIRECT_REMOTE_USER']);
    $_SERVER['REDIRECT_REDIRECT_REMOTE_USER'] = 'bob';
    $panel = new GenericProbe(false);
    assert_eq('bob', $panel->probeAccountName(), 'double REDIRECT_ honoured');
    unset($_SERVER['REDIRECT_REDIRECT_REMOTE_USER']);
});

test('user role with empty / missing REMOTE_USER => exception', function () {
    foreach ([null, ''] as $val) {
        if ($val === null) {
            unset($_SERVER['REMOTE_USER']);
        } else {
            $_SERVER['REMOTE_USER'] = $val;
        }
        $panel = new GenericProbe(false);
        $threw = false;
        try {
            $panel->probeAccountName();
        } catch (\RuntimeException $e) {
            $threw = true;
        }
        assert_eq(true, $threw, 'user role + REMOTE_USER=' . var_export($val, true) . ' throws');
    }
    unset($_SERVER['REMOTE_USER']);
});

test('user role with malicious REMOTE_USER => exception (anti-injection)', function () {
    $bad = [
        'alice/../root',     // path traversal
        '../etc/passwd',     // path traversal
        'alice;rm -rf /',    // shell metacharacters
        'alice ',            // trailing whitespace
        ' alice',            // leading whitespace
        'a' . str_repeat('x', 64), // too long
        "alice\nbob",        // CRLF
        "alice\n",           // trailing newline
        'root',              // user trying to claim root
        'ROOT',              // case variant
    ];
    foreach ($bad as $val) {
        $_SERVER['REMOTE_USER'] = $val;
        $panel = new GenericProbe(false);
        $threw = false;
        try {
            $panel->probeAccountName();
        } catch (\RuntimeException $e) {
            $threw = true;
        }
        assert_eq(true, $threw, 'user role + REMOTE_USER=' . var_export($val, true) . ' throws');
    }
    unset($_SERVER['REMOTE_USER']);
});

test('user role => REMOTE_USER length and first-character boundaries', function () {
    $ok = ['a', '_x', str_repeat('a', 32), 'a' . str_repeat('b', 31)];
    foreach ($ok as $val) {
        $_SERVER['REMOTE_USER'] = $val;
        $panel = new GenericProbe(false);
        assert_eq($val, $panel->probeAccountName(), 'accepted: ' . var_export($val, true));
    }

    $bad = [
        str_repeat('a', 33),  // one over the 32-char limit
        '1alice',             // digit first
        '-alice',             // hyphen first
        'Alice',              // uppercase first
        'alICE',              // uppercase in tail
        "alice\0",            // NUL terminator
    ];
    foreach ($bad as $val) {
        $_SERVER['REMOTE_USER'] = $val;
        $panel = new GenericProbe(false);
        $threw = false;
        try {
            $panel->probeAccountName();
        } catch (\RuntimeException $e) {
            $threw = true;
        }
        assert_eq(true, $threw, 'rejected: ' . var_export($val, true));
    }
    unset($_SERVER['REMOTE_USER']);
});

test('SPA role: admin realm => admin, user realm => client', function () {
    assert_eq(
        'admin',
        (new \Imunify360\panels\Generic(true))->getSpaRole(),
        'admin realm => SPA role admin'
    );
    // The bundled SPA only models admin/client; the user realm must map onto
    // client so the navbar (and the ImunifyEmail tab) renders for mailbox owners.
    assert_eq(
        'client',
        (new \Imunify360\panels\Generic(false))->getSpaRole(),
        'user realm => SPA role client'
    );
});

test('resolveIsAdmin: explicit role values', function () {
    assert_eq(true, \Imunify360\panels\Generic::resolveIsAdmin(['IMUNIFY360_ROLE' => 'admin']), 'admin => admin');
    assert_eq(false, \Imunify360\panels\Generic::resolveIsAdmin(['IMUNIFY360_ROLE' => 'user']), 'user => not admin');
});

test('resolveRoleName: reports the declared role, empty when nothing is set', function () {
    $r = ['\Imunify360\panels\Generic', 'resolveRoleName'];
    assert_eq('admin', call_user_func($r, ['IMUNIFY360_ROLE' => 'admin']), 'plain admin');
    assert_eq('user', call_user_func($r, ['IMUNIFY360_ROLE' => 'user']), 'plain user');
    assert_eq('user', call_user_func($r, ['REDIRECT_IMUNIFY360_ROLE' => 'user']), 'REDIRECT_ chain');
    assert_eq('', call_user_func($r, []), 'absent => empty');
    assert_eq('', call_user_func($r, ['IMUNIFY360_ROLE' => '']), 'empty => empty');
});

test('an undeclared role must not be reported as a role, yet still authorise as admin', function () {
    // The SPA takes a present i360role over the JWT, so index.php may only
    // emit it when the web server actually declared one. The authorisation
    // fail-safe below is deliberately unaffected.
    assert_eq('', \Imunify360\panels\Generic::resolveRoleName([]), 'nothing declared => no role to emit');
    assert_eq(true, \Imunify360\panels\Generic::resolveIsAdmin([]), 'nothing declared => still admin server-side');
});

test('resolveIsAdmin: absent role keeps historical admin default', function () {
    assert_eq(true, \Imunify360\panels\Generic::resolveIsAdmin([]), 'absent => admin');
    assert_eq(true, \Imunify360\panels\Generic::resolveIsAdmin(['IMUNIFY360_ROLE' => '']), 'empty => admin');
});

test('resolveIsAdmin: user survives REDIRECT_ prefix chain (no escalation)', function () {
    assert_eq(false, \Imunify360\panels\Generic::resolveIsAdmin(['REDIRECT_IMUNIFY360_ROLE' => 'user']), 'REDIRECT_ user => not admin');
    assert_eq(false, \Imunify360\panels\Generic::resolveIsAdmin(['REDIRECT_REDIRECT_IMUNIFY360_ROLE' => 'user']), 'double REDIRECT_ user => not admin');
});

test('resolveIsAdmin: unknown role is not admin (fail-closed)', function () {
    assert_eq(false, \Imunify360\panels\Generic::resolveIsAdmin(['IMUNIFY360_ROLE' => 'superuser']), 'unknown => not admin');
    assert_eq(false, \Imunify360\panels\Generic::resolveIsAdmin(['REDIRECT_IMUNIFY360_ROLE' => 'root']), 'unknown REDIRECT_ => not admin');
});

test('resolveIsAdmin: plain var wins over REDIRECT_ variant', function () {
    assert_eq(false, \Imunify360\panels\Generic::resolveIsAdmin([
        'IMUNIFY360_ROLE' => 'user',
        'REDIRECT_IMUNIFY360_ROLE' => 'admin',
    ]), 'plain user beats REDIRECT_ admin');
});

test('resolveRemoteUser: plain, REDIRECT_ chain, precedence, absent', function () {
    $r = ['\Imunify360\panels\Generic', 'resolveRemoteUser'];
    assert_eq('alice', call_user_func($r, ['REMOTE_USER' => 'alice']), 'plain');
    assert_eq('alice', call_user_func($r, ['REDIRECT_REMOTE_USER' => 'alice']), 'REDIRECT_');
    assert_eq('alice', call_user_func($r, ['REDIRECT_REDIRECT_REMOTE_USER' => 'alice']), 'double REDIRECT_');
    assert_eq('alice', call_user_func($r, [
        'REMOTE_USER' => 'alice',
        'REDIRECT_REMOTE_USER' => 'bob',
    ]), 'plain wins over REDIRECT_');
    assert_eq('', call_user_func($r, []), 'absent => empty');
    assert_eq('', call_user_func($r, ['REMOTE_USER' => '']), 'empty plain falls through to empty');
});

test('serverVarThroughRedirects: innermost (fewest REDIRECT_) wins, order-independent', function () {
    $r = ['\Imunify360\panels\Generic', 'resolveRemoteUser'];
    // Chained redirects can leave several REDIRECT_ depths with different
    // values; the least-prefixed (most recent) must win regardless of the
    // $_SERVER iteration order.
    assert_eq('alice', call_user_func($r, [
        'REDIRECT_REDIRECT_REMOTE_USER' => 'stale-outer',
        'REDIRECT_REMOTE_USER' => 'alice',
    ]), 'inner wins when outer is listed first');
    assert_eq('alice', call_user_func($r, [
        'REDIRECT_REMOTE_USER' => 'alice',
        'REDIRECT_REDIRECT_REMOTE_USER' => 'stale-outer',
    ]), 'inner wins when outer is listed last');
});

test('serverVarThroughRedirects: bare REDIRECT_ key is not a match', function () {
    $r = ['\Imunify360\panels\Generic', 'resolveRemoteUser'];
    // Stripping the prefix off a key that is nothing but the prefix runs
    // substr() to the end of the string, which yields false below PHP 7 and
    // '' from PHP 7 on; the cast in the caller has to make both agree.
    assert_eq('', call_user_func($r, ['REDIRECT_' => 'junk']), 'bare REDIRECT_ ignored');
    assert_eq('alice', call_user_func($r, [
        'REDIRECT_' => 'junk',
        'REDIRECT_REMOTE_USER' => 'alice',
    ]), 'bare REDIRECT_ does not shadow a real match');
});

test('resolveIsAdmin: innermost redirect value wins (no stale-outer escalation)', function () {
    assert_eq(false, \Imunify360\panels\Generic::resolveIsAdmin([
        'REDIRECT_REDIRECT_IMUNIFY360_ROLE' => 'admin',
        'REDIRECT_IMUNIFY360_ROLE' => 'user',
    ]), 'inner user beats stale outer admin');
    assert_eq(true, \Imunify360\panels\Generic::resolveIsAdmin([
        'REDIRECT_REDIRECT_IMUNIFY360_ROLE' => 'user',
        'REDIRECT_IMUNIFY360_ROLE' => 'admin',
    ]), 'inner admin beats outer user');
});

fwrite(STDOUT, "\n--- {$passed} passed, {$failures} failed ---\n");
exit($failures === 0 ? 0 : 1);
