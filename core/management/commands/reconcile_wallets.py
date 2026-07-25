"""Nightly reconciliation job — the wallet-scale strategy from the
marketplace-completion blueprint. Wallet.balance is a cache updated
atomically alongside every WalletTransaction; this command is the
independent safety net that recomputes balance from the transaction log
itself (the real source of truth) and flags any drift, rather than
trusting the cache blindly forever.

Intended to run on a schedule (cron / PythonAnywhere scheduled task):
    python manage.py reconcile_wallets
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from core.models import Wallet, WalletTransaction


class Command(BaseCommand):
    help = "Recompute each wallet's balance from its completed transactions and report any mismatch."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix', action='store_true',
            help='Correct any drifted balance to match the transaction log (off by default — report only).',
        )

    def handle(self, *args, **options):
        mismatches = 0
        for wallet in Wallet.objects.all():
            real_total = WalletTransaction.objects.filter(
                wallet=wallet, status='completed'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            if real_total != wallet.balance:
                mismatches += 1
                self.stdout.write(self.style.WARNING(
                    f'MISMATCH: {wallet.user.email} — cached={wallet.balance} real={real_total}'
                ))
                if options['fix']:
                    wallet.balance = real_total
                    wallet.save(update_fields=['balance', 'updated_at'])
                    self.stdout.write(self.style.SUCCESS(f'  -> corrected to {real_total}'))

        if mismatches == 0:
            self.stdout.write(self.style.SUCCESS('All wallet balances match their transaction logs.'))
        else:
            suffix = '' if options['fix'] else ' (run with --fix to correct)'
            self.stdout.write(self.style.WARNING(f'{mismatches} wallet(s) had a mismatch{suffix}.'))
