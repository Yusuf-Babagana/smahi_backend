from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import ActivityLog, ArtisanProfile, BusinessProfile
from core.referrals import effective_coordinator

User = get_user_model()

VERIFY_ACTIONS = {'artisan': 'artisan_verified', 'business': 'business_verified'}


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
        for label, kind, Model in (
            ('Artisans', 'artisan', ArtisanProfile), ('Businesses', 'business', BusinessProfile),
        ):
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {label} ==="))
            total = Model.objects.count()
            self.stdout.write(f"Total {label.lower()}: {total}")

            self_registered_qs = Model.objects.filter(registered_by__isnull=True)
            self_registered = self_registered_qs.count()
            self.stdout.write(self.style.WARNING(
                f"  Self-registered (registered_by is None): {self_registered}"
            ))

            # registered_by is only who clicked "register" — but an agent
            # verifying someone's ID in person (AgentVerifyArtisanView/
            # AgentVerifyBusinessView) is arguably an even stronger "who
            # actually oversees this person" signal, and it applies
            # regardless of how they originally signed up. Every approval
            # is logged in ActivityLog (actor=reviewer, target_user=them)
            # even when there's no registered_by at all.
            recoverable_via_verification = 0
            no_verification_history = 0
            action = VERIFY_ACTIONS[kind]
            for profile in self_registered_qs.select_related('user'):
                reviewer_id = ActivityLog.objects.filter(
                    action=action, target_user=profile.user,
                ).order_by('-created_at').values_list('actor_id', flat=True).first()
                if reviewer_id:
                    recoverable_via_verification += 1
                else:
                    no_verification_history += 1
            self.stdout.write(self.style.SUCCESS(
                f"    Of those, verified in person by a real agent/coordinator "
                f"at some point (recoverable via that reviewer instead — see "
                f"below): {recoverable_via_verification}"
            ))
            self.stdout.write(self.style.ERROR(
                f"    Never verified by anyone — PERMANENTLY unattributable, "
                f"no signal exists for who oversees them: {no_verification_history}"
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

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== Per-agent artisan-list size change "
            "(old LGA-wide -> new registered_by-only -> +verified-by-them) ==="
        ))
        agents = User.objects.filter(role='agent', account_status='active').select_related('lga')
        shrink_rows = []
        for agent in agents:
            if not agent.lga_id:
                continue
            old_count = ArtisanProfile.objects.filter(user__lga_id=agent.lga_id).count()
            registered_ids = set(
                ArtisanProfile.objects.filter(registered_by_id=agent.id).values_list('user_id', flat=True)
            )
            verified_user_ids = set(
                ActivityLog.objects.filter(action='artisan_verified', actor_id=agent.id)
                .values_list('target_user_id', flat=True)
            )
            with_verification_count = len(registered_ids | verified_user_ids)
            new_count = len(registered_ids)
            if old_count != new_count:
                shrink_rows.append((
                    agent.email, agent.lga.name if agent.lga else '?',
                    old_count, new_count, with_verification_count,
                ))

        if shrink_rows:
            shrink_rows.sort(key=lambda r: r[2] - r[3], reverse=True)
            for email, lga_name, old_count, new_count, with_verification_count in shrink_rows[:30]:
                self.stdout.write(f"  {email} ({lga_name}): {old_count} -> {new_count} -> {with_verification_count}")
            if len(shrink_rows) > 30:
                self.stdout.write(f"  ... and {len(shrink_rows) - 30} more active agents affected")
        else:
            self.stdout.write("  No change for any active agent.")

        self.stdout.write(self.style.MIGRATE_HEADING("\nDone. No data was modified.\n"))
