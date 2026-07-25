from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from locations.models import Country, State, LGA

User = get_user_model()


class Category(models.Model):
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='subcategories'
    )
    name = models.CharField(max_length=100)
    name_ha = models.CharField(max_length=100, blank=True, help_text="Hausa translation")
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class ArtisanProfile(models.Model):
    VERIFICATION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='artisan_profile')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='artisans')
    bio = models.TextField(blank=True)
    experience_years = models.PositiveIntegerField(default=0)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    service_countries = models.ManyToManyField(Country, related_name='service_artisans', blank=True)
    service_states = models.ManyToManyField(State, related_name='service_artisans', blank=True)
    service_lgas = models.ManyToManyField(LGA, related_name='service_artisans', blank=True)

    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default='pending'
    )
    # Artisan-controlled visibility switch (dashboard "Available for Jobs").
    # False hides the artisan from public search but not from their own
    # dashboard lookup or direct profile views.
    is_available = models.BooleanField(default=True)
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0.00), MaxValueValidator(5.00)]
    )
    total_reviews = models.PositiveIntegerField(default=0)
    total_bookings = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-rating', '-created_at']

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.category.name if self.category else 'No Category'}"

    def update_rating(self):
        # Review has no FK to ArtisanProfile — it relates to Booking, whose
        # artisan is the User, not this profile. self.reviews never existed
        # (this crashed with AttributeError on every review ever submitted,
        # which is the actual reason reviews were unreachable — not just
        # the missing frontend). Query through the real relationship, at
        # the DB level (Avg/Count) rather than pulling every row into
        # Python. Hidden (moderated) reviews don't count toward the rating.
        from django.db.models import Avg, Count
        agg = Review.objects.filter(
            booking__artisan=self.user, is_hidden=False
        ).aggregate(avg=Avg('rating'), count=Count('id'))
        self.rating = agg['avg'] or 0
        self.total_reviews = agg['count']
        self.save(update_fields=['rating', 'total_reviews'])


class VerificationRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    artisan = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='verification_requests',
        limit_choices_to={'role': 'artisan'}
    )
    document_image_1 = models.ImageField(upload_to='verification_documents/')
    document_image_2 = models.ImageField(upload_to='verification_documents/', blank=True, null=True)
    document_image_3 = models.ImageField(upload_to='verification_documents/', blank=True, null=True)
    additional_info = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True)

    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_verifications'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Verification Request - {self.artisan.get_full_name()} ({self.status})"


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='client_bookings',
        limit_choices_to={'role': 'client'}
    )
    artisan = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='artisan_bookings',
        limit_choices_to={'role': 'artisan'}
    )

    service_description = models.TextField()
    address = models.TextField()

    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, related_name='bookings')
    state = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, related_name='bookings')
    lga = models.ForeignKey(LGA, on_delete=models.SET_NULL, null=True, related_name='bookings')

    scheduled_date = models.DateTimeField()
    # Price/duration are agreed between client and artisan outside the app,
    # so they are unknown at request time and optional forever after.
    duration_hours = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0.5)]
    )
    total_cost = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)]
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    cancellation_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Booking #{self.id} - {self.client.get_full_name()} -> {self.artisan.get_full_name()}"


class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='review')
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    # Admin-only moderation flag — hidden reviews stay in the DB (so
    # ArtisanProfile.rating history is never silently rewritten) but are
    # excluded from the public artisan-reviews endpoint.
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Review for Booking #{self.booking.id} - {self.rating} stars"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        artisan_profile = self.booking.artisan.artisan_profile
        artisan_profile.update_rating()


class PlatformSettings(models.Model):
    """Singleton row of business rules that must be changeable without a
    deploy. Always read via PlatformSettings.current() — never query this
    model directly, and never hardcode a fee/threshold/window elsewhere."""

    registration_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=2500,
        help_text="Artisan registration fee in NGN (replaces the old hardcoded ARTISAN_REGISTRATION_FEE)."
    )

    # Service fee (owed by the artisan after a job completes — the job
    # payment itself stays off-platform, this is only the platform's cut).
    # Flat is the safer default: it's immune to under-reporting job value.
    # Percentage is opt-in via has_percentage_service_fee.
    service_fee_flat_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    service_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    has_percentage_service_fee = models.BooleanField(
        default=False,
        help_text="Off = flat fee (default, recommended). On = percentage of artisan-reported job value."
    )

    agent_commission_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    minimum_withdrawal = models.DecimalField(max_digits=10, decimal_places=2, default=1000)
    maximum_withdrawal = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    cancellation_window_hours = models.PositiveIntegerField(
        default=24, help_text="Hours before scheduled_date a client can cancel without penalty."
    )
    refund_window_days = models.PositiveIntegerField(default=7)

    supported_payment_gateways = models.JSONField(default=list, blank=True, help_text='e.g. ["paystack"]')
    maintenance_mode = models.BooleanField(default=False)

    vat_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='NGN')

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Platform Settings'
        verbose_name_plural = 'Platform Settings'

    def __str__(self):
        return 'Platform Settings'

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # the singleton row is never deletable

    @classmethod
    def current(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class RegistrationPayment(models.Model):
    """Tracks Paystack registration fee payments for artisans."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='registration_payments')
    reference = models.CharField(max_length=100, unique=True)
    amount = models.PositiveIntegerField(help_text="Amount in Kobo")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    paystack_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment {self.reference} - {self.user.email} - {self.status}"
