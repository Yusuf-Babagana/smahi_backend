from django.contrib import admin
from .models import Category, ArtisanProfile, VerificationRequest, Booking, Review, RegistrationPayment


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'name_ha', 'parent', 'icon', 'created_at']
    list_filter = ['parent']
    search_fields = ['name', 'name_ha', 'description']


@admin.register(ArtisanProfile)
class ArtisanProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'category', 'verification_status', 'rating', 'total_reviews', 'hourly_rate', 'created_at']
    list_filter = ['verification_status', 'category', 'created_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'bio']
    filter_horizontal = ['service_countries', 'service_states', 'service_lgas']
    readonly_fields = ['rating', 'total_reviews', 'total_bookings']


@admin.register(VerificationRequest)
class VerificationRequestAdmin(admin.ModelAdmin):
    list_display = ['artisan', 'status', 'reviewed_by', 'created_at', 'reviewed_at']
    list_filter = ['status', 'created_at', 'reviewed_at']
    search_fields = ['artisan__email', 'artisan__first_name', 'artisan__last_name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['id', 'client', 'artisan', 'status', 'scheduled_date', 'total_cost', 'created_at']
    list_filter = ['status', 'created_at', 'scheduled_date']
    search_fields = ['client__email', 'artisan__email', 'service_description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['booking', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['booking__client__email', 'booking__artisan__email', 'comment']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(RegistrationPayment)
class RegistrationPaymentAdmin(admin.ModelAdmin):
    list_display = ['reference', 'user', 'amount_naira', 'status', 'fee_paid', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['reference', 'user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['reference', 'amount', 'paystack_response', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'

    @admin.display(description='Amount (₦)')
    def amount_naira(self, obj):
        return f'{obj.amount / 100:,.0f}'  # stored in kobo

    @admin.display(boolean=True, description='Account activated')
    def fee_paid(self, obj):
        return obj.user.registration_fee_paid
