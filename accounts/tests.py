"""Registration security tests — the public, unauthenticated
POST /api/auth/register/ endpoint must never be able to mint a
privileged (admin/agent/state_coordinator) account. See
UserRegistrationSerializer.validate_role for the fix.
"""
import tempfile

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

REGISTER_URL = '/api/auth/register/'


class PublicRegistrationRoleTests(APITestCase):
    def register(self, **overrides):
        payload = {
            'email': 'newuser@test.com',
            'password': 'password123',
            'password_confirm': 'password123',
            'first_name': 'New',
            'last_name': 'User',
            'role': 'client',
        }
        payload.update(overrides)
        return self.client.post(REGISTER_URL, payload)

    def test_client_role_is_allowed(self):
        response = self.register(role='client')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.get(email='newuser@test.com').role, 'client')

    def test_artisan_role_is_allowed(self):
        response = self.register(role='artisan', email='newartisan@test.com')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(User.objects.get(email='newartisan@test.com').role, 'artisan')

    def test_admin_role_is_rejected(self):
        response = self.register(role='admin')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='newuser@test.com').exists())

    def test_agent_role_is_rejected(self):
        response = self.register(role='agent')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='newuser@test.com').exists())

    def test_state_coordinator_role_is_rejected(self):
        response = self.register(role='state_coordinator')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='newuser@test.com').exists())

    def test_unrecognized_role_is_rejected(self):
        # Not even a real role, but proves the check runs before any
        # choices-based rejection would (defense in depth).
        response = self.register(role='lga_admin')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_role_defaults_to_client(self):
        payload = {
            'email': 'defaultrole@test.com',
            'password': 'password123',
            'password_confirm': 'password123',
            'first_name': 'Default',
            'last_name': 'Role',
        }
        response = self.client.post(REGISTER_URL, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(User.objects.get(email='defaultrole@test.com').role, 'client')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProfilePictureUploadTests(APITestCase):
    """The mobile app's only path for setting a profile photo is
    PATCH /api/auth/profile/ with multipart/form-data — profile_picture is
    just another UserUpdateSerializer field on the same endpoint every other
    account field uses, not a separate route. (app/artisan/profile.tsx used
    to POST to a /auth/profile/picture/ URL that never existed — every
    upload attempt 404'd silently; fixed to call this one instead.)

    MEDIA_ROOT is overridden to a throwaway temp dir — without this, actual
    uploaded test images land in the real project media/ folder (confirmed:
    the first run of these tests left two files in media/profile_pictures/
    on disk, since Django doesn't sandbox file storage during tests the way
    it does the database)."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='photo_user@test.com', password='pass12345',
            first_name='Photo', last_name='User', role='artisan',
        )

    @staticmethod
    def _tiny_png():
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        buf = BytesIO()
        Image.new('RGB', (2, 2), color='red').save(buf, format='PNG')
        buf.seek(0)
        return SimpleUploadedFile('avatar.png', buf.read(), content_type='image/png')

    def test_multipart_patch_updates_the_profile_picture(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            '/api/auth/profile/', {'profile_picture': self._tiny_png()}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.user.refresh_from_db()
        self.assertTrue(bool(self.user.profile_picture))
        self.assertTrue(response.data.get('profile_picture'))

    def test_uploading_a_picture_does_not_touch_other_profile_fields(self):
        self.user.first_name = 'Original'
        self.user.save(update_fields=['first_name'])

        self.client.force_authenticate(user=self.user)
        self.client.patch('/api/auth/profile/', {'profile_picture': self._tiny_png()}, format='multipart')

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Original')

    def test_unauthenticated_upload_is_rejected(self):
        response = self.client.patch(
            '/api/auth/profile/', {'profile_picture': self._tiny_png()}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
