"""Chat + automatic translation tests — the mobile contract for
app/chat/[id].tsx: sending a message, and every participant reading it
back translated into their own preferred_language.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests import FakeTranslationProvider
from core.translation import translation_service
from .models import Conversation, Message

User = get_user_model()


class TranslationIntegrationTests(APITestCase):
    """Uses a FakeTranslationProvider (see core.tests) so these tests never
    hit the real OpenAI API — deterministic, free, and fast."""

    def setUp(self):
        self.hausa_user = User.objects.create_user(
            email='hausa@test.com', password='pass12345',
            first_name='Amina', last_name='Bello', role='client',
            preferred_language='ha',
        )
        self.english_user = User.objects.create_user(
            email='english@test.com', password='pass12345',
            first_name='John', last_name='Doe', role='client',
            preferred_language='en',
        )
        self.arabic_user = User.objects.create_user(
            email='arabic@test.com', password='pass12345',
            first_name='Yusuf', last_name='Ali', role='client',
            preferred_language='ar',
        )

        self.conversation = Conversation.objects.create()
        self.conversation.participants.add(self.hausa_user, self.english_user, self.arabic_user)

        self._original_provider = translation_service.provider
        self.provider = FakeTranslationProvider(
            translations={
                ("Ina son sanin yadda zan yi amfani da wannan app.", "ha", "en"):
                    "I want to know how to use this app.",
                ("Ina son sanin yadda zan yi amfani da wannan app.", "ha", "ar"):
                    "أريد أن أعرف كيفية استخدام هذا التطبيق.",
                ("How are you today?", "en", "ha"): "Yaya kake yau?",
                ("How are you today?", "en", "ar"): "كيف حالك اليوم؟",
            },
        )
        translation_service.provider = self.provider

    def tearDown(self):
        translation_service.provider = self._original_provider

    def messages_url(self):
        return f'/api/chat/messages/?conversation_id={self.conversation.id}'

    def send_as(self, user, text):
        self.client.force_authenticate(user=user)
        return self.client.post('/api/chat/messages/', {
            'conversation_id': self.conversation.id,
            'text': text,
        })

    def results(self, response):
        """DEFAULT_PAGINATION_CLASS wraps list responses as {results: [...]}."""
        data = response.data
        return data if isinstance(data, list) else data['results']

    # --- Send: original_language captured from the sender's own setting ---

    def test_send_captures_sender_preferred_language(self):
        response = self.send_as(self.hausa_user, "Ina son sanin yadda zan yi amfani da wannan app.")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        message = Message.objects.get(id=response.data['id'])
        self.assertEqual(message.original_language, 'ha')
        # Original text is never touched/overwritten by translation.
        self.assertEqual(message.text, "Ina son sanin yadda zan yi amfani da wannan app.")

    def test_send_falls_back_to_detection_when_sender_has_no_preference(self):
        undecided_user = User.objects.create_user(
            email='undecided@test.com', password='pass12345',
            first_name='New', last_name='User', role='client',
        )
        self.conversation.participants.add(undecided_user)
        self.provider.detections["Bonjour"] = 'fr'

        response = self.send_as(undecided_user, "Bonjour")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.provider.detect_calls, 1)
        message = Message.objects.get(id=response.data['id'])
        self.assertEqual(message.original_language, 'fr')

    # --- Read: same message, different language per recipient ---

    def test_each_recipient_reads_their_own_language(self):
        self.send_as(self.hausa_user, "Ina son sanin yadda zan yi amfani da wannan app.")

        self.client.force_authenticate(user=self.english_user)
        english_view = self.results(self.client.get(self.messages_url()))[0]
        self.assertEqual(english_view['text'], "I want to know how to use this app.")
        self.assertEqual(english_view['original_text'], "Ina son sanin yadda zan yi amfani da wannan app.")
        self.assertTrue(english_view['is_translated'])
        self.assertEqual(english_view['display_language'], 'en')

        self.client.force_authenticate(user=self.arabic_user)
        arabic_view = self.results(self.client.get(self.messages_url()))[0]
        self.assertEqual(arabic_view['text'], "أريد أن أعرف كيفية استخدام هذا التطبيق.")
        self.assertEqual(arabic_view['original_text'], "Ina son sanin yadda zan yi amfani da wannan app.")

        # The sender reading their own message back sees it unchanged.
        self.client.force_authenticate(user=self.hausa_user)
        own_view = self.results(self.client.get(self.messages_url()))[0]
        self.assertEqual(own_view['text'], "Ina son sanin yadda zan yi amfani da wannan app.")
        self.assertFalse(own_view['is_translated'])

    def test_translation_is_cached_across_requests(self):
        self.send_as(self.hausa_user, "Ina son sanin yadda zan yi amfani da wannan app.")

        self.client.force_authenticate(user=self.english_user)
        self.client.get(self.messages_url())
        self.client.get(self.messages_url())
        self.client.get(self.messages_url())

        self.assertEqual(self.provider.translate_calls, 1, "repeated reads should hit the DB cache")

    def test_provider_outage_still_delivers_the_original_message(self):
        self.provider.fail = True
        response = self.send_as(self.hausa_user, "Ina son sanin yadda zan yi amfani da wannan app.")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.english_user)
        view = self.results(self.client.get(self.messages_url()))[0]
        self.assertEqual(view['text'], "Ina son sanin yadda zan yi amfani da wannan app.")
        self.assertFalse(view['is_translated'])

    def test_conversation_preview_is_also_translated(self):
        self.send_as(self.hausa_user, "Ina son sanin yadda zan yi amfani da wannan app.")

        self.client.force_authenticate(user=self.english_user)
        response = self.client.get('/api/chat/conversations/')
        preview = self.results(response)[0]['last_message']
        self.assertEqual(preview['text'], "I want to know how to use this app.")

    def test_original_language_is_not_client_settable(self):
        self.client.force_authenticate(user=self.hausa_user)
        response = self.client.post('/api/chat/messages/', {
            'conversation_id': self.conversation.id,
            'text': 'How are you today?',
            'original_language': 'ar',  # attempt to spoof
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        message = Message.objects.get(id=response.data['id'])
        self.assertEqual(message.original_language, 'ha', "server-computed value must win, not the client's")


class PreferredLanguageSecurityTests(APITestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(
            email='a@test.com', password='pass12345',
            first_name='A', last_name='User', role='client', preferred_language='en',
        )
        self.user_b = User.objects.create_user(
            email='b@test.com', password='pass12345',
            first_name='B', last_name='User', role='client', preferred_language='en',
        )

    def test_user_cannot_change_another_users_language(self):
        self.client.force_authenticate(user=self.user_a)
        self.client.patch('/api/auth/profile/', {'preferred_language': 'fr'})

        self.user_b.refresh_from_db()
        self.assertEqual(self.user_b.preferred_language, 'en', "profile endpoint must only ever touch request.user")

    def test_user_can_change_their_own_language(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.patch('/api/auth/profile/', {'preferred_language': 'fr'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.preferred_language, 'fr')

    def test_invalid_language_code_is_rejected(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.patch('/api/auth/profile/', {'preferred_language': 'not-a-real-language'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
