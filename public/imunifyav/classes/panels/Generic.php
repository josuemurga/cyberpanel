<?php

namespace Imunify360\panels;


class Generic extends AbstractPanel {

    // Keep this class PCRE-free. init.php resolves the role on every request,
    // and where PHP may not allocate executable memory the first pattern
    // compile raises an E_WARNING that PHP-FPM writes into the response body,
    // corrupting the SPA shell and every application/json reply alike.

    // Linux usernames: must start with [a-z_], followed by up to 31 chars of
    // [a-z0-9_-]. Matches the POSIX-portable subset used by NSS_NAME_REGEX
    // on RHEL and adduser(8) on Debian. Intentionally narrower than what
    // some panels allow (e.g. uppercase) — we own the security boundary on
    // this side and want to reject anything we cannot trivially validate.
    const REMOTE_USER_MAX_LEN = 32;
    const REMOTE_USER_HEAD_CHARS = 'abcdefghijklmnopqrstuvwxyz_';
    const REMOTE_USER_TAIL_CHARS = 'abcdefghijklmnopqrstuvwxyz0123456789_-';

    /**
     * Resolve isAdmin from the web-server environment.
     *
     * An internal Apache redirect renames SetEnv vars with a REDIRECT_
     * prefix (chained per hop), so a user-realm assignment can arrive as
     * REDIRECT_IMUNIFY360_ROLE while IMUNIFY360_ROLE is unset. Reading only
     * the plain name would lose it and fall through to the admin default,
     * escalating a user request. Walk the prefix chain and treat admin as
     * opt-in: only an explicit 'admin' is privileged, any other present
     * value pins the least-privileged user role. A genuinely absent value
     * keeps the historical admin-only default.
     */
    public static function resolveIsAdmin(array $server)
    {
        $role = self::resolveRoleName($server);
        return ($role === '') ? true : ($role === 'admin');
    }

    /**
     * The role as declared by the web server, '' when nothing was declared.
     * Lets callers tell "declared admin/user" apart from "not configured",
     * which resolveIsAdmin() deliberately collapses into its admin default.
     */
    public static function resolveRoleName(array $server)
    {
        return self::serverVarThroughRedirects($server, 'IMUNIFY360_ROLE');
    }

    /**
     * Resolve REMOTE_USER honouring the same REDIRECT_ prefix chain as
     * resolveIsAdmin: an internal Apache redirect exposes the authenticated
     * user as REDIRECT_REMOTE_USER, so reading only the plain name would lose
     * it — breaking user-realm account resolution (JWT sub) and the SPA
     * username. Returns '' when absent; callers validate.
     */
    public static function resolveRemoteUser(array $server)
    {
        return self::serverVarThroughRedirects($server, 'REMOTE_USER');
    }

    // Read a web-server env var, tolerating the REDIRECT_ prefix (possibly
    // chained) that Apache prepends after an internal redirect. The plain
    // name wins; otherwise the innermost (fewest-prefix) non-empty match.
    private static function serverVarThroughRedirects(array $server, $name)
    {
        if (isset($server[$name]) && $server[$name] !== '') {
            return (string) $server[$name];
        }
        // Chained internal redirects stack REDIRECT_ prefixes, so the
        // least-prefixed key holds the most recent (innermost) value. Pick it
        // deterministically rather than the first key in $_SERVER order — a
        // stale outer value must not win the role/account resolution.
        $best = '';
        $bestDepth = null;
        foreach ($server as $key => $value) {
            if ($value === '') {
                continue;
            }
            $rest = $key;
            $depth = 0;
            while (strncmp($rest, 'REDIRECT_', 9) === 0) {
                $rest = (string) substr($rest, 9);
                $depth++;
                if ($rest === $name) {
                    break;
                }
            }
            if ($depth === 0 || $rest !== $name) {
                continue;
            }
            if ($bestDepth === null || $depth < $bestDepth) {
                $best = (string) $value;
                $bestDepth = $depth;
            }
        }
        return $best;
    }

