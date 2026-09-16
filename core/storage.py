from django.conf import settings
from django.core.files.storage import FileSystemStorage

# No base_url is configured on purpose: this storage backs files (identity
# verification documents) that must never be reachable by a direct URL.
# Access only ever goes through core.views.serve_verification_document,
# which streams the file after checking the same ownership/role scoping as
# VerificationRequestViewSet.get_queryset().
private_media_storage = FileSystemStorage(location=str(settings.PRIVATE_MEDIA_ROOT))
