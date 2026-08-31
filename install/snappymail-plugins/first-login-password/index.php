<?php

/**
 * SOFTI-MEJORA — Cambio obligatorio de contraseña en primer login a SnappyMail.
 */
class FirstLoginPasswordPlugin extends \RainLoop\Plugins\AbstractPlugin
{
    const
        NAME        = 'First Login Password',
        VERSION     = '1.1.1',
        RELEASE     = '2026-08-31',
        REQUIRED    = '2.36.1',
        CATEGORY    = 'Security',
        DESCRIPTION = 'Force mailbox password change on first SnappyMail login (Softi/CyberPanel)';

    /** @var \RainLoop\Config\Plugin */
    private $oConfig;

    public function Init() : void
    {
        $this->oConfig = $this->Config();
        $this->addJs('js/FirstLoginGate.js');
        $this->addJsonHook('FirstLoginCheck', 'CheckMustChange');
        $this->addJsonHook('FirstLoginChangePassword', 'ChangePassword');
    }

    public function Supported() : string
    {
        return 'First login password gate for CyberPanel e_users.must_change_password';
    }

    public function FilterAppDataPluginSection(bool $bAdmin, bool $bAuth, array &$aConfig) : void
    {
        if ($bAdmin) {
            return;
        }
        $aConfig['pass_min_length'] = (int) $this->oConfig->Get('plugin', 'pass_min_length', 10);
        $aConfig['pass_min_strength'] = (int) $this->oConfig->Get('plugin', 'pass_min_strength', 70);
        if (!$bAuth) {
            return;
        }
        try {
            $aConfig['mustChange'] = $this->mustChange($this->accountEmail());
        } catch (\Throwable $e) {
            $aConfig['mustChange'] = false;
        }
    }

    protected function configMapping() : array
    {
        return array(
            \RainLoop\Plugins\Property::NewInstance('pdo_dsn')->SetLabel('DSN')
                ->SetDefaultValue('mysql:host=localhost;dbname=cyberpanel;charset=utf8'),
            \RainLoop\Plugins\Property::NewInstance('pdo_user')->SetLabel('User')
                ->SetDefaultValue('root'),
            \RainLoop\Plugins\Property::NewInstance('pdo_password')->SetLabel('Password')
                ->SetType(\RainLoop\Enumerations\PluginPropertyType::PASSWORD),
            \RainLoop\Plugins\Property::NewInstance('pass_min_length')
                ->SetLabel('Password minimum length')
                ->SetType(\RainLoop\Enumerations\PluginPropertyType::INT)
                ->SetDescription('Minimum length of the password')
                ->SetDefaultValue(10)
                ->SetAllowedInJs(true),
            \RainLoop\Plugins\Property::NewInstance('pass_min_strength')
                ->SetLabel('Password minimum strength')
                ->SetType(\RainLoop\Enumerations\PluginPropertyType::INT)
                ->SetDescription('Minimum strength of the password in %')
                ->SetDefaultValue(70)
                ->SetAllowedInJs(true),
        );
    }

    private function pdo() : \PDO
    {
        return new \PDO(
            $this->oConfig->Get('plugin', 'pdo_dsn', 'mysql:host=localhost;dbname=cyberpanel;charset=utf8'),
            $this->oConfig->Get('plugin', 'pdo_user', 'root'),
            $this->oConfig->Get('plugin', 'pdo_password', ''),
            array(
                \PDO::ATTR_ERRMODE => \PDO::ERRMODE_EXCEPTION,
                \PDO::ATTR_EMULATE_PREPARES => true,
            )
        );
    }

    private function accountEmail() : string
    {
        $oAccount = \RainLoop\Api::Actions()->GetAccount();
        if (!$oAccount) {
            throw new \RainLoop\Exceptions\ClientException(\RainLoop\Notifications::AuthError);
        }
        return $oAccount->Email();
    }

    private function mustChange(string $email) : bool
    {
        $stmt = $this->pdo()->prepare(
            'SELECT must_change_password FROM e_users WHERE email = :email LIMIT 1'
        );
        $stmt->execute(array(':email' => $email));
        $row = $stmt->fetch(\PDO::FETCH_ASSOC);
        return $row && (int) $row['must_change_password'] === 1;
    }

    public function CheckMustChange()
    {
        return $this->jsonResponse(__FUNCTION__, array(
            'mustChange' => $this->mustChange($this->accountEmail()),
        ));
    }

