from django.urls import path
from . import views

urlpatterns = [
    path('', views.packagesHome, name='packagesHome'),
    path('createPackage', views.createPacakge, name='createPackage'),
    path('deletePackage', views.deletePacakge, name='deletePackage'),
    path('modifyPackage', views.modifyPackage, name='modifyPackage'),
    path('listPackages', views.listPackages, name='listPackages'),
    path('fetchPackagesTable', views.fetchPackagesTable, name='fetchPackagesTable'),

    # Softi: uso del plan por cuenta / website
    path('planUsage', views.planUsage, name='planUsage'),
    path('fetchPlanUsage', views.fetchPlanUsage, name='fetchPlanUsage'),

    # Package Modification URLs
    path('submitPackage', views.submitPackage, name='submitPackage'),
    path('submitDelete', views.submitDelete, name='submitDelete'),
    path('submitModify', views.submitModify, name='submitModify'),
    path('saveChanges', views.saveChanges, name='saveChanges'),
]
