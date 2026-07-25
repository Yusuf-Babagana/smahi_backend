# /api/v1/ — reserved for genuinely new, standalone resources (per the
# marketplace-completion blueprint's versioning decision). Existing
# endpoints stay exactly where they are in core/urls.py, unversioned —
# moving them here would break the app already installed on real devices.
# Future phases (Wallet in Phase 4, etc.) register their new resources
# here too, not in the legacy unversioned router.
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DisputeReportViewSet, WalletView, WalletTransactionListView, WithdrawalRequestView

router = DefaultRouter()
router.register(r'disputes', DisputeReportViewSet, basename='dispute')

urlpatterns = [
    path('', include(router.urls)),
    path('wallet/', WalletView.as_view(), name='wallet'),
    path('wallet/transactions/', WalletTransactionListView.as_view(), name='wallet-transactions'),
    path('wallet/withdraw/', WithdrawalRequestView.as_view(), name='wallet-withdraw'),
]
