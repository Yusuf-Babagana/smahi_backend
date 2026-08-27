from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from locations.models import Country, State, LGA

User = get_user_model()

# Offered to someone registering with a custom "Other" profession
# (accounts.serializers.UserRegistrationSerializer) when they'd rather pick
# an icon explicitly than let the app guess one from whatever they typed.
# Deliberately disjoint from the icons the app's keyword-matcher
# (src/constants/professionIcons.ts) already assigns to a *listed*
# profession — these read as generic/neutral rather than colliding with an
# icon a client already associates with a specific trade. Every name here
# is confirmed to exist in @expo/vector-icons' MaterialIcons set — keep
# both lists in sync if either changes.
DEFAULT_OTHER_ICONS = frozenset({
    'engineering', 'design-services', 'category', 'apps', 'star',
    'diamond', 'badge', 'palette', 'pets', 'groups', 'public', 'terrain',
})


class Category(models.Model):
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='subcategories'
    )
    name = models.CharField(max_length=100)
    name_ha = models.CharField(max_length=100, blank=True, help_text="Hausa translation")
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    # Deliberately separate from `icon` above (Ionicons-style, e.g.
    # "shirt-outline", often blank, consumed elsewhere/the website) — this
    # one is a MaterialIcons glyph name for the mobile app specifically.
    # Normally left blank: the app derives an icon from the category name
    # itself (src/constants/professionIcons.ts, keyword-matched, works for
    # any ordinary profession name with zero per-category setup). This
    # field only gets set when someone registering with a custom "Other"
    # profession explicitly picks one of the app's default icons for it
    # (see UserRegistrationSerializer) — an explicit human choice takes
    # priority over a guessed one wherever it's set.
    material_icon = models.CharField(max_length=50, blank=True)
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
    # Agent/coordinator who registered this artisan via AgentRegisterArtisanView.
    # Blank for artisans who self-registered through the public signup flow.
    registered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='artisans_registered'
    )
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
    # Average minutes between a booking request and this artisan's first
    # response (accept or decline) — see Booking.responded_at and
    # update_response_time() below. Null until they've responded to one.
    avg_response_minutes = models.PositiveIntegerField(null=True, blank=True)

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

    def update_response_time(self):
        from django.db.models import Avg, F, DurationField, ExpressionWrapper
        agg = Booking.objects.filter(
            artisan=self.user, responded_at__isnull=False
        ).annotate(
            response_time=ExpressionWrapper(F('responded_at') - F('created_at'), output_field=DurationField())
        ).aggregate(avg=Avg('response_time'))
        avg_delta = agg['avg']
        self.avg_response_minutes = int(avg_delta.total_seconds() // 60) if avg_delta else None
        self.save(update_fields=['avg_response_minutes'])


class Favorite(models.Model):
    """A client's saved artisan. Purely a client-side bookmark — no effect
    on search ranking, notifications, or anything artisan-facing."""
    client = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='favorites',
        limit_choices_to={'role': 'client'}
    )
    artisan = models.ForeignKey(ArtisanProfile, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('client', 'artisan')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.client.email} → {self.artisan}"


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
    # Set when this booking was cancelled inside PlatformSettings.cancellation_window_hours
    # of scheduled_date — see BookingUpdateSerializer.validate(). Purely informational:
    # there is no in-app job payment to charge a fee against.
    is_late_cancellation = models.BooleanField(default=False)
    # First time the artisan moved this booking away from 'pending' (accept
    # or decline) — feeds ArtisanProfile.avg_response_minutes. Never reset
    # once set, even if the booking is later cancelled.
    responded_at = models.DateTimeField(null=True, blank=True)

    # Foreground-only live location the artisan's app pushes (BookingViewSet.
    # update_location) while this booking is 'in_progress' — powers the
    # client's live tracking map. Cleared as soon as the booking leaves that
    # status (see BookingViewSet.perform_update) so a stale/last-known
    # position never lingers on the client's map after the job ends.
    live_latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    live_longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    live_location_updated_at = models.DateTimeField(null=True, blank=True)

    # Client-generated idempotency key — same purpose and pattern as
    # accounts.models.User.client_request_id (see that field's docstring):
    # offline-first booking (app/booking/[artisanId].tsx) can retry the same
    # submission after a network drop that actually reached the server, and
    # this is what lets that retry be recognized as "already done" instead
    # of creating a second booking for one real request. Deliberately
    # scoped unique-per-client (see Meta.constraints below), not globally
    # unique — unlike registration's client_request_id, a Booking already
    # has a natural owner to scope by, and scoping this way means two
    # different clients' devices independently generating the same token
    # (astronomically unlikely, but not worth leaving as a hard crash) can
    # never collide with each other, only ever replay their own request.
    client_request_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # DB-level backstop for BookingCreateSerializer.validate()'s
            # same check: that check runs before the transaction commits, so
            # two concurrent requests for the same artisan/slot can both pass
            # it and both insert. This constraint is what actually prevents
            # that — the second insert fails with IntegrityError, which
            # BookingViewSet.perform_create translates into the same clean
            # validation message.
            models.UniqueConstraint(
                fields=['artisan', 'scheduled_date'],
                condition=models.Q(status__in=['pending', 'confirmed', 'in_progress']),
                name='unique_active_booking_per_artisan_slot',
            ),
            # Scoped per-client (not global) — see client_request_id's own
            # docstring above for why. NULL client_request_id rows (every
            # booking created before this feature existed, and any caller
            # that doesn't send one) are exempt from this entirely, the same
            # way SQL never treats NULL as equal to NULL.
            models.UniqueConstraint(
                fields=['client', 'client_request_id'],
                name='unique_client_request_id_per_client',
            ),
        ]

    def __str__(self):
        return f"Booking #{self.id} - {self.client.get_full_name()} -> {self.artisan.get_full_name()}"


