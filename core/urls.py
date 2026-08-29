from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, ArtisanViewSet, ArtisanProfileView, BusinessProfileViewSet, BusinessProfileView,
    VerificationRequestViewSet, BookingViewSet, ReviewViewSet,
    AIChatView, TranscribeView, AgentArtisanListView, AgentClientListView,
    AgentDashboardStatsView, AgentRegisterArtisanView, AgentVerifyArtisanView,
    AgentServiceRequestsView, AgentBusinessListView, AgentVerifyBusinessView,
    AdminStatsView, AdminUserListView, AdminUserDetailView, AdminCoordinatorListView,
    AdminCreateCoordinatorView, AdminCoordinatorStatusView,
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'artisans', ArtisanViewSet, basename='artisan')
router.register(r'businesses', BusinessProfileViewSet, basename='business')
router.register(r'verification', VerificationRequestViewSet, basename='verification')
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'reviews', ReviewViewSet, basename='review')

urlpatterns = [
    path('', include(router.urls)),
    path('artisan/profile/', ArtisanProfileView.as_view(), name='artisan-profile'),
    path('business/profile/', BusinessProfileView.as_view(), name='business-profile'),
    path('agent/artisans/', AgentArtisanListView.as_view(), name='agent-artisans'),
    path('agent/clients/', AgentClientListView.as_view(), name='agent-clients'),
    path('agent/dashboard-stats/', AgentDashboardStatsView.as_view(), name='agent-dashboard-stats'),
    path('agent/service-requests/', AgentServiceRequestsView.as_view(), name='agent-service-requests'),
    path('agent/register-artisan/', AgentRegisterArtisanView.as_view(), name='agent-register-artisan'),
    path('agent/verify-artisan/<int:user_id>/', AgentVerifyArtisanView.as_view(), name='agent-verify-artisan'),
    path('agent/businesses/', AgentBusinessListView.as_view(), name='agent-businesses'),
    path('agent/verify-business/<int:user_id>/', AgentVerifyBusinessView.as_view(), name='agent-verify-business'),
    path('admin/stats/', AdminStatsView.as_view(), name='admin-stats'),
    path('admin/users/', AdminUserListView.as_view(), name='admin-users'),
    path('admin/users/<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('admin/coordinators/', AdminCoordinatorListView.as_view(), name='admin-coordinators'),
    path('admin/coordinators/create/', AdminCreateCoordinatorView.as_view(), name='admin-coordinator-create'),
    path('admin/coordinators/<int:coordinator_id>/status/', AdminCoordinatorStatusView.as_view(), name='admin-coordinator-status'),
    path('ai/chat/', AIChatView.as_view(), name='ai-chat'),
    path('ai/transcribe/', TranscribeView.as_view(), name='ai-transcribe'),
]
