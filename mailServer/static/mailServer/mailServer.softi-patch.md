# SOFTI-MEJORA — parche para mailServer.js (upstream)
#
# createEmailAccount POST:
#   mustChangePassword: !!$scope.mustChangePassword,
#
# submitPasswordChange POST (listEmails + email forwarding):
#   mustChangePassword: !!$scope.mustChangePasswordOnReset,
# changePasswordInitial: reset $scope.mustChangePasswordOnReset = false
#
# Ver scripts/patch-mail-first-login.py (aplica in-place en el servidor).
