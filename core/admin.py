from django.contrib import admin
from django.db import transaction as db_transaction
from django.shortcuts import redirect
from django.utils import timezone
from .models import (
    Category, ArtisanProfile, VerificationRequest, Booking, Review,
    RegistrationPayment, PlatformSettings, DisputeReport, Wallet, WalletTransaction,
)
from notifications.events import emit


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
    actions = ['approve_verification', 'reject_verification']

    @admin.action(description='Approve verification (also sets is_verified on the user)')
    def approve_verification(self, request, queryset):
        from .services import approve_artisan_verification
        for profile in queryset:
            approve_artisan_verification(profile.user, reviewed_by=request.user)
        self.message_user(request, f'{queryset.count()} artisan(s) verified.')

    @admin.action(description='Reject verification')
    def reject_verification(self, request, queryset):
        # Bulk action, so this uses a generic reason. For a specific,
        # per-artisan reason, edit the matching VerificationRequest's
        # rejection_reason field directly instead.
        from .services import reject_artisan_verification
        for profile in queryset:
            reject_artisan_verification(
                profile.user, reviewed_by=request.user,
                reason='Your verification documents did not meet our requirements. Please contact support.'
            )
        self.message_user(request, f'{queryset.count()} artisan(s) rejected.')


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
    list_display = ['booking', 'rating', 'is_hidden', 'created_at']
    list_filter = ['rating', 'is_hidden', 'created_at']
    search_fields = ['booking__client__email', 'booking__artisan__email', 'comment']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['hide_reviews', 'unhide_reviews']

    @admin.action(description='Hide selected reviews (removes from public artisan profile)')
    def hide_reviews(self, request, queryset):
        updated = queryset.update(is_hidden=True)
        self.message_user(request, f'{updated} review(s) hidden.')

    @admin.action(description='Unhide selected reviews')
    def unhide_reviews(self, request, queryset):
        updated = queryset.update(is_hidden=False)
        self.message_user(request, f'{updated} review(s) unhidden.')


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


@admin.register(DisputeReport)
class DisputeReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'reporter', 'category', 'status', 'booking', 'created_at']
    list_filter = ['status', 'category', 'created_at']
    search_fields = ['reporter__email', 'reporter__first_name', 'reporter__last_name', 'description']
    readonly_fields = ['reporter', 'booking', 'category', 'description', 'resolved_by', 'resolved_at', 'created_at', 'updated_at']
    actions = ['mark_investigating', 'mark_resolved', 'mark_dismissed']
    date_hierarchy = 'created_at'

    @staticmethod
    def _notify_if_closed(dispute, new_status):
        if new_status in ('resolved', 'dismissed'):
            emit(
                'dispute_resolved',
                recipient=dispute.reporter,
                title='Your report has been reviewed',
                body=dispute.resolution_notes or f'Your dispute report has been marked as {new_status}.',
                related_object=dispute,
            )

    def save_model(self, request, obj, form, change):
        # Covers editing a single dispute's status directly in the change
        # form, not just the bulk actions below — both paths must stamp
        # resolved_by/resolved_at and notify consistently.
        status_changed = change and 'status' in form.changed_data
        super().save_model(request, obj, form, change)
        if status_changed and obj.status in ('resolved', 'dismissed'):
            update_fields = []
            if not obj.resolved_by:
                obj.resolved_by = request.user
                update_fields.append('resolved_by')
            if not obj.resolved_at:
                obj.resolved_at = timezone.now()
                update_fields.append('resolved_at')
            if update_fields:
                obj.save(update_fields=update_fields)
            self._notify_if_closed(obj, obj.status)

    def _bulk_transition(self, request, queryset, new_status):
        for dispute in queryset:
            dispute.status = new_status
            if new_status in ('resolved', 'dismissed'):
                dispute.resolved_by = request.user
                dispute.resolved_at = timezone.now()
            dispute.save()
            self._notify_if_closed(dispute, new_status)
        self.message_user(request, f'{queryset.count()} dispute(s) marked {new_status}.')

    @admin.action(description='Mark as investigating')
    def mark_investigating(self, request, queryset):
        self._bulk_transition(request, queryset, 'investigating')

    @admin.action(description='Mark as resolved')
    def mark_resolved(self, request, queryset):
        self._bulk_transition(request, queryset, 'resolved')

    @admin.action(description='Dismiss')
    def mark_dismissed(self, request, queryset):
        self._bulk_transition(request, queryset, 'dismissed')


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    """Read-only — balance is a cache maintained exclusively by
    core.services functions. Wallets are created automatically
    (Wallet.for_user()), never manually."""
    list_display = ['user', 'balance', 'currency', 'updated_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['user', 'balance', 'currency', 'created_at', 'updated_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    """Existing transactions are immutable (ledger integrity — editing a
    past entry would silently desync it from Wallet.balance). The one
    thing this admin CAN create is a manual_adjustment, which goes
    through the same atomic balance update as every other transaction
    type instead of a raw INSERT that would leave balance stale."""
    list_display = ['id', 'wallet', 'type', 'amount', 'status', 'created_at']
    list_filter = ['type', 'status', 'created_at']
    search_fields = ['wallet__user__email', 'description']
    date_hierarchy = 'created_at'
    actions = ['approve_withdrawal', 'reject_withdrawal']

    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing row — nothing is editable
            return [f.name for f in self.model._meta.fields]
        return ['created_by']  # set programmatically below, not via the form

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return

        obj.status = 'completed'
        obj.created_by = request.user
        with db_transaction.atomic():
            super().save_model(request, obj, form, change)
            wallet = Wallet.objects.select_for_update().get(pk=obj.wallet_id)
            wallet.balance = wallet.balance + obj.amount
            wallet.save(update_fields=['balance', 'updated_at'])

        if obj.amount > 0:
            emit(
                'wallet_credited', recipient=obj.wallet.user, title='Wallet credited',
                body=obj.description or f'Your wallet was adjusted by {obj.amount}.',
                related_object=obj,
            )

    @admin.action(description='Approve selected pending withdrawals')
    def approve_withdrawal(self, request, queryset):
        from .services import finalize_withdrawal
        count = 0
        for tx in queryset.filter(type='payout', status='pending'):
            finalize_withdrawal(tx, approve=True, admin_user=request.user)
            count += 1
        self.message_user(request, f'{count} withdrawal(s) approved.')

    @admin.action(description='Reject selected pending withdrawals')
    def reject_withdrawal(self, request, queryset):
        from .services import finalize_withdrawal
        count = 0
        for tx in queryset.filter(type='payout', status='pending'):
            finalize_withdrawal(tx, approve=False, admin_user=request.user)
            count += 1
        self.message_user(request, f'{count} withdrawal(s) rejected.')
