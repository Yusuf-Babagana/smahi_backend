from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from core.models import ArtisanProfile, BusinessProfile, Category, ServiceTaxonomy


class Command(BaseCommand):
    help = (
        "Finds Category rows that only differ by letter case within the same "
        "category_type (e.g. 'Tailor' and 'tailor', both artisan categories) — "
        "the state that makes accounts.serializers._resolve_category_id's "
        "name__iexact lookup raise MultipleObjectsReturned during registration "
        "— and merges each group into a single row. Dry-run by default; pass "
        "--apply to actually write changes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help="Actually write the merge. Without this flag, only prints what would happen.",
        )

    def handle(self, *args, **options):
        apply = options['apply']

        groups = defaultdict(list)
        for cat in Category.objects.all().order_by('id'):
            groups[(cat.name.strip().lower(), cat.category_type)].append(cat)
        dupe_groups = [rows for rows in groups.values() if len(rows) > 1]

        if not dupe_groups:
            self.stdout.write(self.style.SUCCESS("No duplicate categories found. Nothing to do."))
            return

        self.stdout.write(f"Found {len(dupe_groups)} duplicate-name group(s).\n")

        # Reference counts per category, computed once up front — the group
        # member with the most real data already pointing at it becomes the
        # keeper, so a merge reassigns the fewest rows instead of picking an
        # arbitrary/empty duplicate and dragging everything onto it.
        ref_counts = defaultdict(int)
        for row in (
            Category.objects.annotate(n=Count('artisans', distinct=True) + Count('businesses', distinct=True) + Count('taxonomy_rows', distinct=True))
            .values('id', 'n')
        ):
            ref_counts[row['id']] = row['n']

        skipped = []
        planned = []
        for rows in dupe_groups:
            # Keeper = most real data already pointing at it (fewest rows to
            # reassign), tie-broken by lowest id (oldest/most likely canonical).
            keeper = sorted(rows, key=lambda c: (-ref_counts[c.id], c.id))[0]
            losers = [c for c in rows if c.id != keeper.id]

            # A duplicate that is the keeper's own parent can't be safely
            # deleted here: Category.parent cascades on delete, so removing
            # it without first reparenting the keeper risks deleting the
            # keeper too. Rather than guess the right new parent, skip the
            # whole group and leave it for manual review.
            if any(keeper.parent_id == loser.id for loser in losers):
                skipped.append((keeper, losers, "keeper's parent is one of the duplicates"))
                continue

            planned.append((keeper, losers))

        for keeper, losers in planned:
            loser_desc = ', '.join(f"{c.name!r} (id={c.id})" for c in losers)
            self.stdout.write(
                f"  KEEP {keeper.name!r} (id={keeper.id}, type={keeper.category_type}) "
                f"<- merge {loser_desc}"
            )
        for keeper, losers, reason in skipped:
            self.stdout.write(self.style.WARNING(
                f"  SKIP group around {keeper.name!r} (id={keeper.id}): {reason} — needs manual review"
            ))

        if not apply:
            self.stdout.write(self.style.WARNING(
                f"\nDry run only — no changes made. Re-run with --apply to merge the {len(planned)} group(s) above."
            ))
            return

        merged = 0
        with transaction.atomic():
            for keeper, losers in planned:
                loser_ids = [c.id for c in losers]

                # Don't silently lose data a duplicate had that the keeper
                # doesn't — fill the keeper's blank optional fields from
                # whichever loser has a value, never overwrite anything the
                # keeper already has set.
                for loser in losers:
                    for field in ('name_ha', 'description', 'icon', 'material_icon'):
                        if not getattr(keeper, field) and getattr(loser, field):
                            setattr(keeper, field, getattr(loser, field))
                keeper.save()

                # Repoint every real reference before deleting the duplicates.
                ArtisanProfile.objects.filter(category_id__in=loser_ids).update(category=keeper)
                BusinessProfile.objects.filter(category_id__in=loser_ids).update(category=keeper)
                ServiceTaxonomy.objects.filter(category_id__in=loser_ids).update(category=keeper)
                Category.objects.filter(parent_id__in=loser_ids).update(parent=keeper)

                Category.objects.filter(id__in=loser_ids).delete()
                merged += 1

        self.stdout.write(self.style.SUCCESS(f"\nMerged {merged} duplicate group(s)."))
        if skipped:
            self.stdout.write(self.style.WARNING(
                f"{len(skipped)} group(s) skipped and left untouched — see above."
            ))
