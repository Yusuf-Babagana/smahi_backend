import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import ArtisanProfile, Booking, DisputeReport, RegistrationPayment, VerificationRequest

User = get_user_model()


def dashboard_callback(request, context):
    """Populates the KPI cards + bookings chart on the admin homepage.

    Wired up via UNFOLD['DASHBOARD_CALLBACK'] in settings.py; Unfold calls
    this with the index view's existing context (app_list, etc.) and
    renders whatever we add here through templates/admin/index.html —
    everything else about the admin (model list/change pages) is untouched.
    """
    total_users = User.objects.count()
    active_artisans = ArtisanProfile.objects.filter(verification_status='approved').count()
    pending_verifications = VerificationRequest.objects.filter(status='pending').count()
    total_bookings = Booking.objects.count()
    revenue_kobo = RegistrationPayment.objects.filter(status='success').aggregate(total=Sum('amount'))['total'] or 0
    open_disputes = DisputeReport.objects.exclude(status__in=['resolved', 'dismissed']).count()

    context['kpi_cards'] = [
        {'label': 'Total Users', 'value': f'{total_users:,}', 'icon': 'group'},
        {'label': 'Active Artisans', 'value': f'{active_artisans:,}', 'icon': 'verified', 'sub': 'Verification approved'},
        {'label': 'Pending Verifications', 'value': f'{pending_verifications:,}', 'icon': 'pending_actions', 'sub': 'Awaiting review'},
        {'label': 'Total Bookings', 'value': f'{total_bookings:,}', 'icon': 'event_available'},
        {'label': 'Registration Revenue', 'value': f'₦{revenue_kobo / 100:,.0f}', 'icon': 'payments', 'sub': 'Lifetime, successful payments'},
        {'label': 'Open Disputes', 'value': f'{open_disputes:,}', 'icon': 'report', 'sub': 'Open + investigating'},
    ]

    week_start = timezone.now().date() - timedelta(days=6)
    daily_counts = (
        Booking.objects
        .filter(created_at__date__gte=week_start)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
    )
    counts_by_day = {row['day']: row['count'] for row in daily_counts}
    days = [week_start + timedelta(days=i) for i in range(7)]

    context['bookings_chart'] = json.dumps({
        'labels': [d.strftime('%a') for d in days],
        'datasets': [{'label': 'Bookings', 'data': [counts_by_day.get(d, 0) for d in days]}],
    })

    return context
