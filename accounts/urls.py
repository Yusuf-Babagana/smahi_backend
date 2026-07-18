from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    register_view, login_view, ProfileView,
    request_email_verification_view, confirm_email_verification_view,
    password_reset_request_view, password_reset_confirm_view,
    initialize_registration_payment, verify_registration_payment,
)

urlpatterns = [
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('email/verify/request/', request_email_verification_view, name='email-verify-request'),
    path('email/verify/confirm/', confirm_email_verification_view, name='email-verify-confirm'),
    path('password-reset/request/', password_reset_request_view, name='password-reset-request'),
    path('password-reset/confirm/', password_reset_confirm_view, name='password-reset-confirm'),
    path('payments/initialize/', initialize_registration_payment, name='pay-initialize'),
    path('payments/verify/<str:reference>/', verify_registration_payment, name='pay-verify'),
]
