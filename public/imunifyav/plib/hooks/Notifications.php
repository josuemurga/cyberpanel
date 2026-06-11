<?php

use \Imunify360\ImunifyNotification;

class Modules_Imunify360_Notifications extends pm_Hook_Notifications
{
    public function getNotifications()
    {
        return ImunifyNotification::getDefaults();
    }
}