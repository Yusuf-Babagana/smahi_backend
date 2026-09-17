from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Deliberately NOT mounted at '' (site root) — Django admin ships a
    # catch-all view (for a friendly 404/login-redirect on a mistyped
    # admin URL) that, mounted at the root, swallows every request that
    # doesn't match an earlier pattern — including the entire /api/...
    # REST API the mobile app depends on. Confirmed by a 352/408 test
    # failure when this was tried at ''. A real prefix scopes the
    # catch-all to only paths starting with it.
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/locations/', include('locations.urls')),
    path('api/', include('core.urls')),
    path('api/v1/', include('core.urls_v1')),
    path('api/chat/', include('chat.urls')),
    path('api/notifications/', include('notifications.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
