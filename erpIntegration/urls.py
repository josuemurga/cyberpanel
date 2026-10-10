from django.urls import path

from . import views

urlpatterns = [
    path('health', views.health, name='softiErpHealth'),
    path('provision', views.provision, name='softiErpProvision'),
    path('websites', views.websites_summary, name='softiErpWebsites'),
    path('websites/<str:domain>', views.website_detail, name='softiErpWebsiteDetail'),
]
