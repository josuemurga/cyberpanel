<?php

namespace Imunify360\panels;


const JSON_CONTENT_TYPE = 'Content-type: application/json; charset=utf-8';

abstract class AbstractPanel {
    const MODE = 'prod';
    const FILE_MAX_SIZE = 2097152;
    const STATIC_PATH = 'assets/static/';

    /**
     * @var \stdClass
     */
    public $request;
    /**
     * @var bool
     */
    public $isAdmin = true;

    /**
     * @return void
     */
    public abstract function adminAction();

    /**
     * @return void
     */
    public abstract function userAction();

    /**
     * @return string
     */
    public abstract function getJson();

    /**
     * @param string $data
     * @param string $action
     * @return string
     * @throws \ErrorException
     */
    public abstract function execute($data, $action = 'execute');

    /**
     * AbstractPanel constructor.
     * @param bool $isAdmin
     */
    public function __construct($isAdmin = true)
    {
        $this->isAdmin = $isAdmin;
    }

    /**
     * @return array
     */
    public function getPost() {
        return $_POST;
    }

    /**
     *
     */
    public function defaultAction()
    {
        if ($this->isAdmin) {
            $this->adminAction();
        } else {
            $this->userAction();
        }
    }

    /**
     * Forward an Imunify Email request to the IE quarantine socket.
     *
     * The route is signed with a short-lived HS256 JWT (admin → role=admin
     * sub=root; user → role=user sub=REMOTE_USER) which IE-quarantine
     * validates. The account_name (URL substitution + JWT sub)
     * is set server-side BEFORE copying client params, so it can never be
     * overridden by the caller — see the cPanel counterpart in
     * cpanel/handlers/Imunify/Wrapper.pm::imunfyEmailRequest.
     *
     * User-role requests are also subject to a path whitelist on this side
     * (defence-in-depth ahead of IE's isPermit check): only
     * accounts/{account_name}/* paths are forwarded, everything else
     * returns 403 without touching IE.
     */
    public function imunifyEmailAction()
    {
        try {
            $accountName = $this->getImunifyEmailAccountName();
        } catch (\RuntimeException $e) {
            $this->renderError(
                json_encode(array(
                    'result' => 'error',
                    'messages' => $e->getMessage(),
                )),
                403
            );
            return;
        }

        $command = isset($this->request->method)
            ? (array) $this->request->method
            : array();
        $role = $this->isAdmin ? 'admin' : 'user';

        if (!$this->isAdmin && !self::isUserAllowedIePath($command)) {
            $this->renderError(
                json_encode(array(
                    'result' => 'error',
                    'messages' => 'Forbidden: IE path is admin-only',
                )),
                403
            );
            return;
        }

        $params = array();
        if (isset($this->request->params)) {
            $params = is_object($this->request->params)
                ? get_object_vars($this->request->params)
                : (array) $this->request->params;
        }
        $httpMethod = isset($params['request_method'])
            ? (string) $params['request_method']
            : 'GET';
        // request_method is the SPA-side routing meta-field that selects
        // the HTTP verb; it must not leak into the upstream IE request
        // body/query, where it would be a spurious unknown field.
        unset($params['request_method']);

        try {
            $response = $this->getImunifyEmailClient()->call(
                $accountName, $role, $command, $httpMethod, $params
            );
        } catch (\InvalidArgumentException $e) {
            // Bad client input rejected by ImunifyEmailClient (segment
            // regex, HTTP method whitelist, ...) — surface as 400 instead
            // of 502, which we reserve for IE-side / transport failures.
            $this->renderError(
                json_encode(array(
                    'result' => 'error',
                    'messages' => $e->getMessage(),
                )),
                400
            );
            return;
        } catch (\Exception $e) {
            $this->renderError(
                json_encode(array(
                    'result' => 'error',
                    'messages' => $e->getMessage(),
                )),
                502
            );
            return;
        }

        $envelope = $this->buildImunifyEmailEnvelope(
            $response['http_status'], $response['body']
        );
        // 207 is a 2xx code but a partial-failure envelope (result:error);
        // route it to renderError with its real status, not renderSuccess.
        if ($response['http_status'] >= 400 || $response['http_status'] === 207) {
            $this->renderError($envelope, $response['http_status']);
        } else {
            $this->renderSuccess($envelope);
        }
    }

    /**
     * Factory hook so tests can swap in a mock client without touching the
     * production socket path. Subclasses can override to inject a configured
     * client.
     *
     * @return \Imunify360\ImunifyEmailClient
     */
    protected function getImunifyEmailClient()
    {
        return new \Imunify360\ImunifyEmailClient();
    }

    /**
     * Defence-in-depth whitelist of IE-quarantine paths reachable by
     * user-role requests. Mirrors IE's own scope check (isPermit) — we
     * reject before sending, IE rejects again on receipt.
     *
     * Every segment must be either the literal {account_name} placeholder
     * or match the strict SEGMENT_REGEX, so a user-controlled `..` / `/`
     * / control-char in any tail segment cannot escape the intended
     * accounts/{account_name}/... scope (the IE-client would also reject
     * it, but the entry point belongs here).
     *
     * @param array $command path segments
     * @return bool
     */
    private static function isUserAllowedIePath(array $command)
    {
        if (count($command) < 2
            || $command[0] !== 'accounts'
            || $command[1] !== \Imunify360\ImunifyEmailClient::ACCOUNT_NAME_PLACEHOLDER) {
            return false;
        }
        foreach (array_slice($command, 2) as $seg) {
            if (!is_string($seg) && !is_numeric($seg)) {
                return false;
            }
            if (!preg_match(
                \Imunify360\ImunifyEmailClient::SEGMENT_REGEX,
                (string) $seg
            )) {
                return false;
            }
        }
        return true;
    }

