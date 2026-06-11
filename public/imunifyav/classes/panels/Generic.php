<?php

namespace Imunify360\panels;


class Generic extends AbstractPanel {

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
     * @return void
     */
    public function userAction()
    {
        return $this->adminAction();
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