class BookingPhoto(models.Model):
    """A photo attached to a booking (e.g. a client showing the leaking
    pipe). Client-side already limits this to 4 per booking; enforced
    again server-side in the upload view, not just trusted from the app."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='booking_photos/')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Photo for Booking #{self.booking_id}"


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


class DisputeReport(models.Model):
    """A client or artisan reporting a problem. Deliberately minimal —
    this is a real complaint channel, not a full ticketing system (the
    earlier Tickets feature had no backend at all and was hidden this
    session). Resolution happens exclusively in Django Admin; the API
    only supports creating and reading your own reports."""

    CATEGORY_CHOICES = [
        ('payment', 'Payment Issue'),
        ('quality', 'Quality Issue'),
        ('no_show', 'No Show'),
        ('harassment', 'Harassment'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]

    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='disputes_filed')
    # Nullable: not every complaint is tied to a specific booking.
    booking = models.ForeignKey(
        Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='disputes'
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    # max_length on TextField isn't DB-enforced, but DRF's ModelSerializer
    # picks it up as a real input-length validator — cheap spam/abuse guard.
    description = models.TextField(max_length=2000)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    resolution_notes = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='disputes_resolved'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status'])]

    def __str__(self):
        return f"Dispute #{self.id} - {self.reporter.email} ({self.status})"


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


class TranslationCache(models.Model):
    """Content-addressed translation cache shared by chat, notifications,
    and any future translation consumer. Keyed by (source, target, content
    hash) — NOT by message id — so identical text is reused across every
    message/conversation that needs the same source->target pair, per the
    automatic-translation feature's cost-optimization requirement.

    Populated/read exclusively through core.translation.translation_service.
    """
    source_language = models.CharField(max_length=10)
    target_language = models.CharField(max_length=10)
    source_text_hash = models.CharField(max_length=64, db_index=True)  # sha256(source_text)
    source_text = models.TextField()
    translated_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('source_language', 'target_language', 'source_text_hash')]
        indexes = [models.Index(fields=['source_language', 'target_language', 'source_text_hash'])]

    def __str__(self):
        return f"{self.source_language}->{self.target_language}: {self.source_text[:40]}"
