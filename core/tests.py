"""
Booking API tests — the mobile contract, role gates, and the status
state machine. Mirrors the payloads sent by the React Native app
(app/booking/[artisanId].tsx and app/artisan/dashboard.tsx).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ArtisanProfile, Booking

User = get_user_model()

BOOKINGS_URL = '/api/bookings/'


def future_date(days=1):
    return (timezone.now() + timedelta(days=days)).date().isoformat()


class BookingTestBase(APITestCase):

    def setUp(self):
        self.client_user = User.objects.create_user(
            email='client@test.com', password='pass12345',
            first_name='Test', last_name='Client', role='client'
        )
        self.artisan_user = User.objects.create_user(
            email='artisan@test.com', password='pass12345',
            first_name='Test', last_name='Artisan', role='artisan'
        )
        self.artisan_profile = ArtisanProfile.objects.create(user=self.artisan_user)

    def make_booking(self, **overrides):
        defaults = dict(
            client=self.client_user,
            artisan=self.artisan_user,
            service_description='Fix leaking sink',
            address='12 Test Street',
            scheduled_date=timezone.now() + timedelta(days=1),
            status='pending',
        )
        defaults.update(overrides)
        return Booking.objects.create(**defaults)

    def mobile_payload(self, **overrides):
        payload = {
            'artisan': self.artisan_user.id,
            'date': future_date(),
            'time': '09:30',
            'description': 'My kitchen sink is leaking',
            'location': '12 Test Street, Kano',
        }
        payload.update(overrides)
        return payload


class BookingCreateTests(BookingTestBase):

    def test_client_creates_booking_with_mobile_payload(self):
        self.client.force_authenticate(self.client_user)
        response = self.client.post(BOOKINGS_URL, self.mobile_payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        booking = Booking.objects.get()
        self.assertEqual(booking.client, self.client_user)
        self.assertEqual(booking.artisan, self.artisan_user)
        self.assertEqual(booking.service_description, 'My kitchen sink is leaking')
        self.assertEqual(booking.address, '12 Test Street, Kano')
        self.assertEqual(booking.status, 'pending')
        local = timezone.localtime(booking.scheduled_date)
        self.assertEqual(local.date().isoformat(), future_date())
        self.assertEqual(local.strftime('%H:%M'), '09:30')
        self.assertIsNone(booking.total_cost)
        self.assertIsNone(booking.duration_hours)

    def test_legacy_payload_still_accepted(self):
        self.client.force_authenticate(self.client_user)
        response = self.client.post(BOOKINGS_URL, {
            'artisan': self.artisan_user.id,
            'service_description': 'Rewire the shop',
            'address': '5 Legacy Road',
            'scheduled_date': (timezone.now() + timedelta(days=2)).isoformat(),
            'duration_hours': '2.5',
            'total_cost': '15000.00',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        booking = Booking.objects.get()
        self.assertEqual(booking.service_description, 'Rewire the shop')
        self.assertEqual(str(booking.total_cost), '15000.00')

    def test_creation_does_not_increment_total_bookings(self):
        self.client.force_authenticate(self.client_user)
        self.client.post(BOOKINGS_URL, self.mobile_payload())
        self.artisan_profile.refresh_from_db()
        self.assertEqual(self.artisan_profile.total_bookings, 0)

    def test_artisan_cannot_create_booking(self):
        self.client.force_authenticate(self.artisan_user)
        response = self.client.post(BOOKINGS_URL, self.mobile_payload())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_book_a_non_artisan(self):
        other_client = User.objects.create_user(
            email='other@test.com', password='pass12345',
            first_name='Other', last_name='Client', role='client'
        )
        self.client.force_authenticate(self.client_user)
        response = self.client.post(
            BOOKINGS_URL, self.mobile_payload(artisan=other_client.id)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Booking.objects.count(), 0)

    def test_cannot_book_artisan_without_profile(self):
        no_profile = User.objects.create_user(
            email='noprofile@test.com', password='pass12345',
            first_name='No', last_name='Profile', role='artisan'
        )
        self.client.force_authenticate(self.client_user)
        response = self.client.post(
            BOOKINGS_URL, self.mobile_payload(artisan=no_profile.id)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_book_inactive_artisan(self):
        self.artisan_user.is_active = False
        self.artisan_user.save()
        self.client.force_authenticate(self.client_user)
        response = self.client.post(BOOKINGS_URL, self.mobile_payload())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_past_date_rejected(self):
        self.client.force_authenticate(self.client_user)
        past = (timezone.now() - timedelta(days=1)).date().isoformat()
        response = self.client.post(BOOKINGS_URL, self.mobile_payload(date=past))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_description_rejected(self):
        self.client.force_authenticate(self.client_user)
        payload = self.mobile_payload()
        del payload['description']
        response = self.client.post(BOOKINGS_URL, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BookingListTests(BookingTestBase):

    def test_list_returns_mobile_aliases(self):
        self.make_booking()
        self.client.force_authenticate(self.client_user)
        response = self.client.get(BOOKINGS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data['results'][0]
        # Aliases the app reads
        self.assertEqual(item['description'], 'Fix leaking sink')
        self.assertEqual(item['location'], '12 Test Street')
        self.assertIn('date', item)
        self.assertIn('time', item)
        # Canonical fields stay for backward compatibility
        self.assertEqual(item['service_description'], 'Fix leaking sink')
        self.assertEqual(item['address'], '12 Test Street')
        self.assertIn('artisan_details', item)
        self.assertIn('client_details', item)
        # Navigation ids: 'artisan' is the User id, 'artisan_profile_id'
        # is the ArtisanProfile pk the app's artisan screens use.
        self.assertEqual(item['artisan'], self.artisan_user.id)
        self.assertEqual(item['artisan_profile_id'], self.artisan_profile.id)

    def test_parties_only_see_their_own_bookings(self):
        booking = self.make_booking()
        outsider = User.objects.create_user(
            email='outsider@test.com', password='pass12345',
            first_name='Out', last_name='Sider', role='client'
        )
        self.client.force_authenticate(outsider)
        response = self.client.get(BOOKINGS_URL)
        self.assertEqual(response.data['count'], 0)

        self.client.force_authenticate(self.artisan_user)
        response = self.client.get(BOOKINGS_URL, {'artisan': self.artisan_user.id})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], booking.id)


class BookingStatusTransitionTests(BookingTestBase):

    def patch_status(self, booking, user, new_status, **extra):
        self.client.force_authenticate(user)
        return self.client.patch(
            f'{BOOKINGS_URL}{booking.id}/', {'status': new_status, **extra}
        )

    def test_artisan_accepts_pending(self):
        booking = self.make_booking()
        response = self.patch_status(booking, self.artisan_user, 'confirmed')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'confirmed')

    def test_artisan_declines_pending(self):
        booking = self.make_booking()
        response = self.patch_status(
            booking, self.artisan_user, 'cancelled',
            cancellation_reason='Fully booked that day'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertEqual(booking.cancellation_reason, 'Fully booked that day')

    def test_full_happy_path_and_jobs_counter(self):
        booking = self.make_booking()
        self.patch_status(booking, self.artisan_user, 'confirmed')
        self.patch_status(booking, self.artisan_user, 'in_progress')
        response = self.patch_status(booking, self.artisan_user, 'completed')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'completed')
        self.artisan_profile.refresh_from_db()
        self.assertEqual(self.artisan_profile.total_bookings, 1)

    def test_client_cannot_confirm(self):
        booking = self.make_booking()
        response = self.patch_status(booking, self.client_user, 'confirmed')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_client_cannot_complete(self):
        booking = self.make_booking(status='in_progress')
        response = self.patch_status(booking, self.client_user, 'completed')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_client_can_cancel_pending_and_confirmed(self):
        for initial in ('pending', 'confirmed'):
            booking = self.make_booking(status=initial)
            response = self.patch_status(booking, self.client_user, 'cancelled')
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_client_cannot_cancel_in_progress(self):
        booking = self.make_booking(status='in_progress')
        response = self.patch_status(booking, self.client_user, 'cancelled')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_artisan_cannot_skip_to_completed(self):
        booking = self.make_booking()
        response = self.patch_status(booking, self.artisan_user, 'completed')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_terminal_states_are_final(self):
        for terminal in ('completed', 'cancelled'):
            booking = self.make_booking(status=terminal)
            for party in (self.client_user, self.artisan_user):
                response = self.patch_status(booking, party, 'pending')
                self.assertEqual(
                    response.status_code, status.HTTP_400_BAD_REQUEST,
                    f'{terminal} booking was reopened by {party.role}'
                )

    def test_completing_twice_counts_once(self):
        booking = self.make_booking(status='in_progress')
        self.patch_status(booking, self.artisan_user, 'completed')
        # Re-sending the same status is a no-op, not an error
        response = self.patch_status(booking, self.artisan_user, 'completed')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.artisan_profile.refresh_from_db()
        self.assertEqual(self.artisan_profile.total_bookings, 1)

    def test_delete_is_not_allowed(self):
        booking = self.make_booking()
        self.client.force_authenticate(self.client_user)
        response = self.client.delete(f'{BOOKINGS_URL}{booking.id}/')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(Booking.objects.count(), 1)


class LocationDistanceTests(BookingTestBase):
    """Users save GPS coords via profile PATCH; artisan search returns
    Haversine distance against them (the '2 km away' feature)."""

    def test_user_can_save_own_coordinates(self):
        self.client.force_authenticate(self.artisan_user)
        response = self.client.patch('/api/auth/profile/', {
            'latitude': '12.000000', 'longitude': '8.516667',  # Kano
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.artisan_user.refresh_from_db()
        self.assertEqual(float(self.artisan_user.latitude), 12.0)
        self.assertEqual(float(self.artisan_user.longitude), 8.516667)

    def test_out_of_range_coordinates_rejected(self):
        self.client.force_authenticate(self.client_user)
        response = self.client.patch('/api/auth/profile/', {'latitude': '91', 'longitude': '8'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_profile_read_includes_coordinates(self):
        self.artisan_user.latitude = 12.0
        self.artisan_user.longitude = 8.5
        self.artisan_user.save()
        self.client.force_authenticate(self.artisan_user)
        response = self.client.get('/api/auth/profile/')
        self.assertEqual(float(response.data['latitude']), 12.0)

    def test_artisan_search_returns_distance_sorted(self):
        # Artisan A ~0 km from the client, artisan B ~55 km north
        self.artisan_user.latitude, self.artisan_user.longitude = 12.0, 8.5
        self.artisan_user.save()
        far_user = User.objects.create_user(
            email='far@test.com', password='pass12345',
            first_name='Far', last_name='Artisan', role='artisan',
        )
        far_user.latitude, far_user.longitude = 12.5, 8.5
        far_user.save()
        far_profile = ArtisanProfile.objects.create(user=far_user)

        response = self.client.get('/api/artisans/', {'latitude': 12.0, 'longitude': 8.5})
        results = response.data['results']
        self.assertEqual(results[0]['id'], self.artisan_profile.id)
        self.assertEqual(results[0]['distance'], 0.0)
        self.assertEqual(results[1]['id'], far_profile.id)
        self.assertAlmostEqual(results[1]['distance'], 55.6, delta=1.0)

        # max_distance filters the far one out
        response = self.client.get(
            '/api/artisans/', {'latitude': 12.0, 'longitude': 8.5, 'max_distance': 10}
        )
        ids = [a['id'] for a in response.data['results']]
        self.assertIn(self.artisan_profile.id, ids)
        self.assertNotIn(far_profile.id, ids)

    def test_use_saved_falls_back_to_stored_coords(self):
        self.artisan_user.latitude, self.artisan_user.longitude = 12.0, 8.5
        self.artisan_user.save()
        self.client_user.latitude, self.client_user.longitude = 12.0, 8.5
        self.client_user.save()
        self.client.force_authenticate(self.client_user)
        response = self.client.get('/api/artisans/', {'use_saved': 'true'})
        self.assertEqual(response.data['results'][0]['distance'], 0.0)


class ArtisanAvailabilityTests(BookingTestBase):
    """The dashboard 'Available for Jobs' toggle: PATCH artisans/{profile_id}/."""

    def profile_url(self):
        return f'/api/artisans/{self.artisan_profile.id}/'

    def test_owner_can_toggle_availability(self):
        self.client.force_authenticate(self.artisan_user)
        response = self.client.patch(self.profile_url(), {'is_available': False})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.artisan_profile.refresh_from_db()
        self.assertFalse(self.artisan_profile.is_available)

    def test_non_owner_cannot_update_profile(self):
        self.client.force_authenticate(self.client_user)
        response = self.client.patch(self.profile_url(), {'is_available': False})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_update_profile(self):
        response = self.client.patch(self.profile_url(), {'is_available': False})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_offline_artisan_hidden_from_public_list(self):
        self.artisan_profile.is_available = False
        self.artisan_profile.save()
        response = self.client.get('/api/artisans/')
        ids = [a['id'] for a in response.data['results']]
        self.assertNotIn(self.artisan_profile.id, ids)

    def test_offline_artisan_still_visible_to_self_and_by_detail(self):
        self.artisan_profile.is_available = False
        self.artisan_profile.save()
        # Dashboard lookup by user id keeps working
        response = self.client.get('/api/artisans/', {'user': self.artisan_user.id})
        self.assertEqual(response.data['count'], 1)
        self.assertFalse(response.data['results'][0]['is_available'])
        # Direct profile page keeps working
        response = self.client.get(self.profile_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_reads_expose_is_available(self):
        response = self.client.get('/api/artisans/')
        self.assertTrue(response.data['results'][0]['is_available'])
