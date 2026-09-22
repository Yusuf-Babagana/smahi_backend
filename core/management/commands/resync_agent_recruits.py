from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    """Repairs a real production symptom ("coordinators are not seeing the
    artisans/business owners their agent registered, or some agents they
    registered") — traced to core.referrals.reassign_agent_coordinator
    only ever having updated the reassigned AGENT's own sponsor_coordinator,
    never the sponsor_coordinator already recorded on everyone that agent
    had recruited (AgentRegisterArtisanView/AgentRegisterBusinessView, or
    self-registration via the agent's own referral code — see
    accounts.serializers.UserRegistrationSerializer.create()). That field
    is set once, as a snapshot, and never updated on its own — so it goes
    stale the moment the recruiting agent is later moved to a different
    coordinator, or was unclaimed (no coordinator at all) at the moment
    they recruited someone. reassign_agent_coordinator itself now cascades
    this going forward (see core/referrals.py); this command is the
    one-time repair for whatever already went stale before that fix
    shipped.

    Deliberately keys off sponsor_agent (set on every recruit — any role,
    either registration path) rather than
    ArtisanProfile/BusinessProfile.registered_by, so unlike the older,
    narrower backfill_provider_sponsors command, this also: (a) fixes a
    non-null but STALE sponsor_coordinator, not just a missing one, and
    (b) covers Clients and self-registered-via-referral-code accounts,
    which registered_by never touches at all.

    Dry-run by default; pass --apply to actually write the fix.
    """

    help = "Re-syncs sponsor_coordinator on every recruit whose agent's own coordinator has since changed."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually write the fix. Without this flag, only reports what would change.',
        )

    def handle(self, *args, **options):
        apply = options['apply']

        agents = list(User.objects.filter(role='agent').only('id', 'email', 'sponsor_coordinator_id', 'sponsor_coordinator'))
        rows = []
        for agent in agents:
            mismatched = User.objects.filter(sponsor_agent_id=agent.id).exclude(sponsor_coordinator_id=agent.sponsor_coordinator_id)
            count = mismatched.count()
            if count:
                rows.append((agent, count))

        if not rows:
            self.stdout.write(self.style.SUCCESS(
                "Nothing to fix — every recruit's sponsor_coordinator already matches their agent's current one."
            ))
            return

        rows.sort(key=lambda r: -r[1])
        total = 0
        for agent, count in rows:
            coord = agent.sponsor_coordinator.email if agent.sponsor_coordinator_id else 'UNCLAIMED (no coordinator)'
            self.stdout.write(f"  {agent.email} -> {coord}: {count} recruit(s) currently out of sync")
            total += count
        self.stdout.write(f"\nTotal: {total} account(s) across {len(rows)} agent(s).")

        if not apply:
            self.stdout.write(self.style.WARNING(
                "\nDry run only — no changes made. Re-run with --apply to fix."
            ))
            return

        fixed = 0
        with transaction.atomic():
            for agent, _ in rows:
                fixed += User.objects.filter(
                    sponsor_agent_id=agent.id,
                ).exclude(sponsor_coordinator_id=agent.sponsor_coordinator_id).update(
                    sponsor_coordinator=agent.sponsor_coordinator,
                )
        self.stdout.write(self.style.SUCCESS(f"\nFixed {fixed} account(s)."))
