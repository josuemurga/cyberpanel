<?php

class IndexController extends \Imunify360\BaseController
{
    // License types as they are listed in agent
    const LICENSE_TYPE_IMUNIFY_AV_PLUS = 'imunifyAVPlus';
    const LICENSE_TYPE_IMUNIFY_360 = 'imunify360';

    /**
     * Initialize the controller.
     */
    public function init()
    {
        parent::init();

        $session = new \pm_Session();
        $client = $session->getClient();
        if (!$client->isAdmin()) {
            $this->_redirect('/client/index');
        }
        \Imunify360\ImunifyHelper::defineAppMode();
    }

    /**
     * Default action for the controller.
     */
    public function indexAction()
    {
        $panel = new \Imunify360\panels\Plesk();
        $this->view->headScript()->appendScript('var i360role = "admin"');

        $settings = json_encode($this->getSettings());
        $this->view->headScript()->appendScript("var i360PleskSettings = $settings;");

        $this->commonAppends();
    }

    /**
     * Handle request action.
     */
    public function requestAction()
    {
        $this->_helper->layout->disableLayout();
        $this->_helper->viewRenderer->setNoRender(true);

        $panel = new \Imunify360\panels\Plesk();
        (new \Imunify360\Request($panel))->handle();
    }

    /**
     * Get the license type based on the license key.
     *
     * @return string|null The license type if available, null otherwise.
     */
    private function getLicenseType()
    {
        $licenseKey = \Imunify360\ImunifyHelper::getImunifyLicenseKey();
        if ($licenseKey) {
            return strpos($licenseKey, 'IMAV') === 0 ? self::LICENSE_TYPE_IMUNIFY_AV_PLUS : self::LICENSE_TYPE_IMUNIFY_360;
        }
        return null;
    }

    /**
     * Get the settings for the controller.
     *
     * @return array The settings array.
     */
    private function getSettings(): array
    {
        $serverFileManager = new \pm_ServerFileManager();
        return array(
            'buyUrl' => \pm_Context::getBuyUrl(),
            'upgradeUrl' => \pm_Context::getUpgradeLicenseUrl(),
            'marketplace' => $serverFileManager->fileExists('/var/imunify360/plesk-ext-marketplace'),
            'licenseType' => self::getLicenseType(),
            'userScanAllowed' => null,
            'userCleanupAllowed' => null,
        );
    }
}
