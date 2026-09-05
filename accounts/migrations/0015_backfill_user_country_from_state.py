from django.db import migrations


def backfill_country_from_state(apps, schema_editor):
    """One-time data fix for the "Unknown Country" bug: AgentRegisterArtisanView
    / AgentRegisterBusinessView / CoordinatorCreateAgentView all used to copy
    request.user.country_id verbatim onto every account they created. If the
    registering agent/coordinator's OWN country was ever null (a pre-existing
    data gap — e.g. an account created before country was consistently set),
    every artisan/business/agent they went on to register inherited that same
    gap, permanently showing "Unknown Country" on the client-facing artisan
    profile. Those three views now derive country from the state actually
    being assigned instead (see their own comments), which prevents this
    going forward — this migration repairs every account already affected.

    Every State already has its own `country` set (locations app's seed
    data) — a genuinely country-less State is not a real scenario this app
    supports, so this is a safe, unconditional backfill: any user with a
    state but no country gets that state's country, nothing else changes.
    A plain queryset .update() can't reference a joined field like
    state__country directly, hence the explicit loop + bulk_update.
    """
    User = apps.get_model('accounts', 'User')
    affected = list(User.objects.filter(country__isnull=True, state__isnull=False).select_related('state'))
    for user in affected:
        user.country_id = user.state.country_id
    if affected:
        User.objects.bulk_update(affected, ['country'])


def noop_reverse(apps, schema_editor):
    # update()-style backfills aren't meaningfully reversible (we never
    # recorded which rows were actually null beforehand) — reversing is a
    # deliberate no-op rather than re-nulling real data.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_user_serial_number_alter_user_account_status'),
    ]

    operations = [
        migrations.RunPython(backfill_country_from_state, noop_reverse),
    ]
