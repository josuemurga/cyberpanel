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
        } catch (\Throwable $e) {
            ImunifyLog::err('Could not get client by login: ' . $login . '. Trying to find a client as system user. Original error: ' . $e->getMessage());
            $client = self::getClientBySystemUser($login);
            // pm_Exception is the expected "no such client" signal; anything
            // else is an unexpected Plesk error, and if the fallback did not
            // recover, it must reach the entry-point guard so the script exits
            // nonzero and the agent retries instead of recording delivery
            if (is_null($client) && !($e instanceof \pm_Exception)) {
                throw $e;
            }
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
        // Plesk internals may throw non-pm_Exception errors for some domains
        // (e.g. "Site without PhysicalHosting cannot be Webspace" when
        // webspace_id = 0), so a single broken domain must not abort the search.
        $skippedDomains = 0;
        $firstError = null;
        $matchedWithoutClient = false;

        foreach (\pm_Domain::getAllDomains(true) as $domain) {
            try {
                if ($domain->getSysUserLogin() !== $systemUserName) {
                    continue;
                }
                $client = $domain->getClient();
                if ($client !== null) {
                    return $client;
                }
                $matchedWithoutClient = true;
            } catch (\Throwable $e) {
                $skippedDomains++;
                $firstError = $firstError ?? $e->getMessage();
            }
        }

        if ($skippedDomains > 0) {
            ImunifyLog::warn('Skipped ' . $skippedDomains . ' domain(s) while searching for system user ' . $systemUserName . ' (first error: ' . $firstError . '), falling back to a database lookup');
        }

        if ($skippedDomains > 0 || $matchedWithoutClient) {
            return self::getClientBySystemUserFromDb($systemUserName);
        }

        return null;
    }

    private static function getClientBySystemUserFromDb($systemUserName)
    {
        try {
            $statement = \pm_Bootstrap::getDbAdapter()->query(
                'SELECT d.cl_id FROM domains d'
                . ' JOIN hosting h ON h.dom_id = d.id'
                . ' JOIN sys_users s ON s.id = h.sys_user_id'
                . ' WHERE s.login = ? AND d.webspace_id = 0'
                . ' LIMIT 1',
                [$systemUserName]
            );
            $rows = $statement ? $statement->fetchAll(\Zend_Db::FETCH_ASSOC) : [];
            if (!empty($rows[0]['cl_id'])) {
                return \pm_Client::getByClientId((int)$rows[0]['cl_id']);
            }
        } catch (\Throwable $e) {
            ImunifyLog::err('Failed to find client for system user ' . $systemUserName . ' via database: ' . $e->getMessage());
        }

        return null;
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
