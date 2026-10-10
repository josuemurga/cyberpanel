<?php

namespace Imunify360\panels;


class DirectAdmin extends AbstractPanel {
    const MANIFEST_PATH = 'plugins/Imunify/images/assets/static/manifest.json';

    /**
     * @return array
     */
    public function getPost() {
        if (!$_SERVER['POST'] || json_decode($_SERVER['POST'])) {
            return array();
        }

        $data = array();
        $parts = explode('&', $_SERVER['POST']);
        foreach ($parts as $part) {
            list($property, $value) = explode('=', $part);
            $property = urldecode($property);
            $value = urldecode($value);
            if (($pos = strpos($property, '[]')) !== false) {
                $property = substr($property, 0, $pos);
                if (!isset($data[$property]) || !is_array($data[$property])) {
                    $data[$property] = array();
                }
                array_push($data[$property], $value);
            } else {
                $data[$property] = $value;
            }
        }

        return $data;
    }

    /**
     *
     */
    public function uploadFile()
    {
        $data = array(
            'files' => array(),
        );

        foreach ($this->request->files as $tmpPath) {
            $fileName = substr(basename($tmpPath), 0, -6);     // last 6 symbols are randomly added
            $data['files'][$tmpPath] = $fileName;
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
    public function getJson() {
        return $_SERVER['POST'];
    }

    /**
     *
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
     *
     */
    public function userAction()
    {
        $this->adminAction();
    }

    /**
     * @param string $data
     * @param string $action
     * @return string $response
     * @throws \ErrorException
     */
    public function execute($data, $action = 'execute')
    {
        $command = sprintf('/usr/bin/imunify360-command-wrapper %s', $action);

        if ($this->isAdmin) {
            $command = 'sudo ' . $command;
        }

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
            $error = '"proc_open" function is required for Imunify UI to work.' .
                ' Please remove it from "disable_functions" list in ' . php_ini_loaded_file();
            error_log($error);
            throw new \ErrorException($error);
        }

        if ($code) {
            throw new \ErrorException($response);
        }

        return $response;
    }

    /**
     * @param string $data
     */
    public function renderSuccess($data)
    {
        echo "HTTP/1.1 200 OK\r\n";
        echo "Content-Type: application/json; charset=utf-8\r\n\r\n";
        echo $data;
        exit(0);
    }

    /**
     * @param string $data
     * @param int $http_status HTTP status line to send (default 502).
     */
    public function renderError($data, $http_status = 502)
    {
        // Use the shared dataHasError helper so error envelopes coming
        // from imunifyEmailAction ({result:'error', http_status:...}) are
        // rendered with the upstream status — the legacy check looked
        // only at `error` key and missed those, sending 200 OK for IE
        // errors on DirectAdmin (cursor-bugbot 740ac3e4).
        if (!$this->dataHasError($data)) {
            $this->renderSuccess($data);
            return;
        }
        $reason = self::httpStatusReason($http_status);
        echo "HTTP/1.1 {$http_status} {$reason}\r\n";
        echo "Content-Type: application/json; charset=utf-8\r\n\r\n";
        echo $data;
        exit(1);
    }

    /**
     * Not works
     * @param string $command
     */
    public function commandHeader($command, $user = null)
    {
        if (self::MODE !== 'prod') {
            echo "X-I360-COMMAND: {$this->escapeCommand($command)}\r\n";
            if ($user) {
                echo "X-I360-USER: {$this->escapeCommand($user)}\r\n";
            }
        }
    }

    public function getLang() {
        return $_SERVER['LANGUAGE'];
    }

    /**
     * @return string
     */
    protected function getUser()
    {
        return $_SERVER['USER'];
    }
}