    private function verifyCurrentPassword(string $email, string $currentPassword) : void
    {
        $stmt = $this->pdo()->prepare('SELECT password FROM e_users WHERE email = :email LIMIT 1');
        $stmt->execute(array(':email' => $email));
        $row = $stmt->fetch(\PDO::FETCH_ASSOC);
        if (!$row) {
            throw new \RainLoop\Exceptions\ClientException(\RainLoop\Notifications::AuthError);
        }

        $stored = (string) $row['password'];
        if (0 === \strpos($stored, '{CRYPT}')) {
            $stored = \substr($stored, 7);
        }

        if (!\password_verify($currentPassword, $stored)) {
            throw new \RainLoop\Exceptions\ClientException(
                \RainLoop\Notifications::AuthError,
                null,
                'Contraseña actual incorrecta'
            );
        }
    }

    private function hashPassword(string $plain) : string
    {
        return '{CRYPT}' . \password_hash($plain, \PASSWORD_BCRYPT);
    }

    private function validateNewPassword(string $newPassword) : void
    {
        $minLength = (int) $this->oConfig->Get('plugin', 'pass_min_length', 10);
        $minStrength = (int) $this->oConfig->Get('plugin', 'pass_min_strength', 70);

        if (\strlen($newPassword) < $minLength) {
            throw new \RainLoop\Exceptions\ClientException(
                \RainLoop\Notifications::NewPasswordShort,
                null,
                'La contraseña debe tener al menos ' . $minLength . ' caracteres'
            );
        }

        if ($minStrength > self::passwordStrength($newPassword)) {
            throw new \RainLoop\Exceptions\ClientException(
                \RainLoop\Notifications::NewPasswordWeak,
                null,
                'La contraseña es demasiado débil (mínimo ' . $minStrength . '% de fortaleza)'
            );
        }
    }

    /**
     * Misma lógica que plugins/change-password de SnappyMail.
     */
    private static function passwordStrength(string $password) : int
    {
        $i = \strlen($password);
        $max = \min(100, $i * 8);
        $s = 0;
        while (--$i) {
            $s += ($password[$i] != $password[$i - 1] ? 1 : -0.5);
        }
        $c = 0;
        $patterns = array('/[^0-9A-Za-z]+/', '/[0-9]+/', '/[A-Z]+/', '/[a-z]+/');
        foreach ($patterns as $regex) {
            if (\preg_match_all($regex, $password, $matches)) {
                ++$c;
                foreach ($matches[0] as $str) {
                    if (\strlen($str) < 5) {
                        ++$s;
                    }
                }
            }
        }

        return (int) \max(0, \min($max, $s * $c * 1.5));
    }

    public function ChangePassword()
    {
        $CurrentPassword = (string) $this->jsonParam('CurrentPassword', '');
        $NewPassword = (string) $this->jsonParam('NewPassword', '');
        $ConfirmPassword = (string) $this->jsonParam('ConfirmPassword', '');

        $email = $this->accountEmail();

        if (!$this->mustChange($email)) {
            return $this->jsonResponse(__FUNCTION__, array('changed' => false));
        }

        if ($NewPassword === '' || $ConfirmPassword === '') {
            throw new \RainLoop\Exceptions\ClientException(
                \RainLoop\Notifications::ClientViewError,
                null,
                'Debes ingresar la nueva contraseña y su confirmación'
            );
        }

        if ($NewPassword !== $ConfirmPassword) {
            throw new \RainLoop\Exceptions\ClientException(
                \RainLoop\Notifications::ClientViewError,
                null,
                'Las contraseñas nuevas no coinciden'
            );
        }

        $this->validateNewPassword($NewPassword);
        $this->verifyCurrentPassword($email, $CurrentPassword);

        $stmt = $this->pdo()->prepare(
            'UPDATE e_users SET password = :newpass, must_change_password = 0 WHERE email = :email'
        );
        $stmt->execute(array(
            ':newpass' => $this->hashPassword($NewPassword),
            ':email' => $email,
        ));

        $oActions = $this->Manager()->Actions();
        $oAccount = $oActions->GetAccount();
        $oNewPassword = new \SnappyMail\SensitiveString($NewPassword);
        $oPrevPassword = new \SnappyMail\SensitiveString($CurrentPassword);

        $oAccount->SetPassword($oNewPassword);
        if ($oAccount instanceof \RainLoop\Model\MainAccount) {
            $oActions->SetAuthToken($oAccount);
            $oAccount->resealCryptKey($oPrevPassword);
        }

        return $this->jsonResponse(__FUNCTION__, $oActions->AppData(false));
    }
}
