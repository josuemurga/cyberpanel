<?php

namespace Imunify360\panels;


class Plesk extends AbstractPanel {

    /**
     * @var string
     */
    protected $userName;
    /**
     * @var string
     */
    protected $homePath;

    /**
     * @return string
     */
    public function getJson() {
        return file_get_contents('php://input');
    }

    /**
     *
     */
    public function adminAction()
    {
        $command = $this->prepareRequest();
        $this->commandHeader($command);
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
        $user = $this->getUser();
        $command = $this->prepareRequest();
        $this->commandHeader($command);

        $tmpfname = $this->tmpFileWith(base64_encode($command));
        try {
            // We need to use Plesk's `filemng` command to lower privileges.
            // We also need to pass request data via stdin, secure tmp file, or environment variables.
            // `pm_ApiCli::callSbin` doesn't expose stdin and has a limit on env var length, so the only option left is
            // to use a tmp file.
            // However, since on the other side of `filemng` we have less privileges, it is not trivial.
            // To resolve this we will simply read the file after `callSbin`, but before `filemng`.
            // It's ugly, but it works.
            $filemngArgs = array(
                $user, 'exec', $this->homePath,
                '/usr/local/psa/admin/sbin/modules/imunify360/execute.py', 'execute',
            );
            $result = \pm_ApiCli::callSbin(
                'filemng-execute.sh', $filemngArgs, \pm_ApiCli::RESULT_FULL,
                array('I360_REQUEST' => $tmpfname));
            if ($result['code'] !== 0) {
                throw new \ErrorException($result['stderr'] ?: $result['stdout']);
            }

            $this->renderSuccess($result['stdout']);
        } catch (\ErrorException $e) {
            $this->renderError($e->getMessage());
        }
    }

    /**
     * @param string $data
     * @return string
     */
    public function tmpFileWith($data)
    {
        $fileManager = new \pm_ServerFileManager;
        $tmpfname = tempnam(\pm_Context::getVarDir(), 'tmp-execute');
        $fileManager->filePutContents($tmpfname, $data);
        return $tmpfname;
    }

    public function installation()
    {
        if ($this->request->method === array('start')) {
            $this->request = \Imunify360\ImunifyHelper::getImunifyInstallationParams();
        }
        $result = \pm_ApiCli::callSbin(
            'installation.sh', array(base64_encode(json_encode($this->request))),
            \pm_ApiCli::RESULT_FULL, array('PYTHONIOENCODING=utf-8')
        );
        if ($result['code'] !== 0) {
             throw new \ErrorException($result['code'] . $result['stderr'] . $result['stdout']);
        }

        $this->renderSuccess($result['stdout']);
    }

    /**
     * @param string $data
     * @param string $action
     * @return string
     * @throws \ErrorException
     */
    public function execute($data, $action = 'execute')
    {
        $tmpfname = $this->tmpFileWith(base64_encode($data));
        $result = \pm_ApiCli::callSbin(
            'execute.py', array($action, $tmpfname),
             \pm_ApiCli::RESULT_FULL, array('PYTHONIOENCODING=utf-8')
        );
        $fileManager = new \pm_ServerFileManager;
        $fileManager->removeFile($tmpfname);

        if ($result['code'] !== 0) {
            throw new \ErrorException($result['stderr'] ?: $result['stdout']);
        }

        return $result['stdout'];
    }

    /**
     * Fetch Plesk additional license keys for ext-imunify360 and try to register Imunify using the first one.
     *
     * Pass the response from the register command forward to UI.
     * This method is essential for reselling via Plesk marketplace.
     */
    public function applyLicenseFromPanel()
    {
        $licenseKey = \Imunify360\ImunifyHelper::getImunifyLicenseKey();

        if (!is_null($licenseKey)) {
            $this->request = new \stdClass();
            $this->request->method = array('register');
            $this->request->params = new \stdClass();
            $this->request->params->regkey = $licenseKey;
            $this->adminAction();
            return;
        }

        // Couldn't find any valid Imunify keys. Return an empty response with
        // the current license status. It doesn't really matter what to
        // return, just want some valid AgentResponse without typing it here.
        $this->request = new \stdClass();
        $this->request->method = array('version');
        $this->request->params = new \stdClass();
        $this->adminAction();
    }

    public function getStatsData()
    {
        try {
            $this->request = new \stdClass();
            $this->request->method = array('plesk-stats');
            $this->request->params = new \stdClass();
            $command = $this->prepareRequest();
            $response = $this->execute($command);
            $decoded_response = json_decode($response);
            $items = isset($decoded_response->data->items) ? $decoded_response->data->items : null;
            return $items !== null ? json_encode($items) : null;
        } catch (\ErrorException $e) {
            return null;
        }
    }


    public function downgradePlugin()
    {
        try {
            \pm_ApiCli::callSbin('deploy.sh', ['--downgrade']);
            // Immediately report downgrading status to the UI
            $response = json_encode([
                'result' => 'success',
                'messages' => [],
                'data' => ['items' => null],
                'status' => 'downgrading',
            ]);
            $this->renderSuccess($response);
        } catch (\ErrorException $e) {
            $this->renderError(json_encode([
                'result' => 'error',
                'messages' => [$e->getMessage()],
                'data' => ['items' => null],
            ]));
        }
    }

    /**
     * @param string $path
     * @return string|boolean
     */
    private function fileGetContents($path) {
        $fileManager = new \pm_ServerFileManager;
        $fullPath = \pm_Context::getHtdocsDir() . $path;
        if (!$fileManager->fileExists($fullPath)) {
            return false;
        }
        return $fileManager->fileGetContents($fullPath);
    }

    /**
     * @return string
     *
     * @throws \ErrorException
     */
    protected function getUser()
    {
        if (is_null($this->userName)) {
            $currentDomain = \pm_Session::getCurrentDomain();
            if (!$currentDomain || !$currentDomain->hasHosting()) {
                $domains = \pm_Session::getCurrentDomains();
                foreach ($domains as $domain) {
                    if ($domain->hasHosting()) {
                        $currentDomain = $domain;
                        break;
                    }
                }
            }

            $this->homePath = $currentDomain->getHomePath();
            $this->userName = $currentDomain->getSysUserLogin();
        }

        return $this->userName;
    }
}
