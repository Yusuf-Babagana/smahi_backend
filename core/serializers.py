from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Category, ArtisanProfile, VerificationRequest, Booking, Review
from accounts.serializers import UserSerializer
from locations.serializers import CountrySerializer, StateSerializer, LGASerializer

User = get_user_model()


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'icon', 'created_at']


class ArtisanProfileSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    service_countries_details = CountrySerializer(source='service_countries', many=True, read_only=True)
    service_states_details = StateSerializer(source='service_states', many=True, read_only=True)
    service_lgas_details = LGASerializer(source='service_lgas', many=True, read_only=True)
    
    # 👇 1. Add the distance field
    distance = serializers.SerializerMethodField() 
    
    # 🔥 1. Add this new custom field
    profession_name = serializers.SerializerMethodField()

    class Meta:
        model = ArtisanProfile
        fields = [
            'id', 'user', 'user_details', 'category', 'category_name', 'profession_name',
            'bio', 'experience_years', 'hourly_rate',
            'service_countries', 'service_states', 'service_lgas',
            'service_countries_details', 'service_states_details', 'service_lgas_details',
            'verification_status', 'rating', 'total_reviews', 'total_bookings',
            'created_at', 'updated_at', 'distance' 
        ]
        read_only_fields = ['user', 'verification_status', 'rating', 'total_reviews', 'total_bookings']

    # 👇 3. Create the method to extract the calculated distance
    def get_distance(self, obj):
        # Check if the view calculated a distance for this specific request
        if hasattr(obj, 'distance') and obj.distance != float('inf'):
            return round(obj.distance, 1) # Rounds to 1 decimal place (e.g., 2.5)
        return None

    # 🔥 3. Add this function inside the class to safely grab the name
    def get_profession_name(self, obj):
        # First, check if the category is attached directly to the Artisan Profile
        if hasattr(obj, 'category') and obj.category:
            return obj.category.name
            
        # Second, check if it was saved on the User model during registration
        if hasattr(obj.user, 'service_category') and obj.user.service_category:
            # If it's a Category object, get the name
            if hasattr(obj.user.service_category, 'name'):
                return obj.user.service_category.name
            # If it's just plain text, return the text
            return str(obj.user.service_category)
            
        return "Artisan" # Default fallback


class ArtisanProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArtisanProfile
        fields = [
            'category', 'bio', 'experience_years', 'hourly_rate',
            'service_countries', 'service_states', 'service_lgas'
        ]


class VerificationRequestSerializer(serializers.ModelSerializer):
    artisan_details = UserSerializer(source='artisan', read_only=True)
    reviewed_by_details = UserSerializer(source='reviewed_by', read_only=True)

    class Meta:
        model = VerificationRequest
        fields = [
            'id', 'artisan', 'artisan_details',
            'document_image_1', 'document_image_2', 'document_image_3',
            'additional_info', 'status', 'rejection_reason',
            'reviewed_by', 'reviewed_by_details', 'reviewed_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['artisan', 'status', 'reviewed_by', 'reviewed_at']


class VerificationProcessSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=['approved', 'rejected'])
    rejection_reason = serializers.CharField(required=False, allow_blank=True)


class BookingSerializer(serializers.ModelSerializer):
    client_details = UserSerializer(source='client', read_only=True)
    artisan_details = UserSerializer(source='artisan', read_only=True)
    country_details = CountrySerializer(source='country', read_only=True)
    state_details = StateSerializer(source='state', read_only=True)
    lga_details = LGASerializer(source='lga', read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'client', 'client_details', 'artisan', 'artisan_details',
            'service_description', 'address',
            'country', 'state', 'lga',
            'country_details', 'state_details', 'lga_details',
            'scheduled_date', 'duration_hours', 'total_cost',
            'status', 'cancellation_reason',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['client', 'status']

    def validate_scheduled_date(self, value):
        from django.utils import timezone
        if value < timezone.now():
            raise serializers.ValidationError("Scheduled date must be in the future.")
        return value


class BookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = [
            'artisan', 'service_description', 'address',
            'country', 'state', 'lga',
            'scheduled_date', 'duration_hours', 'total_cost'
        ]


class BookingUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ['status', 'cancellation_reason']


class ReviewSerializer(serializers.ModelSerializer):
    booking_details = BookingSerializer(source='booking', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'booking', 'booking_details', 'rating', 'comment', 'created_at', 'updated_at']
        read_only_fields = ['booking']

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate_booking(self, value):
        if value.status != 'completed':
            raise serializers.ValidationError("Can only review completed bookings.")
        if hasattr(value, 'review'):
            raise serializers.ValidationError("This booking has already been reviewed.")
        return value
