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
     */
    public function renderError($data)
    {
        if (!$this->dataHasError($data)) {
            $this->renderSuccess($data);
        }

        header(JSON_CONTENT_TYPE);
        header('HTTP/1.1 502 Bad Gateway');
        echo $data;
        exit(1);
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

