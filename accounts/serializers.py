from rest_framework import serializers
from django.contrib.auth import get_user_model
from locations.serializers import CountryLiteSerializer, StateLiteSerializer, LGASerializer

# 👇 Import ArtisanProfile at the top
from core.models import ArtisanProfile, Category, DEFAULT_OTHER_ICONS

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    # Force the API to require these fields to be filled out
    first_name = serializers.CharField(required=True, allow_blank=False)
    last_name = serializers.CharField(required=True, allow_blank=False)

    # 👇 Category: either an existing ID or a custom name to auto-create
    category_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    custom_category_name = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=100)
    # Only used alongside custom_category_name — an explicit icon choice for
    # a brand-new category, offered when the person typing it would rather
    # pick one than let the app guess from their wording. Ignored if the
    # named category already exists (its icon, guessed or previously
    # chosen, isn't overridden by a later registrant's preference).
    custom_category_icon = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=50)

    # Self-service registration (accounts.views.register_view, AllowAny —
    # no authentication) must never be able to mint a privileged account.
    # Every authorization check in this API (IsAdmin/IsStateAgent/
    # IsStateCoordinator in core/permissions.py) tests request.user.role
    # alone, not is_staff/is_superuser — so without this restriction,
    # POSTing role="admin" here from an anonymous client was a complete
    # privilege-escalation bypass. Agent/state_coordinator/admin accounts
    # are provisioned through authenticated, permission-checked paths only
    # (AgentRegisterArtisanView forces role='artisan' before ever reaching
    # this serializer; coordinator/admin accounts are created in Django
    # Admin) — never through this serializer's public entry point.
    PUBLIC_REGISTRATION_ROLES = {'client', 'artisan'}

    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm', 'first_name', 'last_name',
            'role', 'phone_number', 'address', 'gender', 'country', 'state', 'lga',
            # Optional (the model already has null=True, blank=True on both) —
            # the device's GPS at registration time, so an artisan is
            # immediately findable by every distance-based feature (nearest-
            # search, the map, live tracking) instead of only becoming
            # findable whenever they first open their dashboard and grant
            # location permission there (PATCH auth/profile/ via
            # UserUpdateSerializer, called from
            # app/artisan/(tabs)/dashboard.tsx) — that path stays as the
            # ongoing way these get refreshed; this just closes the gap for
            # the time between registering and that first dashboard visit.
            'latitude', 'longitude',
            'category_id', 'custom_category_name', 'custom_category_icon',
            # Offline-first registration's idempotency key — see the field's
            # own docstring on the User model for why this exists.
            'client_request_id',
        ]
        extra_kwargs = {
            'latitude': {'required': False, 'min_value': -90, 'max_value': 90},
            'longitude': {'required': False, 'min_value': -180, 'max_value': 180},
            'client_request_id': {'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def to_internal_value(self, data):
        # A raw GPS fix routinely arrives with far more precision than the
        # 6 decimal places latitude/longitude allow (DecimalField(max_digits=9,
        # decimal_places=6)) — e.g. a real expo-location reading like
        # 11.945524382145678 — and DRF's DecimalField rejects that with
        # "Ensure that there are no more than 6 decimal places" BEFORE any
        # validate_latitude()-style hook would even run (that check happens
        # inside to_internal_value itself). Round defensively here rather
        # than trusting every caller to pre-round client-side the way
        # saveCoordinates() (the profile-update path) already does —
        # this is what actually broke registration in production.
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        for field_name in ('latitude', 'longitude'):
            value = data.get(field_name)
            if value not in (None, ''):
                try:
                    data[field_name] = round(float(value), 6)
                except (TypeError, ValueError):
                    pass  # leave as-is — the normal field validation will report a clear error
        return super().to_internal_value(data)

    def validate_client_request_id(self, value):
        # Blank/None must stay None, not '' — the unique constraint would
        # otherwise reject the second-ever caller that omits this field
        # (every '' collides with every other ''), while multiple NULLs are
        # fine (SQL treats NULL as never equal to NULL, including itself).
        # allow_null=True still routes an explicit None through to here.
        return (value or '').strip() or None

    def validate_custom_category_icon(self, value):
        if value and value not in DEFAULT_OTHER_ICONS:
            raise serializers.ValidationError("Not one of the offered default icons.")
        return value

    def validate_role(self, value):
        if value not in self.PUBLIC_REGISTRATION_ROLES:
            raise serializers.ValidationError(
                "Only client and artisan accounts can be created through registration."
            )
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords do not match."})

        # Block the specific "User User" placeholder from being saved
        if attrs.get('first_name') == 'User' and attrs.get('last_name') == 'User':
            raise serializers.ValidationError({"first_name": "Please enter your actual name instead of 'User'."})

        return attrs

    def create(self, validated_data):
        # 1. Pull category data out before creating the user
        category_id = validated_data.pop('category_id', None)
        custom_category_name = validated_data.pop('custom_category_name', '').strip()
        custom_category_icon = validated_data.pop('custom_category_icon', '').strip()

        validated_data.pop('password_confirm')
        password = validated_data.pop('password')

        # 2. Create the User account
        user = User.objects.create_user(password=password, **validated_data)

        # 3. Create the ArtisanProfile with the correct category
        if user.role == 'artisan':
            resolved_category_id = None

            if category_id:
                # User picked an existing category from the list
                resolved_category_id = category_id
            elif custom_category_name:
                # User typed a custom profession — find or create the Category.
                # The icon choice only applies to a genuinely NEW category —
                # get_or_create's `defaults` are ignored when a row already
                # matches, so an earlier registrant's (or a guessed) icon for
                # an existing category is never overwritten by this one.
                category_obj, _ = Category.objects.get_or_create(
                    name__iexact=custom_category_name,
                    defaults={'name': custom_category_name, 'material_icon': custom_category_icon},
                )
                resolved_category_id = category_obj.id

            ArtisanProfile.objects.create(
                user=user,
                category_id=resolved_category_id,
                verification_status='pending'
            )

        return user


class UserSerializer(serializers.ModelSerializer):
    # Lite serializers on purpose: the full Country/State serializers nest the
    # ENTIRE location tree (37 states x their LGAs ≈ 70KB per user), which
    # ballooned every artisan/booking/chat payload. The app reads only id/name.
    country_details = CountryLiteSerializer(source='country', read_only=True)
    state_details = StateLiteSerializer(source='state', read_only=True)
    lga_details = LGASerializer(source='lga', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'role', 'phone_number',
            'address', 'profile_picture', 'gender', 'country', 'state', 'lga',
            'country_details', 'state_details', 'lga_details',
            'latitude', 'longitude', 'preferred_language',
            'is_verified', 'email_verified', 'registration_fee_paid',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'role', 'is_verified', 'email_verified', 'registration_fee_paid', 'created_at', 'updated_at']


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone_number', 'address',
            'profile_picture', 'gender', 'country', 'state', 'lga',
            'latitude', 'longitude', 'preferred_language',
        ]
        extra_kwargs = {
            'latitude': {'min_value': -90, 'max_value': 90},
            'longitude': {'min_value': -180, 'max_value': 180},
        }

    def to_internal_value(self, data):
        # Defense-in-depth alongside UserRegistrationSerializer's own copy of
        # this fix — saveCoordinates() (the mobile app's caller for this
        # endpoint) already rounds to 6dp client-side, so this path isn't
        # known to be broken today, but there's no reason a future caller
        # couldn't hit the exact same DecimalField precision error.
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        for field_name in ('latitude', 'longitude'):
            value = data.get(field_name)
            if value not in (None, ''):
                try:
                    data[field_name] = round(float(value), 6)
                except (TypeError, ValueError):
                    pass
        return super().to_internal_value(data)
