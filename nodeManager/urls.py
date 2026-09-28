from django.urls import path
from . import views

# IMPORTANT: never reuse CyberPanel URL names (e.g. listWebsites) —
# {% url 'listWebsites' %} in the sidebar would resolve here and break Sites.
urlpatterns = [
    path("", views.listAppsPage, name="nodeManagerHome"),
    path("create", views.createAppPage, name="nodeManagerCreate"),
    path("app/<str:app_id>", views.appDetailPage, name="nodeManagerDetail"),
    path("listApps", views.listApps, name="nodeManagerListApps"),
    path("listUnregistered", views.listUnregistered, name="nodeManagerListUnregistered"),
    path("inspectProxy", views.inspectProxy, name="nodeManagerInspectProxy"),
    path("listWebsites", views.listWebsites, name="nodeManagerListWebsites"),
    path("createApp", views.createApp, name="nodeManagerCreateApp"),
    path("importApp", views.importApp, name="nodeManagerImportApp"),
    path("attachDomain", views.attachDomain, name="nodeManagerAttachDomain"),
    path("detachDomain", views.detachDomain, name="nodeManagerDetachDomain"),
    path("restartApp", views.restartApp, name="nodeManagerRestartApp"),
    path("startApp", views.startApp, name="nodeManagerStartApp"),
    path("stopApp", views.stopApp, name="nodeManagerStopApp"),
    path("deleteApp", views.deleteApp, name="nodeManagerDeleteApp"),
    path("appLogs", views.appLogs, name="nodeManagerAppLogs"),
    path("flushLogs", views.flushLogs, name="nodeManagerFlushLogs"),
    path("getEnv", views.getEnv, name="nodeManagerGetEnv"),
    path("setEnv", views.setEnv, name="nodeManagerSetEnv"),
    path("upsertEnv", views.upsertEnv, name="nodeManagerUpsertEnv"),
    path("deleteEnv", views.deleteEnv, name="nodeManagerDeleteEnv"),
    path("importEnv", views.importEnv, name="nodeManagerImportEnv"),
    path("updateBuildSettings", views.updateBuildSettings, name="nodeManagerUpdateBuildSettings"),
    path("listNodeVersions", views.listNodeVersions, name="nodeManagerListNodeVersions"),
    path("redeployApp", views.redeployApp, name="nodeManagerRedeployApp"),
    path("uploadDeploy", views.uploadDeploy, name="nodeManagerUploadDeploy"),
    path("listDeploys", views.listDeploys, name="nodeManagerListDeploys"),
]
