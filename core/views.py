from rest_framework import viewsets, status, generics
import math

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates the distance between two GPS coordinates in kilometers."""
    R = 6371.0 # Earth radius in kilometers
    
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Category, ArtisanProfile, VerificationRequest, Booking, Review
from .serializers import (
    CategorySerializer, ArtisanProfileSerializer, ArtisanProfileUpdateSerializer,
    VerificationRequestSerializer, VerificationProcessSerializer,
    BookingSerializer, BookingCreateSerializer, BookingUpdateSerializer,
    ReviewSerializer
)
from .permissions import IsArtisan, IsAgent, IsClient

User = get_user_model()


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    search_fields = ['name', 'description']


class ArtisanViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ArtisanProfileSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['category', 'verification_status', 'user']
    search_fields = ['user__first_name', 'user__last_name', 'bio']

    def get_queryset(self):
        queryset = ArtisanProfile.objects.select_related('user', 'category')
        
        # Note: I removed the prefetch_related for service_countries to keep it simple

        category_id = self.request.query_params.get('category_id')
        country_id = self.request.query_params.get('country_id')
        state_id = self.request.query_params.get('state_id')
        lga_id = self.request.query_params.get('lga_id')

        if category_id:
            queryset = queryset.filter(category_id=category_id)
            
        # 🔥 THE FIX: Tell Django to look at the User's actual location!
        if country_id:
            queryset = queryset.filter(user__country__id=country_id)
        if state_id:
            queryset = queryset.filter(user__state__id=state_id)
        if lga_id:
            queryset = queryset.filter(user__lga__id=lga_id)

        return queryset.distinct()

    # 👇 ADD THIS NEW LIST METHOD 👇
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        # 1. Grab the client's location from the URL parameters
        client_lat = request.query_params.get('latitude')
        client_lon = request.query_params.get('longitude')

        # Convert queryset to a list so we can manipulate it in Python
        artisans = list(queryset)

        if client_lat and client_lon:
            try:
                client_lat = float(client_lat)
                client_lon = float(client_lon)

                for artisan in artisans:
                    art_lat = artisan.user.latitude
                    art_lon = artisan.user.longitude
                    
                    if art_lat and art_lon:
                        # Calculate distance and attach it to the object temporarily
                        artisan.distance = calculate_haversine_distance(
                            client_lat, client_lon, float(art_lat), float(art_lon)
                        )
                    else:
                        artisan.distance = float('inf') # Push artisans without GPS to the bottom

                # 2. Sort the artisans: Closest first!
                artisans.sort(key=lambda x: getattr(x, 'distance', float('inf')))
                
                # Optional: Filter out artisans that are too far away (e.g., > 50km)
                # artisans = [a for a in artisans if getattr(a, 'distance', float('inf')) <= 50.0]

            except ValueError:
                pass # If coordinates are invalid, just return the unsorted list

        # 3. Handle Pagination and Response
        page = self.paginate_queryset(artisans)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(artisans, many=True)
        return Response(serializer.data)


class ArtisanProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, IsArtisan]
    serializer_class = ArtisanProfileSerializer

    def get_object(self):
        profile, created = ArtisanProfile.objects.get_or_create(user=self.request.user)
        return profile

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ArtisanProfileUpdateSerializer
        return ArtisanProfileSerializer


class VerificationRequestViewSet(viewsets.ModelViewSet):
    serializer_class = VerificationRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'artisan':
            return VerificationRequest.objects.filter(artisan=user)
        elif user.role == 'agent':
            return VerificationRequest.objects.filter(status='pending')
        return VerificationRequest.objects.none()

    def perform_create(self, serializer):
        serializer.save(artisan=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAgent])
    def process(self, request, pk=None):
        verification_request = self.get_object()
        serializer = VerificationProcessSerializer(data=request.data)

        if serializer.is_valid():
            verification_request.status = serializer.validated_data['status']
            verification_request.reviewed_by = request.user
            verification_request.reviewed_at = timezone.now()

            if serializer.validated_data['status'] == 'rejected':
                verification_request.rejection_reason = serializer.validated_data.get('rejection_reason', '')

            verification_request.save()

            if serializer.validated_data['status'] == 'approved':
                artisan_profile, created = ArtisanProfile.objects.get_or_create(
                    user=verification_request.artisan
                )
                artisan_profile.verification_status = 'approved'
                artisan_profile.save()

                verification_request.artisan.is_verified = True
                verification_request.artisan.save()

            return Response(
                VerificationRequestSerializer(verification_request).data,
                status=status.HTTP_200_OK
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'artisan', 'client']

    def get_queryset(self):
        user = self.request.user
        if user.role == 'client':
            return Booking.objects.filter(client=user).select_related(
                'client', 'artisan', 'country', 'state', 'lga'
            )
        elif user.role == 'artisan':
            return Booking.objects.filter(artisan=user).select_related(
                'client', 'artisan', 'country', 'state', 'lga'
            )
        return Booking.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return BookingCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return BookingUpdateSerializer
        return BookingSerializer

    def perform_create(self, serializer):
        booking = serializer.save(client=self.request.user)
        artisan_profile = booking.artisan.artisan_profile
        artisan_profile.total_bookings += 1
        artisan_profile.save()


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        if user.role == 'client':
            return Review.objects.filter(booking__client=user).select_related('booking')
        elif user.role == 'artisan':
            return Review.objects.filter(booking__artisan=user).select_related('booking')
        return Review.objects.none()

    def perform_create(self, serializer):
        booking_id = self.request.data.get('booking')
        try:
            booking = Booking.objects.get(id=booking_id, client=self.request.user)
            if booking.status != 'completed':
                raise serializers.ValidationError("Can only review completed bookings.")
            serializer.save(booking=booking)
        except Booking.DoesNotExist:
            raise serializers.ValidationError("Booking not found or you don't have permission to review it.")
