from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import ArtisanProfile, BusinessProfile
from core.referrals import ACTIVE_STATUSES, effective_coordinator

User = get_user_model()


class Command(BaseCommand):
    """One-time transition helper for switching AgentArtisanListView/
    AgentBusinessListView from LGA-wide to ownership-based (registered_by)
    scoping. Run audit_referral_coverage FIRST to see the numbers this
    affects.

    A self-registered artisan/business (registered_by is None — nobody
    ever registered them through an agent) has no data anywhere saying who
    should own them. Left alone, ownership-based scoping makes them
    invisible to every agent the moment it ships. This command softens
    that one-time transition: for each self-registered provider, assigns
    registered_by to one of the ACTIVE agents currently covering their
    LGA, round-robin — so agents who were already collectively overseeing
    that LGA's roster keep a fair share of it, rather than one agent
    getting everything and the rest getting nothing (or everyone getting
    nothing). This is a one-time grandfather step; every NEW registration
    going forward is already correctly owned from the moment it's created
    (see AgentRegisterArtisanView/AgentRegisterBusinessView), so this
    command has nothing new to do on a second run except pick up any
    genuinely new self-registrations since the last run.

    An LGA with no currently-active agent falls back to that state's own
    standing coordinator (if any) — same as a coordinator registering
    someone directly, which AgentRegisterArtisanView already allows. No
    agent will see these, but the coordinator keeps oversight instead of
    losing them outright. Only truly orphaned (no active agent in the LGA
    AND no active coordinator in the state) stay unowned.

    Idempotent and safe to re-run: only ever touches rows where
    registered_by is still null.
    """

    help = (
        "Grandfathers self-registered artisans/businesses to an active "
        "agent currently covering their LGA (round-robin per LGA), falling "
        "back to the state's standing coordinator if no agent is active "
        "there, so ownership-based dashboard scoping doesn't wipe out "
        "every self-registered account's visibility on day one."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without writing anything.',
        )

    def _grandfather(self, label, Model, dry_run, coordinator_by_state):
        unowned = list(
            Model.objects.filter(registered_by__isnull=True, user__lga__isnull=False)
            .select_related('user').order_by('user_id')
        )
        if not unowned:
            self.stdout.write(f"  No unowned {label} to grandfather.")
            return 0, 0, 0

        by_lga = defaultdict(list)
        for profile in unowned:
            by_lga[profile.user.lga_id].append(profile)

        active_agents_by_lga = defaultdict(list)
        for agent in User.objects.filter(role='agent', account_status='active', lga__isnull=False).order_by('id'):
            active_agents_by_lga[agent.lga_id].append(agent)

        assigned, assigned_to_coordinator, orphaned = 0, 0, 0
        for lga_id, profiles in by_lga.items():
            agents = active_agents_by_lga.get(lga_id) or []
            if agents:
                for i, profile in enumerate(profiles):
                    agent = agents[i % len(agents)]
                    coord = effective_coordinator(agent)
                    self.stdout.write(
                        f"  {label} {profile.user.email} -> agent {agent.email}"
                        + (f" (coordinator {coord.email})" if coord else "")
                    )
                    if not dry_run:
                        profile.registered_by = agent
                        profile.save(update_fields=['registered_by'])
                        if coord is not None:
                            profile.user.sponsor_coordinator = coord
                            profile.user.save(update_fields=['sponsor_coordinator'])
                    assigned += 1
                continue

            # No active agent anywhere in this LGA — fall back to the
            # state's own standing coordinator (if any), same as a
            # coordinator registering someone directly (AgentRegisterArtisanView
            # allows this). No agent will see these, but the coordinator
            # keeps oversight instead of losing them outright.
            for profile in profiles:
                coord = coordinator_by_state.get(profile.user.state_id)
                if coord is None:
                    orphaned += 1
                    continue
                self.stdout.write(
                    f"  {label} {profile.user.email} -> coordinator {coord.email} "
                    f"(no active agent in their LGA)"
                )
                if not dry_run:
                    profile.registered_by = coord
                    profile.save(update_fields=['registered_by'])
                    profile.user.sponsor_coordinator = coord
                    profile.user.save(update_fields=['sponsor_coordinator'])
                assigned += 1
                assigned_to_coordinator += 1
        return assigned, assigned_to_coordinator, orphaned

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        with transaction.atomic():
            coordinator_by_state = {}
            for coord in User.objects.filter(
                role='state_coordinator', account_status__in=ACTIVE_STATUSES, state__isnull=False,
            ).order_by('-created_at'):
                # Most-recently-created wins if a state has several —
                # matches effective_coordinator()'s own tie-break.
                coordinator_by_state.setdefault(coord.state_id, coord)

            total_assigned, total_to_coordinator, total_orphaned = 0, 0, 0
            for label, Model in (('artisan', ArtisanProfile), ('business', BusinessProfile)):
                self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {label.capitalize()}s ==="))
                assigned, to_coordinator, orphaned = self._grandfather(label, Model, dry_run, coordinator_by_state)
                total_assigned += assigned
                total_to_coordinator += to_coordinator
                total_orphaned += orphaned

            summary = (
                f"assigned {total_assigned} accounts ({total_to_coordinator} of those "
                f"to a coordinator directly, no active agent in their LGA). "
                f"{total_orphaned} left unowned — no active agent AND no active "
                f"coordinator exists for them at all."
            )
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING(f"\nDRY RUN — would have {summary} Nothing was written."))
            else:
                self.stdout.write(self.style.SUCCESS(f"\n{summary[0].upper()}{summary[1:]}"))
