from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from locations.models import Country, State, LGA

User = get_user_model()


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
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
        reviews = self.reviews.all()
        if reviews.exists():
            total = sum(review.rating for review in reviews)
            self.rating = total / reviews.count()
            self.total_reviews = reviews.count()
            self.save()


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
    duration_hours = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0.5)])
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

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
