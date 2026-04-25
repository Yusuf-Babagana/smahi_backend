from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, ArtisanViewSet, ArtisanProfileView,
    VerificationRequestViewSet, BookingViewSet, ReviewViewSet
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
]
