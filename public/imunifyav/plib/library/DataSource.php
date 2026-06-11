<?php

namespace Imunify360;

class DataSource
{
    private $_dbh;

    public function __construct()
    {
        $this->_dbh = $this->getDBHandler();
    }


    private function getDBHandler()
    {
     	$db = new \pm_Bootstrap();
        return $db->getDbAdapter();
    }


   function getUserRoleByLogin($username)
    {
     	$query = "SELECT DISTINCT smb_roles.id, smb_users.login, smb_users.roleId, smb_roles.name FROM smb_users, smb_roles WHERE smb_users.login=? AND smb_roles.id=smb_users.roleId";
        if ($sth = $this->_dbh->query($query, $username)) {
            $result = $sth->fetchAll(\Zend_Db::FETCH_ASSOC);;
            if (!empty($result)) {
                return $result[0];
            }
        }
        return null;
    }

}
