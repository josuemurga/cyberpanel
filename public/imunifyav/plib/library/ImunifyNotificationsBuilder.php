<?php

namespace Imunify360;

class ImunifyNotificationsBuilder
{
    /**
     * Main dispatcher: choose recipients by event_id
     */
    public static function dispatch($event)
    {
        $adminLogin = self::getAdminLogin();
        switch ($event->event_id ?? null) {
            case 'CUSTOM_SCAN_MALWARE_FOUND':
                $event->initiator = $adminLogin;
                self::prepareAndSendNotification($adminLogin, $event);
                break;
            case 'REALTIME_MALWARE_FOUND':
                // malicious_files is an object {user:[files]}
                if (isset($event->malicious_files) && is_object($event->malicious_files)) {
                    foreach ($event->malicious_files as $login => $files) {
                        if (!is_array($files) || !count($files)) {
                            continue;
                        }
                        $evClone = (object)get_object_vars($event);
                        $evClone->malicious_files = array_values($files); // pure array
                        $evClone->total_malicious = count($files);
                        $evClone->initiator = $login;
                        self::prepareAndSendNotification($login, $evClone);
                    }
                }
                break;
            case 'USER_SCAN_MALWARE_FOUND':
                if (isset($event->initiator) && $event->initiator !== 'undefined') {
                    self::prepareAndSendNotification($event->initiator, $event);
                } else {
                    $event->initiator = $adminLogin;
                    self::prepareAndSendNotification($adminLogin, $event);
                }
                break;
            default:
                if (isset($event->message_type)) {
                    $login = isset($event->user) && !empty($event->user) ? $event->user : $adminLogin;
                    $isGeneric = strtolower($event->message_type) === 'generic';
                    self::prepareAndSendNotification($login, $event, $isGeneric);
                }
                break;
        }
    }

    private static function prepareAndSendNotification($login, $event, $isGeneric = false)
    {
        $client = null;
        try {
            $client = \pm_Client::getByLogin($login);
        } catch (\pm_Exception $e) {
            ImunifyLog::err('Could not get client by login: ' . $login . '. Trying to find a client as system user. Original error: ' . $e->getMessage());
            $client = self::getClientBySystemUser($login);
        }

        if (is_null($client)) {
            ImunifyLog::err('Failed to find ' . $login . ' in Plesk');
            return;
        }

        $imunifyClient = new ImunifyClient($client->getId(), $client);
        $notification = new ImunifyNotification($imunifyClient, $event);
        $notification->send($isGeneric);
    }

    private static function getClientBySystemUser($systemUserName)
    {
        $mainDomains = \pm_Domain::getAllDomains(true);
        $foundClient = null;

        try {
            foreach ($mainDomains as $domain) {
                $domainSysUserLogin = $domain->getSysUserLogin();

                if ($domainSysUserLogin === $systemUserName) {
                    $foundClient = $domain->getClient();
                    break;
                }
            }
        } catch (\pm_Exception $e) {
            ImunifyLog::err('Failed to find subscription by system user name: ' . $e->getMessage());
        }

        return $foundClient;
    }

    private static function getAdminLogin(): string
    {
        if (version_compare(\pm_ProductInfo::getVersion(), '18.0.56', '>=')) {
            try {
                $admin = \pm_Client::getAdmin();
                return $admin->getLogin();
            } catch (\pm_Exception $e) {
                return self::getAdminLoginFromDb();
            }
        } else {
            return self::getAdminLoginFromDb();
        }
    }

    private static function getAdminLoginFromDb(): string
    {
        try {
            $db = \pm_Bootstrap::getDbAdapter();
            $result = $db->fetchOne("SELECT login FROM clients WHERE type = 'admin' ORDER BY id LIMIT 1");
            return $result ?: 'admin';
        } catch (\Exception $e) {
            ImunifyLog::err('Imunify: Failed to get admin login: ' . $e->getMessage());
            return 'admin'; // fallback
        }
    }
}
