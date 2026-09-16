from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import ArtisanProfile, BusinessProfile
from core.referrals import effective_coordinator

User = get_user_model()


class Command(BaseCommand):
    """One-time companion to the ownership-based dashboard-scoping fix
    (AgentArtisanListView/AgentBusinessListView/AgentDashboardStatsView —
    see core.referrals._recruited_query). Run audit_referral_coverage
    FIRST to see the exact numbers this would affect before running this.

    For every artisan/business that WAS registered by an agent/coordinator
    (registered_by is set) but whose own sponsor_coordinator is still
    unset, resolves that agent's current effective_coordinator() (their
    recorded sponsor_coordinator, or their state's current standing
    coordinator) and sets the provider's sponsor_coordinator to match —
    exactly what accounts/migrations/0017_backfill_referral_codes_and_
    sponsors.py already did for pre-existing Agent accounts when the
    referral network was introduced, extended here to the
    artisans/businesses that migration missed.

    Deliberately does NOT touch self-registered accounts (registered_by is
    None) — there is no registering agent to derive a coordinator from,
    and attributing them to some contextually-plausible coordinator would
    be a guess, not a fact. Those stay outside every coordinator's network,
    same as audit_referral_coverage reports them.

    Idempotent and safe to re-run: only ever touches rows where
    sponsor_coordinator is still null, and does nothing if there's nothing
    left to backfill.
    """

    help = (
        "Backfills sponsor_coordinator on artisans/businesses that were "
        "registered by an agent but never got the sponsor link the "
        "referral-network migration only applied to Agent accounts."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without writing anything.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        with transaction.atomic():
            updated, orphaned = 0, 0
            for label, Model in (('artisan', ArtisanProfile), ('business', BusinessProfile)):
                gap = Model.objects.filter(
                    registered_by__isnull=False, user__sponsor_coordinator__isnull=True,
                ).select_related('user', 'registered_by')

                for profile in gap:
                    coord = effective_coordinator(profile.registered_by)
                    if coord is None:
                        orphaned += 1
                        continue
                    profile.user.sponsor_coordinator = coord
                    profile.user.save(update_fields=['sponsor_coordinator'])
                    updated += 1
                    self.stdout.write(
                        f"  {label} {profile.user.email} -> coordinator {coord.email}"
                    )

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING(
                    f"\nDRY RUN — would have updated {updated} accounts "
                    f"({orphaned} left orphaned, no resolvable coordinator). "
                    f"Nothing was written."
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"\nUpdated {updated} accounts. {orphaned} left orphaned "
                    f"(their registering agent's state has no active/"
                    f"suspended coordinator at all — nothing to attribute "
                    f"them to)."
                ))
