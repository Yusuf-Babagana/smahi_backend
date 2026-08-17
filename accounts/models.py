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
        ('agent', 'Agent'),
        ('state_coordinator', 'State Coordinator'),
        ('admin', 'Admin'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended')
    ]

    username = None
    account_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='client')
    phone_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"
