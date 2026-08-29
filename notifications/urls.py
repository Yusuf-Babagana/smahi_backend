from django.urls import path

from .views import (
    NotificationListView, NotificationUnreadCountView,
    NotificationMarkReadView, NotificationMarkAllReadView,
)

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', NotificationUnreadCountView.as_view(), name='notification-unread-count'),
    path('mark-all-read/', NotificationMarkAllReadView.as_view(), name='notification-mark-all-read'),
    path('<int:notification_id>/read/', NotificationMarkReadView.as_view(), name='notification-mark-read'),
]
