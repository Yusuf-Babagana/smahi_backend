from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import ArtisanProfile, BusinessProfile
from core.referrals import effective_coordinator

User = get_user_model()


class Command(BaseCommand):
    """Read-only report on how much artisan/business dashboard visibility
    coordinators/agents will gain or lose once AgentArtisanListView/
    AgentBusinessListView/AgentDashboardStatsView switch from territory
    (LGA/state) scoping to ownership (registered_by/sponsor_coordinator)
    scoping.

    Makes NO writes — safe to run directly against production. Run this
    BEFORE deploying that change so the real impact is a measured number,
    not a guess, and to know how many accounts backfill_provider_sponsors
    (a separate command) would actually recover.
    """

    help = (
        "Reports, without changing anything, how many artisans/businesses "
        "would lose agent/coordinator visibility once dashboard scoping "
        "switches from territory-based to ownership-based."
    )

    def handle(self, *args, **options):
        for label, Model in (('Artisans', ArtisanProfile), ('Businesses', BusinessProfile)):
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {label} ==="))
            total = Model.objects.count()
            self.stdout.write(f"Total {label.lower()}: {total}")

            self_registered = Model.objects.filter(registered_by__isnull=True).count()
            self.stdout.write(self.style.WARNING(
                f"  Self-registered (registered_by is None) — PERMANENTLY "
                f"invisible to every agent after deploy, no backfill "
                f"possible (there's no registering agent to attribute them "
                f"to): {self_registered}"
            ))

            agent_registered = Model.objects.filter(registered_by__isnull=False)
            agent_registered_count = agent_registered.count()
            self.stdout.write(f"  Registered by an agent/coordinator: {agent_registered_count}")

            already_visible = agent_registered.filter(user__sponsor_coordinator__isnull=False).count()
            self.stdout.write(self.style.SUCCESS(
                f"    Already visible to a coordinator today (their own "
                f"sponsor_coordinator is set): {already_visible}"
            ))

            gap = agent_registered.filter(user__sponsor_coordinator__isnull=True)
            gap_count = gap.count()
            self.stdout.write(self.style.WARNING(
                f"    Missing sponsor_coordinator — invisible to every "
                f"coordinator until backfilled: {gap_count}"
            ))

            recoverable = 0
            orphaned = 0
            for profile in gap.select_related('registered_by'):
                agent = profile.registered_by
                if agent is None or effective_coordinator(agent) is None:
                    orphaned += 1
                else:
                    recoverable += 1

            self.stdout.write(self.style.SUCCESS(
                f"      Recoverable by backfill_provider_sponsors: {recoverable}"
            ))
            self.stdout.write(self.style.ERROR(
                f"      Truly orphaned — registering agent has no "
                f"resolvable coordinator (their state currently has no "
                f"active/suspended coordinator at all): {orphaned}"
            ))

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Per-agent artisan-list size change ==="))
        agents = User.objects.filter(role='agent', account_status='active').select_related('lga')
        shrink_rows = []
        for agent in agents:
            if not agent.lga_id:
                continue
            old_count = ArtisanProfile.objects.filter(user__lga_id=agent.lga_id).count()
            new_count = ArtisanProfile.objects.filter(registered_by_id=agent.id).count()
            if old_count != new_count:
                shrink_rows.append((agent.email, agent.lga.name if agent.lga else '?', old_count, new_count))

        if shrink_rows:
            shrink_rows.sort(key=lambda r: r[2] - r[3], reverse=True)
            for email, lga_name, old_count, new_count in shrink_rows[:30]:
                self.stdout.write(f"  {email} ({lga_name}): {old_count} -> {new_count}")
            if len(shrink_rows) > 30:
                self.stdout.write(f"  ... and {len(shrink_rows) - 30} more active agents affected")
        else:
            self.stdout.write("  No change for any active agent.")

        self.stdout.write(self.style.MIGRATE_HEADING("\nDone. No data was modified.\n"))
