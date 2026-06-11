<?php


class Modules_Imunify360_CustomInfo implements pm_Hook_Interface
{
    public function getInfo()
    {
        // To avoid Exception: PHP Notice: Undefined index: REMOTE_ADDR;
        if (!array_key_exists('REMOTE_ADDR', $_SERVER)) {
            $_SERVER['REMOTE_ADDR'] = null;
        }

        try {
            $panel = new \Imunify360\panels\Plesk();
            return $panel->getStatsData();
        } catch (Exception $e) {
            return null;
        }
    }
}
