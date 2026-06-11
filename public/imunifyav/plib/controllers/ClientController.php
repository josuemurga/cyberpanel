<?php

use Imunify360\BaseController;
use \Imunify360\DataSource;
use \Imunify360\ImunifyHelper;
use \Imunify360\ImunifyPermissions;

class ClientController extends BaseController
{
    protected $_accessLevel = ['client', 'reseller'];
    private $acceptedRoles = ['Owner', 'WebMaster'];
    private $currentSession = null;

    public function init()
    {
        $session = $this->getCurrentSession();
        $client = $session->getClient();
        if ($client->isAdmin()) {
            $this->_redirect('/');
        }
        if (!ImunifyHelper::isClientPluginEnabled()) {
            echo 'Plugin is disabled. Please contact the administrator.';
            return;
        }
        if (!$client->isReseller() && !$client->isClient()) {
            $db = new DataSource();
            $userName = $client->getLogin();
            $userData = $db->getUserRoleByLogin($userName);
            // accept Owner users
            if ($userData  && in_array($userData['name'], $this->acceptedRoles)) {
                $this->_accessLevel = [];
            } else {
               echo 'No data to show, Permission denied!';
               return;
            }
        }
        $domains = $session->getCurrentDomains();
        if (!ImunifyHelper::checkHosting($domains)) {
            echo 'No data to show, because no subscriptions with domains exist';
            return;
        }
        if (!ImunifyPermissions::isAvailableForEndUser($client, $domains)) {
            echo 'It is not available by permission in the Service Plan';
            return;
        }
        parent::init();
        \Imunify360\ImunifyHelper::defineAppMode();
    }


    public function indexAction()
    {
        $panel = new \Imunify360\panels\Plesk(false);
        $this->view->headScript()->appendScript('var i360role = "client"');
        $settings = json_encode($this->getSettings());
        $this->view->headScript()->appendScript("var i360PleskSettings = $settings;");

        $this->commonAppends();
    }

    public function requestAction()
    {
        $this->_helper->layout->disableLayout();
        $this->_helper->viewRenderer->setNoRender(true);

        $panel = new \Imunify360\panels\Plesk(false);
        (new \Imunify360\Request($panel))->handle();
    }

    private function getCurrentSession(): \pm_Session
    {
        if ($this->currentSession === null) {
            $this->currentSession = new \pm_Session();
        }
        return $this->currentSession;
    }

    /**
     * Get the settings for the client
     *
     * @return array The settings array.
     */
    private function getSettings(): array
    {
        $session = $this->getCurrentSession();
        $client = $session->getClient();
        $domains = $session->getCurrentDomains();

        return array(
            'buyUrl' => null,
            'upgradeUrl' => null,
            'marketplace' => null,
            'licenseType' => null,
            'userScanAllowed' => ImunifyPermissions::scanningAllowed($client, $domains),
            'userCleanupAllowed' => ImunifyPermissions::cleanupAllowed($client, $domains),
        );
    }

}
