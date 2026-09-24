from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from .services import approve_artisan_verification, approve_business_verification, get_registration_fee_naira

User = get_user_model()


@staff_member_required
@require_POST
def verify_user_from_dashboard(request, user_id):
    """POST-only action behind the admin dashboard's "Pending verification"
    widget (core/dashboard.py, templates/admin/index.html). Session-
    authenticated like the rest of Django Admin — @staff_member_required
    is the same gate every other admin page uses — unlike core.views.
    AdminVerifyUserView, which is the JWT-only mobile-app equivalent.
    Both route through the same approve_artisan_verification/
    approve_business_verification functions (core/services.py) so they
    enforce identical rules, e.g. the registration-fee-paid check below."""
    target_user = get_object_or_404(User, id=user_id, role__in=['artisan', 'business'])

    if getattr(settings, 'PAYSTACK_SECRET_KEY', '') and not target_user.registration_fee_paid:
        messages.error(
            request,
            f'Cannot verify {target_user.get_full_name() or target_user.email}: '
            f'registration fee of ₦{get_registration_fee_naira():,} has not been paid.',
        )
        return redirect(reverse('admin:index'))

    if target_user.role == 'artisan':
        approve_artisan_verification(target_user, reviewed_by=request.user)
    else:
        approve_business_verification(target_user, reviewed_by=request.user)

    messages.success(request, f'{target_user.get_full_name() or target_user.email} is now verified.')
    return redirect(reverse('admin:index'))