    /**
     * @return string
     */
     public function getJson()
     {
         return file_get_contents('php://input');
     }

    /**
     * @return void
     */
    public function adminAction()
    {
        $command = $this->prepareRequest();

        try {
            $response = $this->execute($command);
            $this->renderSuccess($response);
        } catch (\ErrorException $e) {
            $this->renderError($e->getMessage());
        }
    }

     /**
     * User-role default: production-grade no-panel hosts expose a separate
     * /i360/user/ Apache location for system mailbox owners. The only
     * command this realm is allowed to use is commandIE (routed by
     * Request::handle straight into imunifyEmailAction); everything else
     * is rejected here.
     */
    public function userAction()
    {
        $this->renderError(
            json_encode(array(
                'result' => 'error',
                'messages' => 'Forbidden: command not available in user role',
            )),
            403
        );
    }

    /**
     * SPA-facing role. The bundled SPA models only admin/client, so the user
     * realm maps onto client to render the navbar (and the ImunifyEmail tab)
     * for mailbox owners; server-side per-account scoping is unchanged.
     *
     * @return string
     */
    public function getSpaRole()
    {
        return $this->isAdmin ? 'admin' : 'client';
    }

    /**
     * Resolve the IE account_name for the current request.
     *
     * Admin role → 'root' (full scope), regardless of REMOTE_USER. The admin
     * realm is reached via /i360/admin/, which is htpasswd-gated on the
     * Apache side, so REMOTE_USER there reflects the panel-admin login, not
     * a mailbox owner.
     *
     * User role → REMOTE_USER, validated against a conservative UNIX-name
     * regex and explicitly rejecting 'root' (anti-escalation guard). The
     * /i360/user/ realm is PAM-gated against system users on Apache.
     */
    protected function getImunifyEmailAccountName()
    {
        if ($this->isAdmin) {
            return 'root';
        }
        $user = self::resolveRemoteUser($_SERVER);
        if ($user === 'root') {
            throw new \RuntimeException(
                'user role cannot claim the root account'
            );
        }
        if (!self::isValidRemoteUser($user)) {
            throw new \RuntimeException(
                'user role requires a valid REMOTE_USER'
            );
        }
        return $user;
    }

    private static function isValidRemoteUser($user)
    {
        $len = strlen($user);
        if ($len < 1 || $len > self::REMOTE_USER_MAX_LEN) {
            return false;
        }
        if (strspn($user, self::REMOTE_USER_HEAD_CHARS, 0, 1) !== 1) {
            return false;
        }
        return strspn($user, self::REMOTE_USER_TAIL_CHARS) === $len;
    }

    /**
     * @param string $data
     * @param string $action
     * @return string
     * @throws \ErrorException
     */
    public function execute($data, $action = 'execute')
    {
        $command = sprintf(__DIR__ . '/../../bin/execute.py %s', $action);

        $descriptorspec = array(  // will add pipes:
            0 => array("pipe", "r"),  // 0 => writeable handle connected to child stdin
            1 => array("pipe", "w"),  // 1 => readable handle connected to child stdout
            2 => array("pipe", "w"),  // 2 => readable handle connected to child stderr
        );
        $process = proc_open($command, $descriptorspec, $pipes);

        if (is_resource($process)) {
            fwrite($pipes[0], base64_encode($data));
            fclose($pipes[0]);

            $response = stream_get_contents($pipes[1]) . stream_get_contents($pipes[2]);
            fclose($pipes[1]);
            fclose($pipes[2]);

            $code = proc_close($process);
        } else {
            $warning = '"proc_open" function is required for Imunify UI to work.'.
                ' Please remove it from "disable_functions" list in '.php_ini_loaded_file();
            error_log($warning);
            $this->renderError($warning);
            return '';
        }

        if ($code) {
            throw new \ErrorException($response);
        }

        return $response;
    }
}
