from django.urls import path

from . import views

urlpatterns = [
    path('health', views.health, name='softiErpHealth'),
    path('provision', views.provision, name='softiErpProvision'),
    path('websites', views.websites_summary, name='softiErpWebsites'),
    path('websites/<str:domain>/status', views.website_status, name='softiErpWebsiteStatus'),
    path('websites/<str:domain>/owner', views.website_owner, name='softiErpWebsiteOwner'),
    path('users', views.users, name='softiErpUsers'),
    path('usage', views.usage, name='softiErpUsage'),
    path('sso', views.sso, name='softiErpSso'),
    path('websites/<str:domain>', views.website_detail, name='softiErpWebsiteDetail'),
]
