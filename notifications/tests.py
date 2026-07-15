from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import OTPCode
from .services import MAX_VERIFY_ATTEMPTS

User = get_user_model()

REQUEST_URL = '/api/auth/email/verify/request/'
CONFIRM_URL = '/api/auth/email/verify/confirm/'


@patch('notifications.services.send_transactional_email', return_value=True)
class EmailVerificationTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='client@test.com', password='pass12345',
            first_name='Test', last_name='Client', role='client'
        )
        self.client.force_authenticate(self.user)

    def _request_code(self):
        return self.client.post(REQUEST_URL)

    def _sent_code(self, mock_send):
        # The plaintext code only exists inside the email body — dig it out of the mock call
        html = mock_send.call_args.kwargs['html_content']
        start = html.index('<h2')
        start = html.index('>', start) + 1
        return html[start:start + 6]

    def test_request_creates_code_and_sends_email(self, mock_send):
        response = self._request_code()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_send.called)
        self.assertEqual(
            OTPCode.objects.filter(email=self.user.email, purpose='email_verify', is_used=False).count(),
            1
        )

    def test_confirm_with_correct_code_verifies_email(self, mock_send):
        self._request_code()
        code = self._sent_code(mock_send)

        response = self.client.post(CONFIRM_URL, {'code': code})
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertTrue(response.data['user']['email_verified'])
        # Code is consumed — cannot be replayed
        self.assertFalse(OTPCode.objects.filter(email=self.user.email, is_used=False).exists())

    def test_wrong_code_rejected_and_attempts_capped(self, mock_send):
        self._request_code()
        code = self._sent_code(mock_send)
        wrong = '000000' if code != '000000' else '111111'

        for _ in range(MAX_VERIFY_ATTEMPTS):
            response = self.client.post(CONFIRM_URL, {'code': wrong})
            self.assertEqual(response.status_code, 400)

        # Even the right code is refused after too many failures
        response = self.client.post(CONFIRM_URL, {'code': code})
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_expired_code_rejected(self, mock_send):
        self._request_code()
        code = self._sent_code(mock_send)
        OTPCode.objects.filter(email=self.user.email).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        response = self.client.post(CONFIRM_URL, {'code': code})
        self.assertEqual(response.status_code, 400)
        self.assertIn('expired', response.data['error'])

    def test_resend_cooldown(self, mock_send):
        self.assertEqual(self._request_code().status_code, 200)
        response = self._request_code()
        self.assertEqual(response.status_code, 429)

    def test_resend_after_cooldown_invalidates_previous_code(self, mock_send):
        self._request_code()
        old_code = self._sent_code(mock_send)
        OTPCode.objects.filter(email=self.user.email).update(
            created_at=timezone.now() - timedelta(minutes=2)
        )

        self.assertEqual(self._request_code().status_code, 200)

        response = self.client.post(CONFIRM_URL, {'code': old_code})
        self.assertEqual(response.status_code, 400)

    def test_already_verified_email_rejects_both_endpoints(self, mock_send):
        self.user.email_verified = True
        self.user.save(update_fields=['email_verified'])

        self.assertEqual(self._request_code().status_code, 400)
        self.assertEqual(self.client.post(CONFIRM_URL, {'code': '123456'}).status_code, 400)

    def test_missing_code_rejected(self, mock_send):
        response = self.client.post(CONFIRM_URL, {})
        self.assertEqual(response.status_code, 400)

    def test_endpoints_require_authentication(self, mock_send):
        self.client.force_authenticate(None)
        self.assertEqual(self._request_code().status_code, 401)
        self.assertEqual(self.client.post(CONFIRM_URL, {'code': '123456'}).status_code, 401)


class SendFailureTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='client2@test.com', password='pass12345',
            first_name='Test', last_name='Client', role='client'
        )
        self.client.force_authenticate(self.user)

    @patch('notifications.services.send_transactional_email', return_value=False)
    def test_provider_failure_returns_503_and_stores_nothing(self, mock_send):
        response = self.client.post(REQUEST_URL)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(OTPCode.objects.exists())

    @patch('notifications.services.send_transactional_email', return_value=False)
    def test_registration_survives_provider_failure(self, mock_send):
        self.client.force_authenticate(None)
        response = self.client.post('/api/auth/register/', {
            'email': 'newuser@test.com', 'password': 'pass12345',
            'password_confirm': 'pass12345',
            'first_name': 'New', 'last_name': 'Person', 'role': 'client',
        })
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['user']['email_verified'])

    @patch('notifications.services.send_transactional_email', return_value=True)
    def test_registration_sends_verification_otp(self, mock_send):
        self.client.force_authenticate(None)
        response = self.client.post('/api/auth/register/', {
            'email': 'newuser2@test.com', 'password': 'pass12345',
            'password_confirm': 'pass12345',
            'first_name': 'New', 'last_name': 'Person', 'role': 'client',
        })
        self.assertEqual(response.status_code, 201)
        self.assertTrue(mock_send.called)
        self.assertTrue(
            OTPCode.objects.filter(email='newuser2@test.com', purpose='email_verify').exists()
        )
