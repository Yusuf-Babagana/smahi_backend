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

from .models import ArtisanProfile, Booking, Category
from .views import AIChatView

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


class FakeTranslationProvider:
    """Deterministic stand-in for OpenAITranslationProvider — no network,
    no cost, and lets tests assert exactly how many times it was called."""

    def __init__(self, translations=None, detections=None, fail=False):
        self.translations = translations or {}
        self.detections = detections or {}
        self.fail = fail
        self.translate_calls = 0
        self.detect_calls = 0

    def translate(self, text, source_language, target_language):
        self.translate_calls += 1
        if self.fail:
            raise RuntimeError("provider unavailable")
        return self.translations.get((text, source_language, target_language), f"[{target_language}] {text}")

    def detect_language(self, text):
        self.detect_calls += 1
        if self.fail:
            raise RuntimeError("provider unavailable")
        return self.detections.get(text, 'en')


class TranslationServiceTests(APITestCase):
    """core.translation.TranslationService — caching, fallback, and the
    behaviours the automatic-translation feature depends on for safety
    and cost control."""

    def setUp(self):
        from core.translation import TranslationService
        self.provider = FakeTranslationProvider()
        self.service = TranslationService(provider=self.provider)

    def test_same_language_is_a_passthrough(self):
        text, was_translated = self.service.translate("Hello", "en", "en")
        self.assertEqual(text, "Hello")
        self.assertFalse(was_translated)
        self.assertEqual(self.provider.translate_calls, 0)

    def test_empty_text_is_a_passthrough(self):
        text, was_translated = self.service.translate("", "en", "ha")
        self.assertEqual(text, "")
        self.assertFalse(was_translated)
        self.assertEqual(self.provider.translate_calls, 0)

    def test_translates_and_caches(self):
        from core.models import TranslationCache

        text, was_translated = self.service.translate("How are you?", "en", "ha")
        self.assertTrue(was_translated)
        self.assertEqual(text, "[ha] How are you?")
        self.assertEqual(self.provider.translate_calls, 1)
        self.assertEqual(TranslationCache.objects.count(), 1)

    def test_cache_hit_skips_the_provider(self):
        self.service.translate("How are you?", "en", "ha")
        self.assertEqual(self.provider.translate_calls, 1)

        # Same content/source/target again — even via a brand new service
        # instance, i.e. this is a DB-level cache, not an in-memory one.
        from core.translation import TranslationService
        second_service = TranslationService(provider=self.provider)
        text, was_translated = second_service.translate("How are you?", "en", "ha")

        self.assertEqual(text, "[ha] How are you?")
        self.assertTrue(was_translated)
        self.assertEqual(self.provider.translate_calls, 1, "second call should have hit the cache")

    def test_cache_does_not_mix_different_language_pairs(self):
        self.service.translate("Hello", "en", "ha")
        self.service.translate("Hello", "en", "fr")
        self.assertEqual(self.provider.translate_calls, 2)

    def test_provider_failure_falls_back_to_original_text(self):
        failing_provider = FakeTranslationProvider(fail=True)
        from core.translation import TranslationService
        service = TranslationService(provider=failing_provider)

        text, was_translated = service.translate("Hello", "en", "ha")

        self.assertEqual(text, "Hello")
        self.assertFalse(was_translated)

    def test_detect_language_failure_returns_empty_string(self):
        failing_provider = FakeTranslationProvider(fail=True)
        from core.translation import TranslationService
        service = TranslationService(provider=failing_provider)

        self.assertEqual(service.detect_language("Ina son sanin"), '')

    def test_detect_language_empty_text(self):
        self.assertEqual(self.service.detect_language(""), '')


