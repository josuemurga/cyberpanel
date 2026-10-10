from django.urls import path
from . import views

urlpatterns = [
    path('', views.homePage, name='mailGuardHome'),
    path('stats', views.stats, name='mailGuardStats'),
    path('queue', views.queue, name='mailGuardQueue'),
    path('block', views.blockUser, name='mailGuardBlock'),
    path('unblock', views.unblockUser, name='mailGuardUnblock'),
    path('queue/delete', views.deleteQueue, name='mailGuardQueueDelete'),
    path('queue/flush-bounces', views.flushBounces, name='mailGuardFlushBounces'),
    path('ipv4', views.forceIpv4, name='mailGuardForceIpv4'),
]
