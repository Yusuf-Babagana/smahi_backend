from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, ArtisanViewSet, ArtisanProfileView,
    VerificationRequestViewSet, BookingViewSet, ReviewViewSet,
    AIChatView, TranscribeView, AgentArtisanListView, AgentClientListView,
    AgentDashboardStatsView, AgentRegisterArtisanView, AgentVerifyArtisanView,
    AdminStatsView, AdminUserListView
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'artisans', ArtisanViewSet, basename='artisan')
router.register(r'verification', VerificationRequestViewSet, basename='verification')
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'reviews', ReviewViewSet, basename='review')

urlpatterns = [
    path('', include(router.urls)),
    path('artisan/profile/', ArtisanProfileView.as_view(), name='artisan-profile'),
    path('agent/artisans/', AgentArtisanListView.as_view(), name='agent-artisans'),
    path('agent/clients/', AgentClientListView.as_view(), name='agent-clients'),
    path('agent/dashboard-stats/', AgentDashboardStatsView.as_view(), name='agent-dashboard-stats'),
    path('agent/register-artisan/', AgentRegisterArtisanView.as_view(), name='agent-register-artisan'),
    path('agent/verify-artisan/<int:user_id>/', AgentVerifyArtisanView.as_view(), name='agent-verify-artisan'),
    path('admin/stats/', AdminStatsView.as_view(), name='admin-stats'),
    path('admin/users/', AdminUserListView.as_view(), name='admin-users'),
    path('ai/chat/', AIChatView.as_view(), name='ai-chat'),
    path('ai/transcribe/', TranscribeView.as_view(), name='ai-transcribe'),
]
