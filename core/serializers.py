from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Category, ArtisanProfile, VerificationRequest, Booking, BookingPhoto, Review, DisputeReport
from accounts.serializers import UserSerializer
from locations.serializers import CountryLiteSerializer, StateLiteSerializer, LGASerializer

User = get_user_model()


class SubcategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.SerializerMethodField()
    parent_name_ha = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'name_ha', 'description', 'icon', 'parent_name', 'parent_name_ha']

    def get_parent_name(self, obj):
        return obj.parent.name if obj.parent else None

    def get_parent_name_ha(self, obj):
        return obj.parent.name_ha if obj.parent and obj.parent.name_ha else None


class CategorySerializer(serializers.ModelSerializer):
    subcategories = SubcategorySerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'name_ha', 'description', 'icon', 'subcategories', 'created_at']


class FlatCategorySerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(source='parent.id', read_only=True, allow_null=True)
    parent_name = serializers.SerializerMethodField()
    parent_name_ha = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'name_ha', 'description', 'icon', 'parent_id', 'parent_name', 'parent_name_ha']

    def get_parent_name(self, obj):
        return obj.parent.name if obj.parent else None

    def get_parent_name_ha(self, obj):
        return obj.parent.name_ha if obj.parent and obj.parent.name_ha else None


class ArtisanProfileSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_name_ha = serializers.CharField(source='category.name_ha', read_only=True, default='')
    service_countries_details = CountryLiteSerializer(source='service_countries', many=True, read_only=True)
    service_states_details = StateLiteSerializer(source='service_states', many=True, read_only=True)
    service_lgas_details = LGASerializer(source='service_lgas', many=True, read_only=True)
    
    # 👇 1. Add the distance field
    distance = serializers.SerializerMethodField() 
    
    # 🔥 1. Add this new custom field
    profession_name = serializers.SerializerMethodField()

    class Meta:
        model = ArtisanProfile
        fields = [
            'id', 'user', 'user_details', 'category', 'category_name', 'category_name_ha', 'profession_name',
            'bio', 'experience_years', 'hourly_rate',
            'service_countries', 'service_states', 'service_lgas',
            'service_countries_details', 'service_states_details', 'service_lgas_details',
            'verification_status', 'is_available', 'rating', 'total_reviews', 'total_bookings',
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
            'service_countries', 'service_states', 'service_lgas',
            'is_available'
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


class BookingPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingPhoto
        fields = ['id', 'image', 'created_at']


class BookingSerializer(serializers.ModelSerializer):
    client_details = UserSerializer(source='client', read_only=True)
    artisan_details = UserSerializer(source='artisan', read_only=True)
    country_details = CountryLiteSerializer(source='country', read_only=True)
    state_details = StateLiteSerializer(source='state', read_only=True)
    lga_details = LGASerializer(source='lga', read_only=True)
    # Read aliases matching the mobile app's field names (additive; the
    # canonical fields below stay unchanged for existing clients).
    description = serializers.CharField(source='service_description', read_only=True)
    location = serializers.CharField(source='address', read_only=True)
    date = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()
    # 'artisan' is a User id; the app's artisan screens navigate by
    # ArtisanProfile id, which is a different number.
    artisan_profile_id = serializers.SerializerMethodField()
    has_review = serializers.SerializerMethodField()
    photos = BookingPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'client', 'client_details', 'artisan', 'artisan_details',
            'artisan_profile_id',
            'service_description', 'description', 'address', 'location',
            'country', 'state', 'lga',
            'country_details', 'state_details', 'lga_details',
            'scheduled_date', 'date', 'time', 'duration_hours', 'total_cost',
            'status', 'cancellation_reason', 'has_review', 'photos',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['client', 'status']

    def get_artisan_profile_id(self, obj):
        profile = getattr(obj.artisan, 'artisan_profile', None)
        return profile.id if profile else None

    def get_has_review(self, obj):
        return hasattr(obj, 'review')

    def get_date(self, obj):
        from django.utils import timezone
        if not obj.scheduled_date:
            return None
        return timezone.localtime(obj.scheduled_date).date().isoformat()

    def get_time(self, obj):
        from django.utils import timezone
        if not obj.scheduled_date:
            return None
        return timezone.localtime(obj.scheduled_date).strftime('%H:%M')

    def validate_scheduled_date(self, value):
        from django.utils import timezone
        if value < timezone.now():
            raise serializers.ValidationError("Scheduled date must be in the future.")
        return value


class BookingCreateSerializer(serializers.ModelSerializer):
    # The mobile booking wizard sends {artisan, date, time, description, location}.
    # 'description'/'location' write to the canonical model fields via source;
    # 'date' + 'time' are combined into scheduled_date in validate(). The
    # original field names remain accepted for backward compatibility.
    description = serializers.CharField(source='service_description', required=False)
    location = serializers.CharField(source='address', required=False)
    date = serializers.DateField(required=False, write_only=True)
    time = serializers.TimeField(required=False, write_only=True)

    class Meta:
        model = Booking
        fields = [
            'artisan', 'service_description', 'description', 'address', 'location',
            'country', 'state', 'lga',
            'scheduled_date', 'date', 'time', 'duration_hours', 'total_cost'
        ]
        extra_kwargs = {
            'service_description': {'required': False},
            'address': {'required': False},
            'scheduled_date': {'required': False},
            'country': {'required': False},
            'state': {'required': False},
            'lga': {'required': False},
        }

    def validate_artisan(self, value):
        if value.role != 'artisan':
            raise serializers.ValidationError("Selected user is not an artisan.")
        if not value.is_active:
            raise serializers.ValidationError("This artisan account is not active.")
        if not hasattr(value, 'artisan_profile'):
            raise serializers.ValidationError("This artisan does not have a profile yet.")
        request = self.context.get('request')
        if request and request.user == value:
            raise serializers.ValidationError("You cannot book yourself.")
        return value

    def validate(self, attrs):
        from datetime import datetime, time as dt_time
        from django.utils import timezone

        date = attrs.pop('date', None)
        time = attrs.pop('time', None)

        if not attrs.get('scheduled_date'):
            if not date:
                raise serializers.ValidationError(
                    {'date': "Provide 'scheduled_date' or 'date' (with optional 'time')."}
                )
            naive = datetime.combine(date, time or dt_time(9, 0))
            attrs['scheduled_date'] = timezone.make_aware(naive)

        if attrs['scheduled_date'] < timezone.now():
            raise serializers.ValidationError(
                {'scheduled_date': "Scheduled date must be in the future."}
            )

        if not attrs.get('service_description'):
            raise serializers.ValidationError(
                {'description': "A job description is required."}
            )
        if not attrs.get('address'):
            raise serializers.ValidationError(
                {'location': "An address is required."}
            )

        # Double-booking guard: the mobile app offers a fixed set of time
        # slots, so an exact scheduled_date match for the same artisan
        # means two clients are trying to claim the identical slot.
        # Cancelled bookings don't block a new request at that time.
        artisan = attrs.get('artisan')
        if artisan and Booking.objects.filter(
            artisan=artisan,
            scheduled_date=attrs['scheduled_date'],
            status__in=['pending', 'confirmed', 'in_progress'],
        ).exists():
            raise serializers.ValidationError(
                {'scheduled_date': "This artisan already has a booking at that time. Please choose a different slot."}
            )

        return attrs


class BookingUpdateSerializer(serializers.ModelSerializer):
    # Legal status transitions per role. Bookings not listed here
    # ('completed', 'cancelled') are terminal.
    ALLOWED_TRANSITIONS = {
        'client': {
            'pending': {'cancelled'},
            'confirmed': {'cancelled'},
        },
        'artisan': {
            'pending': {'confirmed', 'cancelled'},
            'confirmed': {'in_progress', 'cancelled'},
            'in_progress': {'completed'},
        },
    }

    class Meta:
        model = Booking
        fields = ['status', 'cancellation_reason']

    def validate(self, attrs):
        new_status = attrs.get('status')
        booking = self.instance
        if new_status and new_status != booking.status:
            user = self.context['request'].user
            if user == booking.client:
                party = 'client'
            elif user == booking.artisan:
                party = 'artisan'
            else:
                raise serializers.ValidationError(
                    {'status': "You are not a party to this booking."}
                )
            allowed = self.ALLOWED_TRANSITIONS.get(party, {}).get(booking.status, set())
            if new_status not in allowed:
                raise serializers.ValidationError(
                    {'status': f"A {party} cannot change this booking from "
                               f"'{booking.status}' to '{new_status}'."}
                )
        return attrs


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

    # No validate_booking here: 'booking' is read_only above, and DRF never
    # calls validate_<field> for read-only fields. The real "completed" and
    # "not already reviewed" checks live in ReviewViewSet.perform_create,
    # where 'booking' is actually resolved from the request.


class PublicReviewSerializer(serializers.ModelSerializer):
    """For the public artisan-reviews endpoint. Deliberately NOT ReviewSerializer:
    that one nests booking_details -> client_details -> full UserSerializer,
    which includes the reviewing client's phone number, email, and address —
    fine for the client/artisan viewing their own review, a real PII leak if
    shown to any stranger browsing an artisan's profile. This serializer
    exposes only a first name, nothing else about the reviewer."""
    client_first_name = serializers.CharField(source='booking.client.first_name', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'rating', 'comment', 'client_first_name', 'created_at']


class DisputeReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisputeReport
        fields = [
            'id', 'booking', 'category', 'description',
            'status', 'resolution_notes', 'created_at', 'updated_at',
        ]
        # reporter comes from request.user in the view, never client input.
        # status/resolution_notes only ever change via Django Admin.
        read_only_fields = ['status', 'resolution_notes']


class AgentOverviewSerializer(serializers.ModelSerializer):
    """One agent, as seen by their state coordinator — identity plus the
    two counts CoordinatorAgentListView annotates onto the queryset."""
    state_details = StateLiteSerializer(source='state', read_only=True)
    # source names differ from the annotation aliases in CoordinatorAgentListView
    # only in that those aliases can't reuse 'artisans_registered' itself — that
    # name is already the FK related_name and Django's ORM rejects the collision.
    artisans_registered = serializers.IntegerField(source='registered_artisans_count', read_only=True)
    artisans_verified = serializers.IntegerField(source='verified_artisans_count', read_only=True)

    class Meta:
        model = get_user_model()
        fields = [
            'id', 'first_name', 'last_name', 'email', 'phone_number',
            'account_status', 'state_details', 'created_at',
            'artisans_registered', 'artisans_verified',
        ]
