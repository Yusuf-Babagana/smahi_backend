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
RESET_REQUEST_URL = '/api/auth/password-reset/request/'
RESET_CONFIRM_URL = '/api/auth/password-reset/confirm/'


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


@patch('notifications.services.send_transactional_email', return_value=True)
class PasswordResetTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='resetme@test.com', password='oldpass123',
            first_name='Reset', last_name='Me', role='client'
        )

    def _sent_code(self, mock_send):
        html = mock_send.call_args.kwargs['html_content']
        start = html.index('<h2')
        start = html.index('>', start) + 1
        return html[start:start + 6]

    def test_request_sends_code_for_existing_email(self, mock_send):
        response = self.client.post(RESET_REQUEST_URL, {'email': 'resetme@test.com'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_send.called)
        self.assertEqual(mock_send.call_args.kwargs['subject'], 'Your S-MAHII password reset code')
        self.assertTrue(
            OTPCode.objects.filter(email='resetme@test.com', purpose='password_reset').exists()
        )

    def test_request_for_unknown_email_returns_same_200_and_sends_nothing(self, mock_send):
        response = self.client.post(RESET_REQUEST_URL, {'email': 'ghost@test.com'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(mock_send.called)
        # Identical body to the existing-email case — no enumeration signal
        known = self.client.post(RESET_REQUEST_URL, {'email': 'resetme@test.com'})
        self.assertEqual(response.data, known.data)

    def test_confirm_resets_password(self, mock_send):
        self.client.post(RESET_REQUEST_URL, {'email': 'resetme@test.com'})
        code = self._sent_code(mock_send)

        response = self.client.post(RESET_CONFIRM_URL, {
            'email': 'resetme@test.com', 'code': code, 'new_password': 'newpass456'
        })
        self.assertEqual(response.status_code, 200)

        # Old password dead, new one works
        old = self.client.post('/api/auth/login/', {'email': 'resetme@test.com', 'password': 'oldpass123'})
        self.assertEqual(old.status_code, 401)
        new = self.client.post('/api/auth/login/', {'email': 'resetme@test.com', 'password': 'newpass456'})
        self.assertEqual(new.status_code, 200)

        # Code consumed — cannot be replayed to set another password
        replay = self.client.post(RESET_CONFIRM_URL, {
            'email': 'resetme@test.com', 'code': code, 'new_password': 'hacker789'
        })
        self.assertEqual(replay.status_code, 400)

    def test_confirm_with_wrong_code_rejected(self, mock_send):
        self.client.post(RESET_REQUEST_URL, {'email': 'resetme@test.com'})
        code = self._sent_code(mock_send)
        wrong = '000000' if code != '000000' else '111111'

        response = self.client.post(RESET_CONFIRM_URL, {
            'email': 'resetme@test.com', 'code': wrong, 'new_password': 'newpass456'
        })
        self.assertEqual(response.status_code, 400)
        login = self.client.post('/api/auth/login/', {'email': 'resetme@test.com', 'password': 'oldpass123'})
        self.assertEqual(login.status_code, 200)

    def test_confirm_unknown_email_matches_wrong_code_response(self, mock_send):
        response = self.client.post(RESET_CONFIRM_URL, {
            'email': 'ghost@test.com', 'code': '123456', 'new_password': 'newpass456'
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], 'Invalid code. Please check and try again.')

    def test_short_password_rejected(self, mock_send):
        self.client.post(RESET_REQUEST_URL, {'email': 'resetme@test.com'})
        code = self._sent_code(mock_send)
        response = self.client.post(RESET_CONFIRM_URL, {
            'email': 'resetme@test.com', 'code': code, 'new_password': 'short'
        })
        self.assertEqual(response.status_code, 400)

    def test_reset_code_unusable_for_email_verification(self, mock_send):
        self.client.post(RESET_REQUEST_URL, {'email': 'resetme@test.com'})
        code = self._sent_code(mock_send)
        self.client.force_authenticate(self.user)
        response = self.client.post(CONFIRM_URL, {'code': code})
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)


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


class NotificationInboxTests(APITestCase):
    """Every Dashboard Must Be Connected (item 10) — a Notification has
    existed and been written to (emit()) since long before this, but
    there was no way to read it back from inside the app at all, only
    via Django Admin. These are the endpoints every dashboard's bell
    icon now calls."""
    LIST_URL = '/api/notifications/'
    UNREAD_COUNT_URL = '/api/notifications/unread-count/'
    MARK_ALL_READ_URL = '/api/notifications/mark-all-read/'

    def mark_read_url(self, notification_id):
        return f'/api/notifications/{notification_id}/read/'

    def setUp(self):
        self.user = User.objects.create_user(
            email='inbox_client@test.com', password='pass12345',
            first_name='Inbox', last_name='Client', role='client',
        )
        self.other_user = User.objects.create_user(
            email='inbox_other@test.com', password='pass12345',
            first_name='Other', last_name='Person', role='client',
        )

        from .models import Notification
        self.own_notification = Notification.objects.create(
            recipient=self.user, event_type='verification_approved',
            title='You are verified!', body='Congrats.',
        )
        self.other_notification = Notification.objects.create(
            recipient=self.other_user, event_type='verification_approved',
            title='You are verified!', body='Congrats.',
        )

    def test_list_scoped_to_the_requesting_user_only(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.LIST_URL)
        self.assertEqual(response.status_code, 200, response.data)
        ids = [n['id'] for n in response.data['results']]
        self.assertIn(self.own_notification.id, ids)
        self.assertNotIn(self.other_notification.id, ids)

    def test_list_requires_authentication(self):
        response = self.client.get(self.LIST_URL)
        self.assertEqual(response.status_code, 401)

    def test_unread_count(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.UNREAD_COUNT_URL)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['unread_count'], 1)

    def test_mark_one_read(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.mark_read_url(self.own_notification.id))
        self.assertEqual(response.status_code, 200, response.data)
        self.own_notification.refresh_from_db()
        self.assertTrue(self.own_notification.is_read)

    def test_cannot_mark_someone_elses_notification_read(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.mark_read_url(self.other_notification.id))
        self.assertEqual(response.status_code, 404)
        self.other_notification.refresh_from_db()
        self.assertFalse(self.other_notification.is_read)

    def test_mark_all_read(self):
        from .models import Notification
        Notification.objects.create(
            recipient=self.user, event_type='dispute_resolved', title='Reviewed', body='',
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.MARK_ALL_READ_URL)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['marked_read'], 2)
        self.assertEqual(Notification.objects.filter(recipient=self.user, is_read=False).count(), 0)
        # Someone else's unread notifications must be completely untouched.
        self.other_notification.refresh_from_db()
        self.assertFalse(self.other_notification.is_read)
