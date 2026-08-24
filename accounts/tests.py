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


class CustomCategoryIconTests(APITestCase):
    """Registering with a custom "Other" profession lets the person pick a
    default icon for it (app/register.tsx step 4) — the choice must
    actually persist (Category.material_icon) and, critically, must never
    overwrite an icon an EARLIER registrant already set for the same
    category name."""

    def register(self, **overrides):
        from core.models import DEFAULT_OTHER_ICONS
        payload = {
            'email': 'custom_icon_test@example.com',
            'password': 'password123',
            'password_confirm': 'password123',
            'first_name': 'Custom',
            'last_name': 'Artisan',
            'role': 'artisan',
            'custom_category_name': 'Drone Photography Service',
            'custom_category_icon': sorted(DEFAULT_OTHER_ICONS)[0],
        }
        payload.update(overrides)
        return self.client.post(REGISTER_URL, payload)

    def test_chosen_icon_is_saved_on_the_new_category(self):
        from core.models import Category, ArtisanProfile

        response = self.register()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        category = Category.objects.get(name__iexact='Drone Photography Service')
        self.assertTrue(category.material_icon)

        artisan_profile = ArtisanProfile.objects.get(user__email='custom_icon_test@example.com')
        self.assertEqual(artisan_profile.category_id, category.id)

    def test_rejects_an_icon_not_in_the_offered_set(self):
        response = self.register(
            email='bad_icon_test@example.com',
            custom_category_icon='not-a-real-option',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_icon_is_optional(self):
        response = self.register(email='no_icon_test@example.com', custom_category_icon='')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_second_registrant_cannot_override_an_already_set_icon(self):
        from core.models import Category, DEFAULT_OTHER_ICONS

        first_icon, second_icon = sorted(DEFAULT_OTHER_ICONS)[:2]
        self.register(email='first_registrant@example.com', custom_category_icon=first_icon)

        # A second person types the exact same custom profession name and
        # picks a DIFFERENT icon — get_or_create must find the existing
        # category and leave its icon exactly as the first person set it.
        self.register(email='second_registrant@example.com', custom_category_icon=second_icon)

        category = Category.objects.get(name__iexact='Drone Photography Service')
        self.assertEqual(category.material_icon, first_icon)
        self.assertEqual(Category.objects.filter(name__iexact='Drone Photography Service').count(), 1)


class GenderFieldTests(APITestCase):
    """Gender is optional everywhere — registration, and editing an existing
    account — and powers a male/female fallback avatar (mobile app's Avatar
    component) in place of initials when no profile_picture is set."""

    def register(self, **overrides):
        payload = {
            'email': 'gender_test@example.com',
            'password': 'password123',
            'password_confirm': 'password123',
            'first_name': 'Gender',
            'last_name': 'Test',
            'role': 'client',
        }
        payload.update(overrides)
        return self.client.post(REGISTER_URL, payload)

    def test_registration_accepts_male(self):
        response = self.register(gender='male')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(User.objects.get(email='gender_test@example.com').gender, 'male')

    def test_registration_accepts_female(self):
        response = self.register(email='gender_test2@example.com', gender='female')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(User.objects.get(email='gender_test2@example.com').gender, 'female')

    def test_registration_without_gender_still_works(self):
        response = self.register(email='gender_test3@example.com')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(User.objects.get(email='gender_test3@example.com').gender, '')

    def test_registration_rejects_an_invalid_gender_value(self):
        response = self.register(email='gender_test4@example.com', gender='other')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_existing_user_can_set_gender_later_via_profile(self):
        user = User.objects.create_user(
            email='retro_gender@test.com', password='pass12345',
            first_name='Retro', last_name='User', role='client',
        )
        self.assertEqual(user.gender, '')  # never set — matches every pre-existing account

        self.client.force_authenticate(user=user)
        response = self.client.patch('/api/auth/profile/', {'gender': 'female'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        user.refresh_from_db()
        self.assertEqual(user.gender, 'female')

    def test_gender_is_visible_on_the_authenticated_users_own_profile(self):
        user = User.objects.create_user(
            email='visible_gender@test.com', password='pass12345',
            first_name='Visible', last_name='User', role='client', gender='male',
        )
        self.client.force_authenticate(user=user)
        response = self.client.get('/api/auth/profile/')
        self.assertEqual(response.data.get('gender'), 'male')