    /**
     * Translate an IE response into the JSON envelope the SPA expects.
     *
     * The IE-quarantine API answers with a JSON body and a real HTTP status.
     * The SPA-facing envelope uses `http_status` (not `status`) so the
     * shared ImunifyStatusInterceptor cannot mistake the IE HTTP code for
     * an agent-status enum and collapse the navbar.
     */
    private function buildImunifyEmailEnvelope($httpStatus, $body)
    {
        $data = array();
        if ($body !== '') {
            $decoded = json_decode($body, true);
            if (is_array($decoded)) {
                $data = isset($decoded['items'])
                    ? $decoded
                    : array('items' => $decoded);
            }
        }
        // 2xx is success — IE uses 201 Created for POSTs and 204 No Content
        // for DELETEs, so only-literal-200 would wrongly flag those as errors.
        // The one 2xx exception is 207 Multi-Status: a partial bulk
        // release/delete failure that must surface as an error, not a success.
        $isSuccess = $httpStatus < 400 && $httpStatus !== 207;
        return json_encode(array(
            'result' => $isSuccess ? 'success' : 'error',
            'messages' => $isSuccess
                ? ''
                : 'Something went wrong please try again',
            'http_status' => $httpStatus,
            'data' => $data,
        ));
    }

    /**
     * Source of the IE `account_name`. Default implementation handles only
     * the admin scope ('root'); subclasses that want to expose IE in user
     * role MUST override this method and translate the request-time
     * identity (REMOTE_USER, the current domain's sys user, ...) themselves.
     *
     * The default fail-closed for user role prevents a subclass that
     * inherits AbstractPanel without per-user wiring (Plesk(false),
     * DirectAdmin(false)) from accidentally executing IE calls as root —
     * a privilege escalation surfaced by BugBot on the initial PoC.
     *
     * @return string
     * @throws \RuntimeException when isAdmin is false and the subclass did
     *     not override this method
     */
    protected function getImunifyEmailAccountName()
    {
        if (!$this->isAdmin) {
            throw new \RuntimeException(
                'panel does not implement IE access for the user role'
            );
        }
        return 'root';
    }

    /**
     *
     */
    public function uploadFile()
    {
        $data = array(
            'files' => array(),
        );

        foreach ($_FILES['files']['name'] as $k => $v) {
            $data['files'][$_FILES['files']['tmp_name'][$k]] = $_FILES['files']['name'][$k];
        }

        try {
            $response = $this->execute(json_encode($data), 'uploadFile');
            $this->renderSuccess($response);
        } catch (\ErrorException $e) {
            $this->renderError($response);
        }
    }

    /**
     * @return string
     */
    public function prepareRequest() {
        $args = new \stdClass();
        $args->command = $this->request->method;

        $args->params = new \stdClass();
        if (isset($this->request->params)) {
            $args->params = $this->request->params;
        }
        $args->params->remote_addr = $_SERVER['REMOTE_ADDR'];

        return json_encode($args);
    }

    /**
     * @param string $data
     * @param bool $error
     */
    public function render($data, $error = false)
    {
        if ($error) {
            $this->renderError($data);
        } else {
            $this->renderSuccess($data);
        }
    }

    /**
     * @param string $data
     * @return bool
     */
    public function dataHasError($data)
    {
        $json = json_decode($data);
        return ($json && (isset($json->error) || (isset($json->result) && $json->result == "error")));
    }

    /**
     * @param string $data
     */
    public function renderSuccess($data)
    {
        if ($this->dataHasError($data)) {
            $this->renderError($data);
        }
        header(JSON_CONTENT_TYPE);
        header('HTTP/1.1 200 OK');
        echo $data;
        exit(0);
    }

    /**
     * @param string $data
     * @param int $http_status HTTP status line to send (default 502).
     */
    public function renderError($data, $http_status = 502)
    {
        if (!$this->dataHasError($data)) {
            $this->renderSuccess($data);
        }

        header(JSON_CONTENT_TYPE);
        header(sprintf('HTTP/1.1 %d %s', $http_status, self::httpStatusReason($http_status)));
        echo $data;
        exit(1);
    }

    protected static function httpStatusReason($code)
    {
        $map = array(
            207 => 'Multi-Status',
            400 => 'Bad Request',
            401 => 'Unauthorized',
            403 => 'Forbidden',
            404 => 'Not Found',
            500 => 'Internal Server Error',
            502 => 'Bad Gateway',
            504 => 'Gateway Timeout',
        );
        return isset($map[$code]) ? $map[$code] : 'Error';
    }

    /**
     * @param $data
     */
    public function dump($data)
    {
        header(JSON_CONTENT_TYPE);
        header('HTTP/1.1 200 OK');
        var_dump($data);
        exit(0);
    }

    /**
     * @param string $command
     */
    public function commandHeader($command, $user = null)
    {
        if (self::MODE !== 'prod') {
            header('X-I360-COMMAND: ' . $this->escapeCommand($command));
            if ($user) {
                header('X-I360-USER: ' . $this->escapeCommand($user));
            }
        }
    }

    /**
     * @param string $command
     * @return string
     */
    protected function escapeCommand($command)
    {
        return preg_replace('/[^[:alnum:][:punct:] ]+?/m', ' ', $command);
    }

    /**
     * @param string $value
     * @return string
     */
    protected function escapeParams($value)
    {
        return "'" . str_replace("'", "'\''", $value) . "'";
    }
}

