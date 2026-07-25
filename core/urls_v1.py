# /api/v1/ — reserved for genuinely new, standalone resources (per the
# marketplace-completion blueprint's versioning decision). Existing
# endpoints stay exactly where they are in core/urls.py, unversioned —
# moving them here would break the app already installed on real devices.
# Future phases (Wallet in Phase 4, etc.) register their new resources
# here too, not in the legacy unversioned router.
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DisputeReportViewSet, CoordinatorAgentListView, CoordinatorAgentStatusView,
    FavoriteListView, FavoriteToggleView, PresenceHeartbeatView,
)

router = DefaultRouter()
router.register(r'disputes', DisputeReportViewSet, basename='dispute')

urlpatterns = [
    path('', include(router.urls)),
    path('coordinator/agents/', CoordinatorAgentListView.as_view(), name='coordinator-agents'),
    path('coordinator/agents/<int:agent_id>/status/', CoordinatorAgentStatusView.as_view(), name='coordinator-agent-status'),
    path('favorites/', FavoriteListView.as_view(), name='favorites-list'),
    path('favorites/toggle/', FavoriteToggleView.as_view(), name='favorites-toggle'),
    path('presence/heartbeat/', PresenceHeartbeatView.as_view(), name='presence-heartbeat'),
]
