from rest_framework import serializers
from django.contrib.auth import get_user_model
from locations.serializers import CountryLiteSerializer, StateLiteSerializer, LGASerializer

# 👇 Import ArtisanProfile at the top
from core.models import ArtisanProfile, BusinessProfile, Category, DEFAULT_OTHER_ICONS

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    # Force the API to require these fields to be filled out
    first_name = serializers.CharField(required=True, allow_blank=False)
    last_name = serializers.CharField(required=True, allow_blank=False)

    # 👇 Category: either an existing ID or a custom name to auto-create.
    # Shared between artisan (a profession) and business (a business type)
    # registration — which Category.category_type a custom name gets
    # created under is decided by role in create() below, never by the
    # caller, so a business registrant can't accidentally pollute the
    # artisan profession list (or vice versa).
    category_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    custom_category_name = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=100)
    # Only used alongside custom_category_name — an explicit icon choice for
    # a brand-new category, offered when the person typing it would rather
    # pick one than let the app guess from their wording. Ignored if the
    # named category already exists (its icon, guessed or previously
    # chosen, isn't overridden by a later registrant's preference).
    custom_category_icon = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=50)

    # Business-only — validated as required in validate() when role='business'.
    business_name = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=150)

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
    # Admin) — never through this serializer's public entry point. Business
    # is public/self-service, same as client/artisan — a hospital/hotel/shop
    # owner registering their own business poses no privilege-escalation risk.
    PUBLIC_REGISTRATION_ROLES = {'client', 'artisan', 'business'}

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
            'category_id', 'custom_category_name', 'custom_category_icon', 'business_name',
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

    def __init__(self, *args, extra_allowed_roles=None, **kwargs):
        # Only ever passed by a trusted, authenticated, permission-gated
        # server-side caller — CoordinatorCreateAgentView passes {'agent'}
        # so a Coordinator can create Agents through this same serializer
        # (reusing its password hashing / client_request_id dedup / GPS
        # rounding logic) without weakening PUBLIC_REGISTRATION_ROLES for
        # the actual public, unauthenticated register_view, which never
        # passes this and behaves exactly as before.
        self._extra_allowed_roles = extra_allowed_roles or set()
        super().__init__(*args, **kwargs)

    def validate_role(self, value):
        if value not in (self.PUBLIC_REGISTRATION_ROLES | self._extra_allowed_roles):
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

        if attrs.get('role') == 'business' and not attrs.get('business_name', '').strip():
            raise serializers.ValidationError({"business_name": "A business name is required."})

        return attrs

    def _resolve_category_id(self, category_id, custom_category_name, custom_category_icon, category_type):
        """Shared by both the artisan and business branches of create()
        below — the only difference between them is which category_type
        a brand-new custom entry gets filed under, which is what actually
        keeps "Photography" (an artisan profession) and, say, a business
        calling itself "Photography Studio" from ever colliding as the
        same Category row."""
        if category_id:
            return category_id
        if custom_category_name:
            # The icon choice only applies to a genuinely NEW category —
            # get_or_create's `defaults` are ignored when a row already
            # matches, so an earlier registrant's (or a guessed) icon for
            # an existing category is never overwritten by this one.
            category_obj, _ = Category.objects.get_or_create(
                name__iexact=custom_category_name, category_type=category_type,
                defaults={'name': custom_category_name, 'material_icon': custom_category_icon, 'category_type': category_type},
            )
            return category_obj.id
        return None

    def create(self, validated_data):
        # 1. Pull category/business data out before creating the user
        category_id = validated_data.pop('category_id', None)
        custom_category_name = validated_data.pop('custom_category_name', '').strip()
        custom_category_icon = validated_data.pop('custom_category_icon', '').strip()
        business_name = validated_data.pop('business_name', '').strip()

        validated_data.pop('password_confirm')
        password = validated_data.pop('password')

        # 2. Create the User account
        user = User.objects.create_user(password=password, **validated_data)

        # 3. Create the ArtisanProfile/BusinessProfile with the correct category
        if user.role == 'artisan':
            resolved_category_id = self._resolve_category_id(
                category_id, custom_category_name, custom_category_icon, 'artisan'
            )
            ArtisanProfile.objects.create(
                user=user,
                category_id=resolved_category_id,
                verification_status='pending'
            )
        elif user.role == 'business':
            resolved_category_id = self._resolve_category_id(
                category_id, custom_category_name, custom_category_icon, 'business'
            )
            BusinessProfile.objects.create(
                user=user,
                business_name=business_name,
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
            # serial_number/account_status were missing entirely — the
            # mobile agent dashboard has always read `user.serial_number`
            # (falling back to a hardcoded "PENDING" placeholder), but
            # this serializer never actually sent it, so every agent saw
            # that placeholder regardless of whether they had a real
            # serial number. Both are read-only: an agent's own status
            # only ever changes via CoordinatorAgentStatusView, and the
            # serial number is assigned once at creation.
            'serial_number', 'account_status',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'role', 'is_verified', 'email_verified', 'registration_fee_paid',
            'serial_number', 'account_status', 'created_at', 'updated_at',
        ]


class PublicUserSerializer(serializers.ModelSerializer):
    """RBAC (item 11): what a caller with no administrative/oversight
    relationship to this account is allowed to see about it — used to
    nest a directory listing's owner (a public artisan/business search
    result, or a chat partner) instead of the full UserSerializer, which
    was leaking email, exact GPS, account_status, registration_fee_paid,
    email_verified, and serial_number to anyone who could hit a public
    endpoint or exchange one chat message. State/LGA are kept (a rough
    location is the whole point of a marketplace listing); exact
    latitude/longitude is not.

    Contexts that genuinely need more than this (Admin's own User CRUD,
    Coordinator/Agent oversight lists, or a user viewing their own
    profile) use UserSerializer/AdminUserSerializer instead — this is
    deliberately not a universal replacement for those."""
    state_details = StateLiteSerializer(source='state', read_only=True)
    lga_details = LGASerializer(source='lga', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'phone_number',
            'profile_picture', 'gender', 'state_details', 'lga_details',
        ]
        read_only_fields = fields


class AdminUserSerializer(serializers.ModelSerializer):
    """Full account detail for Admin's User CRUD (core.views.
    AdminUserDetailView) — includes account_status/is_active, which the
    regular self-service UserSerializer above deliberately omits (a user
    editing their own profile has no business seeing/setting those)."""
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
            'account_status', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """Deliberately far more permissive than UserUpdateSerializer below —
    role, state, account_status, and is_active are all editable here,
    which would be a serious privilege-escalation risk on any endpoint
    not already gated behind IsAdmin (core.views.AdminUserDetailView,
    itself the second deliberate exception to "every privileged write
    stays in Django Admin" — see AdminCreateCoordinatorView for the
    first)."""
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'phone_number', 'address', 'gender',
            'role', 'country', 'state', 'lga', 'account_status', 'is_active',
            'preferred_language',
        ]


class CoordinatorRegisteredUserUpdateSerializer(serializers.ModelSerializer):
    """What a Coordinator may edit on an artisan/business account they
    personally registered (core.views.CoordinatorRegisteredUserDetailView)
    — a small, deliberately conservative subset of AdminUserUpdateSerializer's
    fields. No role/account_status/is_active/email/state here: those stay
    Admin-only or go through the dedicated verify/deactivate actions — same
    reasoning as UserUpdateSerializer excluding them for a user's own
    self-service profile edit. LGA reassignment is handled separately in
    the view (needs cross-checking against the coordinator's own state,
    not a plain field validator)."""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_number', 'address', 'gender']


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
