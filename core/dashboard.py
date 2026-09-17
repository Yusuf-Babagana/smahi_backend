import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone

from .models import ArtisanProfile, Booking, DisputeReport, RegistrationPayment, VerificationRequest

User = get_user_model()


def _weekly_trend(queryset, date_field, label):
    """A 7-day daily count trend (today inclusive) for `queryset`, in the
    {labels, datasets} shape unfold/components/chart/line.html expects.
    Returns (chart_json, is_empty) — is_empty is True when every day is
    zero, so the template can show a real empty state instead of a flat
    zero-line chart."""
    week_start = timezone.now().date() - timedelta(days=6)
    daily_counts = (
        queryset
        .filter(**{f'{date_field}__date__gte': week_start})
        .annotate(day=TruncDate(date_field))
        .values('day')
        .annotate(count=Count('id'))
    )
    counts_by_day = {row['day']: row['count'] for row in daily_counts}
    days = [week_start + timedelta(days=i) for i in range(7)]
    values = [counts_by_day.get(d, 0) for d in days]

    chart_json = json.dumps({
        'labels': [d.strftime('%a') for d in days],
        'datasets': [{'label': label, 'data': values}],
    })
    return chart_json, not any(values)


def dashboard_callback(request, context):
    """Populates the KPI cards, trend charts, and quick actions on the admin
    homepage.

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
        {
            'label': 'Total Users', 'value': f'{total_users:,}', 'icon': 'group',
            'href': reverse('admin:accounts_user_changelist'),
        },
        {
            'label': 'Active Artisans', 'value': f'{active_artisans:,}', 'icon': 'verified',
            'sub': 'Verification approved',
            'href': reverse('admin:core_artisanprofile_changelist') + '?verification_status__exact=approved',
        },
        {
            'label': 'Pending Verifications', 'value': f'{pending_verifications:,}', 'icon': 'pending_actions',
            'sub': 'Awaiting review',
            'href': reverse('admin:core_verificationrequest_changelist') + '?status__exact=pending',
        },
        {
            'label': 'Total Bookings', 'value': f'{total_bookings:,}', 'icon': 'event_available',
            'href': reverse('admin:core_booking_changelist'),
        },
        {
            'label': 'Registration Revenue', 'value': f'₦{revenue_kobo / 100:,.0f}', 'icon': 'payments',
            'sub': 'Lifetime, successful payments',
            'href': reverse('admin:core_registrationpayment_changelist') + '?status__exact=success',
        },
        {
            # "Open" here means open + investigating, which isn't a single
            # __exact value — linking to an unfiltered list is honest;
            # a filtered link would misrepresent what's actually shown.
            'label': 'Open Disputes', 'value': f'{open_disputes:,}', 'icon': 'report',
            'sub': 'Open + investigating',
            'href': reverse('admin:core_disputereport_changelist'),
        },
    ]

    context['bookings_chart'], context['bookings_chart_empty'] = _weekly_trend(
        Booking.objects, 'created_at', 'Bookings'
    )
    context['users_chart'], context['users_chart_empty'] = _weekly_trend(
        User.objects, 'date_joined', 'New users'
    )

    context['quick_actions'] = [
        {'label': 'Add User', 'icon': 'person_add', 'href': reverse('admin:accounts_user_add')},
        {
            'label': 'Review Verifications', 'icon': 'fact_check',
            'href': reverse('admin:core_verificationrequest_changelist') + '?status__exact=pending',
        },
        {'label': 'Manage Artisans', 'icon': 'engineering', 'href': reverse('admin:core_artisanprofile_changelist')},
        {'label': 'Manage Bookings', 'icon': 'event_available', 'href': reverse('admin:core_booking_changelist')},
        {'label': 'View Disputes', 'icon': 'report', 'href': reverse('admin:core_disputereport_changelist')},
        {'label': 'View Activity Logs', 'icon': 'history', 'href': reverse('admin:core_activitylog_changelist')},
    ]

    return context
