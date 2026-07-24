from django.contrib import admin
from django.shortcuts import redirect
from .models import Category, ArtisanProfile, VerificationRequest, Booking, Review, RegistrationPayment, PlatformSettings


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    """Singleton — every business rule (fees, thresholds, windows) lives
    here instead of a hardcoded constant, editable without a deploy."""
    fieldsets = (
        ('Registration', {'fields': ('registration_fee',)}),
        ('Service fee (charged to the artisan after a completed job — the job payment itself stays off-platform)', {
            'fields': ('has_percentage_service_fee', 'service_fee_flat_amount', 'service_fee_percentage'),
        }),
        ('Agent commission', {'fields': ('agent_commission_amount',)}),
        ('Wallet', {'fields': ('minimum_withdrawal', 'maximum_withdrawal')}),
        ('Booking policy', {'fields': ('cancellation_window_hours', 'refund_window_days')}),
        ('Platform', {'fields': ('supported_payment_gateways', 'maintenance_mode', 'vat_percentage', 'currency')}),
    )
    readonly_fields = ['updated_at']

    def has_add_permission(self, request):
        return not PlatformSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Only ever one row — skip the list page, go straight to editing it.
        obj = PlatformSettings.current()
        return redirect('admin:core_platformsettings_change', obj.pk)


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
    actions = ['mark_paid_and_activate']

    @staticmethod
    def _activate(user):
        if not user.registration_fee_paid or user.account_status != 'active':
            user.registration_fee_paid = True
            user.account_status = 'active'
            user.save(update_fields=['registration_fee_paid', 'account_status', 'updated_at'])

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Setting status to success must actually unlock the artisan: the
        # app checks user.registration_fee_paid, not this payment record.
        if obj.status == 'success':
            self._activate(obj.user)

    @admin.action(description='Mark as paid and activate the artisan account')
    def mark_paid_and_activate(self, request, queryset):
        for payment in queryset:
            if payment.status != 'success':
                payment.status = 'success'
                payment.save(update_fields=['status', 'updated_at'])
            self._activate(payment.user)
        self.message_user(request, f'{queryset.count()} payment(s) marked paid; accounts activated.')

    @admin.display(description='Amount (₦)')
    def amount_naira(self, obj):
        return f'{obj.amount / 100:,.0f}'  # stored in kobo

    @admin.display(boolean=True, description='Account activated')
    def fee_paid(self, obj):
        return obj.user.registration_fee_paid
