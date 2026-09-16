import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import VerificationRequest


class Command(BaseCommand):
    """One-time migration for the ID-verification-document public-exposure
    fix: moves any document files that are still sitting under the old,
    publicly-served MEDIA_ROOT/verification_documents/ into
    PRIVATE_MEDIA_ROOT, where they're only reachable through the
    authenticated serve_verification_document view.

    The DB-stored relative path (e.g. "verification_documents/id.jpg") does
    NOT change — only the physical file location does, since the field's
    storage backend (core.storage.private_media_storage) now resolves that
    same relative path against PRIVATE_MEDIA_ROOT instead of MEDIA_ROOT.

    Safe to re-run: already-migrated files are skipped.
    """

    help = (
        "Moves existing verification-document files from the public "
        "MEDIA_ROOT into PRIVATE_MEDIA_ROOT. Run once after deploying the "
        "storage fix, then again any time you're unsure it's fully applied."
    )

    def handle(self, *args, **options):
        old_root = Path(settings.MEDIA_ROOT)
        new_root = Path(settings.PRIVATE_MEDIA_ROOT)
        new_root.mkdir(parents=True, exist_ok=True)

        moved, already_private, missing = 0, 0, 0

        for req in VerificationRequest.objects.all():
            for field_name in ('document_image_1', 'document_image_2', 'document_image_3'):
                field_file = getattr(req, field_name)
                if not field_file:
                    continue

                relative_name = field_file.name  # e.g. "verification_documents/id.jpg"
                new_path = new_root / relative_name
                if new_path.exists():
                    already_private += 1
                    continue

                old_path = old_root / relative_name
                if not old_path.exists():
                    missing += 1
                    self.stdout.write(self.style.WARNING(
                        f"  Missing everywhere: VerificationRequest #{req.pk} {field_name} "
                        f"-> {relative_name}"
                    ))
                    continue

                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_path), str(new_path))
                moved += 1
                self.stdout.write(f"  Moved: {relative_name}")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Moved {moved}, already private {already_private}, missing {missing}."
        ))
        if missing:
            self.stdout.write(self.style.WARNING(
                "Files reported missing could not be found in either location "
                "— check MEDIA_ROOT/PRIVATE_MEDIA_ROOT paths on this server."
            ))
