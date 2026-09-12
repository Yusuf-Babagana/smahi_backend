# Drops the unique_active_coordinator_per_state constraint introduced in
# 0013, reversing the "one coordinator per state" rule: states may now hold
# multiple active/suspended coordinators (AdminCreateCoordinatorView assigns
# them freely), and coordinator/agent ownership is tracked via the permanent
# sponsor_coordinator FK instead of the DB backstop.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_backfill_referral_codes_and_sponsors'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='user',
            name='unique_active_coordinator_per_state',
        ),
    ]