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


class PublicRegistrationIdempotencyTests(APITestCase):
    """Offline-first registration (app/register.tsx) can retry the exact
    same submission after a network drop that actually reached the server
    — the device queued it as still-pending (no response ever arrived) and
    syncs it again later. The retry must be recognized as the same
    submission and replayed, not rejected on the unique email constraint
    or (worse) allowed to create a second account."""

    def register(self, **overrides):
        payload = {
            'email': 'offline_user@test.com',
            'password': 'password123',
            'password_confirm': 'password123',
            'first_name': 'Offline',
            'last_name': 'User',
            'role': 'client',
            'client_request_id': 'device-xyz-0001',
        }
        payload.update(overrides)
        return self.client.post(REGISTER_URL, payload)

    def test_retrying_the_same_client_request_id_replays_success(self):
        first = self.register()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        self.assertNotIn('already_registered', first.data)

        second = self.register()
        self.assertEqual(second.status_code, status.HTTP_200_OK, second.data)
        self.assertTrue(second.data.get('already_registered'))
        self.assertEqual(second.data['user']['id'], first.data['user']['id'])
        self.assertIn('tokens', second.data, "replay must still hand back usable tokens")

        self.assertEqual(
            User.objects.filter(email='offline_user@test.com').count(), 1,
            "retrying the same client_request_id must not create a second account",
        )

    def test_missing_client_request_id_behaves_exactly_as_before(self):
        # Every caller before this feature existed sends no such field at
        # all — must not become required, and must not affect normal
        # duplicate-email rejection.
        payload = {
            'email': 'nokey_user@test.com', 'password': 'password123',
            'password_confirm': 'password123', 'first_name': 'No', 'last_name': 'Key',
            'role': 'client',
        }
        first = self.client.post(REGISTER_URL, payload)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)

        second = self.client.post(REGISTER_URL, payload)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)


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


class RegistrationCapturesGpsLocationTests(APITestCase):
    """Feature 8 (General Location Selection): an artisan's real GPS
    coordinate must be saved at registration time so they're immediately
    findable by every distance-based feature (nearest-search, the map,
    live tracking) — not only once they first open their dashboard and
    grant location permission there. Optional: registration must still
    work fine (and never store garbage coordinates) when a device has no
    GPS fix yet or the user denied permission."""

    def register(self, **overrides):
        payload = {
            'email': 'gpsuser@test.com',
            'password': 'password123',
            'password_confirm': 'password123',
            'first_name': 'Gps',
            'last_name': 'User',
            'role': 'artisan',
        }
        payload.update(overrides)
        return self.client.post('/api/auth/register/', payload)

    def test_latitude_and_longitude_are_saved_when_provided(self):
        response = self.register(latitude='11.945524', longitude='8.482703')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        user = User.objects.get(email='gpsuser@test.com')
        self.assertAlmostEqual(float(user.latitude), 11.945524, places=5)
        self.assertAlmostEqual(float(user.longitude), 8.482703, places=5)

    def test_registration_still_works_without_a_gps_fix(self):
        # No location permission granted / no fix yet — must not block
        # account creation, and must leave the fields genuinely blank
        # rather than some placeholder like 0,0.
        response = self.register()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        user = User.objects.get(email='gpsuser@test.com')
        self.assertIsNone(user.latitude)
        self.assertIsNone(user.longitude)

    def test_out_of_range_coordinates_are_rejected(self):
        response = self.register(latitude='999', longitude='8.482703')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='gpsuser@test.com').exists())

    def test_a_raw_high_precision_gps_reading_is_rounded_not_rejected(self):
        # Regression test for the actual production bug this was reported
        # against: a real expo-location fix routinely has far more than 6
        # decimal places (DecimalField(max_digits=9, decimal_places=6)) —
        # register.tsx sends the raw reading as-is, unlike saveCoordinates()
        # (the profile-update path) which already rounds client-side. This
        # used to fail with {"latitude": ["Ensure that there are no more
        # than 6 decimal places."]} instead of registering the account at all.
        response = self.register(latitude='11.945524382145678', longitude='8.482703912345678')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        user = User.objects.get(email='gpsuser@test.com')
        self.assertAlmostEqual(float(user.latitude), 11.945524, places=5)
        self.assertAlmostEqual(float(user.longitude), 8.482704, places=5)

class ProfileUpdateRoundsHighPrecisionCoordinatesTests(APITestCase):
    """Defense-in-depth companion to RegistrationCapturesGpsLocationTests —
    saveCoordinates() (the mobile app's only caller of this endpoint) already
    rounds to 6dp client-side, so this path isn't known to be broken today,
    but UserUpdateSerializer shares the exact same DecimalField precision
    limit, so it should fail the same way for the same reason if a future
    caller ever sends an unrounded value."""

    def test_high_precision_coordinates_are_rounded_not_rejected(self):
        user = User.objects.create_user(
            email='profilegps@test.com', password='pass12345',
            first_name='Profile', last_name='Gps', role='client',
        )
        self.client.force_authenticate(user)
        response = self.client.patch('/api/auth/profile/', {
            'latitude': '11.945524382145678',
            'longitude': '8.482703912345678',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        user.refresh_from_db()
        self.assertAlmostEqual(float(user.latitude), 11.945524, places=5)
        self.assertAlmostEqual(float(user.longitude), 8.482704, places=5)
