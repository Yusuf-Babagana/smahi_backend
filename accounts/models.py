from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from locations.models import Country, State, LGA
from core.languages import SUPPORTED_LANGUAGES


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        
        # 👇 ADD THIS LINE BACK 👇
        extra_fields.setdefault('account_status', 'active') 

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    ROLE_CHOICES = [
        ('client', 'Client'),
        ('artisan', 'Artisan'),
        # A registered business (hospital, hotel, restaurant, grocery/retail
        # store, etc.) — deliberately separate from 'artisan': a business
        # isn't an individual tradesperson offering a personal service, it's
        # an establishment with a business_name and its own category tree
        # (core.models.BusinessProfile / Category.category_type). See
        # UserRegistrationSerializer for how registration branches on this.
        ('business', 'Business'),
        ('agent', 'Agent'),
        ('state_coordinator', 'State Coordinator'),
        ('admin', 'Admin'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
        # Distinct from 'suspended' (temporary, reactivatable) — a Coordinator
        # dismissing an Agent "according to company rules" (CoordinatorAgentStatusView)
        # is meant to be final, not something the same reactivate button undoes.
        ('dismissed', 'Dismissed'),
    ]
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
    ]

    username = None
    account_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='client')
    phone_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    # Optional — never required, and blank for every account created before
    # this field existed. Powers a male/female fallback avatar (mobile app)
    # in place of initials when no profile_picture is set; blank falls back
    # to initials exactly as before this field existed.
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)

    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    state = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    lga = models.ForeignKey(LGA, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    is_verified = models.BooleanField(default=False)
    # Email ownership confirmed via OTP — independent of the artisan verification badge above
    email_verified = models.BooleanField(default=False)
    # Updated by PresenceHeartbeatView, pinged periodically by the frontend
    # while the app is foregrounded — not by Django middleware, since DRF's
    # JWT auth resolves request.user inside the view, after middleware runs.
    last_seen_at = models.DateTimeField(null=True, blank=True)
    # Artisans must pay a registration fee before their account is activated
    registration_fee_paid = models.BooleanField(default=False)
    # Default language messages are automatically translated into for this
    # user (chat.translation). Blank = never explicitly chosen — treated as
    # "unset" (falls back to detecting the sender's language instead of
    # trusting it) rather than as an implicit choice of English.
    preferred_language = models.CharField(max_length=10, choices=SUPPORTED_LANGUAGES, blank=True, default='')
    # Client-generated idempotency key (a UUID minted once on-device, per
    # registration attempt) — offline-first registration (register.tsx,
    # agent/register.tsx) can end up retrying the exact same submission
    # after a network drop that actually reached the server, or after the
    # queued draft is synced later. Without this, a retry either fails on
    # the unique email constraint (confusing the user into thinking
    # registration failed when it already succeeded) or, worse, could
    # create a second account for one real registration. Null+unique so
    # every pre-existing row (and any caller that doesn't send one) is
    # unaffected, but a real value can only ever be claimed once — see
    # UserRegistrationSerializer/register_view/AgentRegisterArtisanView for
    # the actual replay check.
    client_request_id = models.CharField(max_length=64, unique=True, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # Each state has at most one coordinator actually holding the
            # role at a time. Only 'active' and 'suspended' occupy the
            # seat — 'suspended' still counts (temporarily locked out, not
            # vacated; must be reactivated or dismissed before anyone else
            # can be assigned that state), but both 'dismissed' (explicit,
            # final end of the role — CoordinatorAgentStatusView/
            # AdminCoordinatorStatusView) and 'inactive' (Admin's generic
            # soft-delete, AdminUserDetailView) free the state up for a
            # replacement — a soft-deleted coordinator obviously shouldn't
            # keep blocking their state forever. AdminCreateCoordinatorView's
            # own pre-check gives a clean error before this constraint
            # would ever need to catch a race between two concurrent
            # creation attempts.
            models.UniqueConstraint(
                fields=['state'],
                condition=models.Q(role='state_coordinator', account_status__in=['active', 'suspended']),
                name='unique_active_coordinator_per_state',
            ),
        ]

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"
