<?php

namespace Imunify360;

class ImunifyClient
{
    private $id          = '';
    private $is_admin    = null;
    private $is_reseller = null;
    private $is_client   = null;

    private $pm_client   = null;


    public function __construct($client_id, \pm_Client $client = null)
    {
        $this->id = $client_id;
        if (!is_null($client)) {
            $this->pm_client = $client;
        }
    }

    public function getId()
    {
        return $this->id;
    }

    public function isAdmin()
    {
        $this->loadPmClient();
        if (!is_null($this->is_admin)) {
            return $this->is_admin;
        }
        $this->is_admin = $this->pm_client->isAdmin();
        return $this->is_admin;
    }

    public function isReseller()
    {
        $this->loadPmClient();
        if (!is_null($this->is_reseller)) {
            return $this->is_reseller;
        }
        $this->is_reseller = $this->pm_client->isReseller();
        return $this->is_reseller;
    }

    public function isClient()
    {
        $this->loadPmClient();
        if (!is_null($this->is_client)) {
            return $this->is_client;
        }
        $this->is_client = $this->pm_client->isClient();
        return $this->is_client;
    }

    public function getPMClient()
    {
        $this->loadPmClient();
        return $this->pm_client;
    }

    private function loadPmClient()
    {
        if (is_null($this->pm_client)) {
            $this->pm_client = \pm_Client::getByClientId($this->id);
        }
    }

}