class AgentRegisterArtisanStateScopingTests(APITestCase):
    """AgentRegisterArtisanView must force the new artisan into the AGENT'S
    OWN state/lga/country server-side — trusting whatever the client sends
    let a modified client register an artisan into a different state
    entirely, invisible to that state's own dashboards."""

    def setUp(self):
        from locations.models import Country, State

        self.country = Country.objects.create(name='Nigeria')
        self.kano = State.objects.create(name='Kano', country=self.country)
        self.lagos = State.objects.create(name='Lagos', country=self.country)

        self.agent = User.objects.create_user(
            email='kano_agent@test.com', password='pass12345',
            first_name='Kano', last_name='Agent', role='agent',
            country=self.country, state=self.kano,
        )
        self.stateless_agent = User.objects.create_user(
            email='stateless_agent@test.com', password='pass12345',
            first_name='Stateless', last_name='Agent', role='agent',
        )

    def register_url(self):
        return '/api/agent/register-artisan/'

    def test_new_artisan_lands_in_agents_own_state_even_if_client_sends_another(self):
        self.client.force_authenticate(user=self.agent)
        response = self.client.post(self.register_url(), {
            'email': 'spoofed_artisan@test.com',
            'first_name': 'Spoofed',
            'last_name': 'Artisan',
            # Attempting to place this artisan in Lagos despite a Kano agent registering them
            'state': self.lagos.id,
            'country': self.country.id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        new_artisan = User.objects.get(email='spoofed_artisan@test.com')
        self.assertEqual(new_artisan.state_id, self.kano.id, "server must force the agent's own state, not the client's")

    def test_agent_with_no_state_cannot_register_artisans(self):
        self.client.force_authenticate(user=self.stateless_agent)
        response = self.client.post(self.register_url(), {
            'email': 'orphan_artisan@test.com',
            'first_name': 'Orphan',
            'last_name': 'Artisan',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='orphan_artisan@test.com').exists())


class AIVerificationStatusTests(APITestCase):
    """The AI assistant must report an artisan's verification status from
    the real database, never invent or guess it (audit request: the AI and
    the Service Directory should agree — a client asking the AI about
    "Ahmed the mechanic" must get the same ✓/pending truth the artisan card
    in the app shows, not a plausible-sounding hallucination)."""

    def setUp(self):
        self.category = Category.objects.create(name='Mechanic')
        self.verified_user = User.objects.create_user(
            email='verified_mechanic@test.com', password='pass12345',
            first_name='Ahmed', last_name='Bello', role='artisan',
            is_verified=True,
        )
        ArtisanProfile.objects.create(user=self.verified_user, category=self.category)

        self.unverified_user = User.objects.create_user(
            email='unverified_mechanic@test.com', password='pass12345',
            first_name='Musa', last_name='Danjuma', role='artisan',
            is_verified=False,
        )
        ArtisanProfile.objects.create(user=self.unverified_user, category=self.category)

    def _mock_openai_tool_flow(self, mock_openai_cls, tool_name, tool_args):
        """Wires a fake OpenAI client through the exact two-call tool flow
        AIChatView uses, and returns the fake client so the test can inspect
        every message actually sent to the "model"."""
        import json as _json
        from types import SimpleNamespace

        fake_client = mock_openai_cls.return_value
        tool_call = SimpleNamespace(
            id='call_1',
            function=SimpleNamespace(name=tool_name, arguments=_json.dumps(tool_args)),
        )
        first_response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='', tool_calls=[tool_call],
        ))])
        second_response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='Here is what I found.', tool_calls=None,
        ))])
        fake_client.chat.completions.create.side_effect = [first_response, second_response]
        return fake_client

    def test_search_tool_result_carries_the_real_is_verified_value(self):
        """The is_verified S-MAHII sends back to the model must be the actual
        database value, not something the model could plausibly override."""
        from unittest.mock import patch

        with patch('core.views.openai.OpenAI') as mock_openai_cls:
            fake_client = self._mock_openai_tool_flow(mock_openai_cls, 'search_artisans', {'query': 'mechanic'})

            response = self.client.post('/api/ai/chat/', {'text': 'find me a mechanic'}, format='json')

            self.assertEqual(response.status_code, status.HTTP_200_OK)

            # Inspect exactly what was sent to the model for the second
            # (reply-writing) call — this is the real source of truth the
            # model is instructed to use. Both a verified and an unverified
            # "mechanic" exist (setUp) — order isn't guaranteed, so match by
            # name rather than assuming which comes first.
            import json as _json
            second_call_messages = fake_client.chat.completions.create.call_args_list[1].kwargs['messages']
            tool_messages = [m for m in second_call_messages if m['role'] == 'tool']
            self.assertEqual(len(tool_messages), 1)
            results = _json.loads(tool_messages[0]['content'])['data']['results']
            by_name = {r['name']: r['is_verified'] for r in results}
            self.assertTrue(by_name['Ahmed Bello'])
            self.assertFalse(by_name['Musa Danjuma'])

    def test_verification_status_rule_is_present_in_the_system_prompt(self):
        # A regression guard for the actual instruction text, not just its
        # presence — catches someone accidentally deleting/weakening it.
        prompt = AIChatView.SYSTEM_PROMPT
        self.assertIn('is_verified', prompt)
        self.assertIn('Never state, imply, or guess', prompt)

    def test_reinforcement_reminder_is_injected_before_the_reply_is_written(self):
        from unittest.mock import patch

        with patch('core.views.openai.OpenAI') as mock_openai_cls:
            fake_client = self._mock_openai_tool_flow(mock_openai_cls, 'view_artisan', {'name': 'Ahmed'})

            response = self.client.post('/api/ai/chat/', {'text': 'tell me about Ahmed'}, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            second_call_messages = fake_client.chat.completions.create.call_args_list[1].kwargs['messages']
            # The very last message before generation must be the reminder —
            # recency matters for how strongly a model follows an instruction.
            last_message = second_call_messages[-1]
            self.assertEqual(last_message['role'], 'system')
            self.assertIn('is_verified', last_message['content'])

    def test_view_artisan_reports_the_real_status_for_an_unverified_artisan(self):
        from unittest.mock import patch

        with patch('core.views.openai.OpenAI') as mock_openai_cls:
            fake_client = self._mock_openai_tool_flow(mock_openai_cls, 'view_artisan', {'name': 'Musa Danjuma'})

            self.client.post('/api/ai/chat/', {'text': 'tell me about Musa Danjuma'}, format='json')

            import json as _json
            second_call_messages = fake_client.chat.completions.create.call_args_list[1].kwargs['messages']
            tool_payload = [m for m in second_call_messages if m['role'] == 'tool'][0]['content']
            tool_data = _json.loads(tool_payload)
            self.assertFalse(tool_data['data']['is_verified'])


class AICardCompletenessTests(APITestCase):
    """The AI's artisan cards must carry the same fields the Service
    Directory's ArtisanCard shows: photo, name, profession, rating,
    verification, and distance — all from real data, computed the same way
    ArtisanViewSet already does (calculate_haversine_distance)."""

    def setUp(self):
        self.category = Category.objects.create(name='Electrician')
        # Kano city center-ish coordinates for the artisan; a nearby point
        # ~5km away for the "client".
        self.artisan_user = User.objects.create_user(
            email='distance_artisan@test.com', password='pass12345',
            first_name='Bala', last_name='Sani', role='artisan',
            is_verified=True, latitude=12.0000, longitude=8.5167,
        )
        self.artisan_profile = ArtisanProfile.objects.create(
            user=self.artisan_user, category=self.category,
        )

        self.no_gps_user = User.objects.create_user(
            email='no_gps_artisan@test.com', password='pass12345',
            first_name='Tanko', last_name='Yusuf', role='artisan',
            is_verified=False,
        )
        ArtisanProfile.objects.create(user=self.no_gps_user, category=self.category)

    def _mock_and_call(self, mock_openai_cls, payload):
        import json as _json
        from types import SimpleNamespace

        fake_client = mock_openai_cls.return_value
        tool_call = SimpleNamespace(
            id='call_1',
            function=SimpleNamespace(name='filter_by_category', arguments=_json.dumps({'category': 'Electrician'})),
        )
        first_response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='', tool_calls=[tool_call],
        ))])
        second_response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='Here you go.', tool_calls=None,
        ))])
        fake_client.chat.completions.create.side_effect = [first_response, second_response]

        response = self.client.post('/api/ai/chat/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        second_call_messages = fake_client.chat.completions.create.call_args_list[1].kwargs['messages']
        tool_payload = [m for m in second_call_messages if m['role'] == 'tool'][0]['content']
        return _json.loads(tool_payload)['data']['results']

    def test_distance_is_computed_when_client_sends_live_gps(self):
        from unittest.mock import patch

        with patch('core.views.openai.OpenAI') as mock_openai_cls:
            results = self._mock_and_call(mock_openai_cls, {
                'text': 'show me electricians',
                'latitude': 12.05, 'longitude': 8.52,
            })

        by_name = {r['name']: r for r in results}
        # Bala has GPS set — must get a real, non-null distance.
        self.assertIsNotNone(by_name['Bala Sani']['distance_km'])
        self.assertIsInstance(by_name['Bala Sani']['distance_km'], float)
        # Tanko has no GPS at all — must be null, never guessed.
        self.assertIsNone(by_name['Tanko Yusuf']['distance_km'])

    def test_distance_is_null_for_everyone_without_client_location(self):
        from unittest.mock import patch

        with patch('core.views.openai.OpenAI') as mock_openai_cls:
            results = self._mock_and_call(mock_openai_cls, {'text': 'show me electricians'})

        for r in results:
            self.assertIsNone(r['distance_km'])

    def test_saved_profile_location_is_used_when_no_live_gps_sent(self):
        from unittest.mock import patch

        self.client.force_authenticate(user=self.artisan_user)  # any authenticated user works
        self.artisan_user.latitude = 12.05
        self.artisan_user.longitude = 8.52
        self.artisan_user.save(update_fields=['latitude', 'longitude'])

        with patch('core.views.openai.OpenAI') as mock_openai_cls:
            results = self._mock_and_call(mock_openai_cls, {'text': 'show me electricians'})

        by_name = {r['name']: r for r in results}
        self.assertIsNotNone(by_name['Bala Sani']['distance_km'])

    def test_profile_picture_field_is_present_on_every_result(self):
        from unittest.mock import patch

        with patch('core.views.openai.OpenAI') as mock_openai_cls:
            results = self._mock_and_call(mock_openai_cls, {'text': 'show me electricians'})

        for r in results:
            self.assertIn('profile_picture', r)  # None here (no upload in the test), but key must exist

    def test_distance_rule_is_present_in_the_system_prompt(self):
        prompt = AIChatView.SYSTEM_PROMPT
        self.assertIn('distance_km', prompt)
        self.assertIn('DISTANCE RULE', prompt)


def _fake_completion(text):
    """A minimal stand-in for openai's ChatCompletion response shape, for
    the single-string-answer style calls (_semantic_category_lookup) rather
    than the tool-call flow _mock_openai_tool_flow covers above."""
    from types import SimpleNamespace
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class AISemanticSearchTests(APITestCase):
    """The AI must never rely on a user's exact wording already existing
    verbatim in the database — "lawyer" must find "Legal Services",
    "makaniki"/"mai gyaran mota" (Hausa) must find "Mechanic", etc. Primary
    mechanism: the AI's system prompt is given the real category vocabulary
    (English + Hausa) and instructed to map intent to the exact name itself
    — the model's own semantic understanding does the actual matching, not
    a hand-maintained synonym list. Backend query matching is broadened as
    a safety net alongside that, not a replacement for it."""

    def setUp(self):
        # _category_vocabulary() only advertises SUBcategories (parent__isnull=False)
        # to the AI — that's what artisans actually get assigned via the
        # registration picker (categoryAPI.getCategoriesFlat()), never a bare
        # top-level group. Give these a parent so the test data matches that.
        parent = Category.objects.create(name='Professional Services')
        self.legal = Category.objects.create(name='Legal Services', name_ha="Ayyukan Shari'a", parent=parent)
        self.mechanic = Category.objects.create(name='Auto Mechanic', name_ha='Makaniki', parent=parent)
        self.lawyer_user = User.objects.create_user(
            email='lawyer_test@test.com', password='pass12345',
            first_name='Amina', last_name='Bello', role='artisan',
        )
        ArtisanProfile.objects.create(user=self.lawyer_user, category=self.legal)
        self.mechanic_user = User.objects.create_user(
            email='mechanic_test@test.com', password='pass12345',
            first_name='Musa', last_name='Sani', role='artisan',
        )
        ArtisanProfile.objects.create(user=self.mechanic_user, category=self.mechanic)

    def test_system_prompt_includes_the_category_vocabulary_and_rule(self):
        prompt = AIChatView()._build_system_prompt()
        self.assertIn('Legal Services', prompt)
        self.assertIn('Auto Mechanic', prompt)
        self.assertIn('Makaniki', prompt)  # Hausa name included alongside English
        self.assertIn('SEMANTIC MATCHING RULE', prompt)

    def test_search_matches_a_category_by_its_hausa_name(self):
        # Covers both: a user typing the Hausa name directly, and the model
        # having already mapped an informal term to it.
        result = AIChatView()._execute_tool('search_artisans', {'query': 'Makaniki'})
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Musa Sani', names)
        self.assertNotIn('Amina Bello', names)

    def test_filter_by_category_matches_via_hausa_name(self):
        result = AIChatView()._execute_tool('filter_by_category', {'category': 'Makaniki'})
        self.assertEqual(result['data']['category'], 'Auto Mechanic')
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Musa Sani', names)

    def test_search_matches_individual_words_not_just_the_full_phrase(self):
        # "Auto Mechanic" doesn't contain "car mechanic near me" verbatim,
        # but shares the word "mechanic" — the safety-net word-split match.
        result = AIChatView()._execute_tool('search_artisans', {'query': 'car mechanic near me'})
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Musa Sani', names)

    def test_category_vocabulary_is_cached(self):
        from core.views import _category_vocabulary, _category_vocab_cache
        _category_vocab_cache['fetched_at'] = 0.0  # force a fresh fetch
        first = _category_vocabulary()
        Category.objects.create(name='Brand New Category', name_ha='Sabon Aiki', parent=self.legal.parent)
        second = _category_vocabulary()
        self.assertNotIn('Brand New Category', second)
        self.assertEqual(first, second)

    # --- Deterministic fallback: the model doesn't always follow the
    # prompt's mapping instruction (confirmed against production — "find me
    # a lawyer" was passed through as query="lawyer" verbatim, which shares
    # no substring with "Legal Services"/"Ayyukan Shari'a"). These cover the
    # backend-side safety net that catches that case. ---

    def test_search_falls_back_to_semantic_lookup_when_literal_match_fails(self):
        from unittest.mock import patch
        with patch('core.views.openai.OpenAI') as mock_openai_cls:
            fake_client = mock_openai_cls.return_value
            fake_client.chat.completions.create.return_value = _fake_completion('Legal Services')
            result = AIChatView()._execute_tool('search_artisans', {'query': 'lawyer'})
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Amina Bello', names)

    def test_filter_by_category_falls_back_to_semantic_lookup(self):
        from unittest.mock import patch
        with patch('core.views.openai.OpenAI') as mock_openai_cls:
            fake_client = mock_openai_cls.return_value
            fake_client.chat.completions.create.return_value = _fake_completion('Legal Services')
            result = AIChatView()._execute_tool('filter_by_category', {'category': 'attorney'})
        self.assertEqual(result['data']['category'], 'Legal Services')
        names = [r['name'] for r in result['data']['results']]
        self.assertIn('Amina Bello', names)

    def test_semantic_lookup_ignores_a_hallucinated_category_name(self):
        """A name the model invents that isn't in the real vocabulary must
        never be used as a filter — it would silently return nothing (or
        worse, a wrong match) instead of a visible failure."""
        from unittest.mock import patch
        with patch('core.views.openai.OpenAI') as mock_openai_cls:
            fake_client = mock_openai_cls.return_value
            fake_client.chat.completions.create.return_value = _fake_completion('Made Up Category')
            mapped = AIChatView()._semantic_category_lookup('something obscure')
        self.assertIsNone(mapped)

    def test_semantic_lookup_returns_none_without_raising_when_api_key_missing(self):
        with self.settings(OPENAI_API_KEY=''):
            mapped = AIChatView()._semantic_category_lookup('lawyer')
        self.assertIsNone(mapped)

    def test_semantic_lookup_returns_none_without_raising_on_api_error(self):
        from unittest.mock import patch
        with patch('core.views.openai.OpenAI') as mock_openai_cls:
            mock_openai_cls.return_value.chat.completions.create.side_effect = Exception('boom')
            mapped = AIChatView()._semantic_category_lookup('lawyer')
        self.assertIsNone(mapped)
