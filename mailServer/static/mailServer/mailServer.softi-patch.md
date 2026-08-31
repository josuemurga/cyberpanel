# SOFTI-MEJORA — parche para mailServer.js (upstream)
#
# En createEmailAccount controller, añadir al objeto data del POST:
#
#   mustChangePassword: !!$scope.mustChangePassword,
#
# Ver scripts/patch-mail-first-login.py (aplica in-place en el servidor).
