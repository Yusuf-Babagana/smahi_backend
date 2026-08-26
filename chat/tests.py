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
            # original_language is now determined by DETECTING what was
            # actually typed (see chat/views.py perform_create) — map every
            # literal used in this file to its real language so the fake
            # provider mirrors what the real one would return.
            detections={
                "Ina son sanin yadda zan yi amfani da wannan app.": "ha",
                "How are you today?": "en",
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

    # --- Send: original_language is DETECTED from what was actually typed ---

    def test_send_detects_the_actual_language_typed(self):
        response = self.send_as(self.hausa_user, "Ina son sanin yadda zan yi amfani da wannan app.")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        message = Message.objects.get(id=response.data['id'])
        self.assertEqual(message.original_language, 'ha')
        # Original text is never touched/overwritten by translation.
        self.assertEqual(message.text, "Ina son sanin yadda zan yi amfani da wannan app.")

    def test_send_falls_back_to_sender_preference_only_if_detection_fails(self):
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

    def test_detection_overrides_a_stale_sender_preference(self):
        # Regression test: a Hausa-preferring artisan answering in English
        # (or any sender typing in something other than their own chosen
        # language) must have THAT message correctly tagged 'en', not
        # silently mislabeled 'ha' from their stored preference — the old
        # "trust the sender's preference, skip detection" behavior made a
        # recipient with a matching preferred_language ('ha') see the raw,
        # untranslated English text because source and target both looked
        # like 'ha' even though the message itself was never Hausa.
        hausa_preferring_but_typed_english = User.objects.create_user(
            email='bilingual@test.com', password='pass12345',
            first_name='Bilingual', last_name='User', role='artisan',
            preferred_language='ha',
        )
        self.conversation.participants.add(hausa_preferring_but_typed_english)
        self.provider.detections["Actually typed in English"] = 'en'

        response = self.send_as(hausa_preferring_but_typed_english, "Actually typed in English")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        message = Message.objects.get(id=response.data['id'])
        self.assertEqual(message.original_language, 'en', "detection must win over the stale stored preference")

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
        # Server-detected value must win, not the client's spoofed value —
        # and not blindly the sender's own preferred_language either (this
        # Hausa-preferring sender actually typed English here).
        self.assertEqual(message.original_language, 'en')


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


class NewConversationFlowTests(APITestCase):
    """Regression test for the exact mobile flow: open a brand-new chat
    (id='new' + recipientId in app/chat/[id].tsx) then send the first
    message — reproduces "Please wait — initializing conversation..."
    getting stuck if get_or_create or the first send ever breaks."""

    def setUp(self):
        self.client_user = User.objects.create_user(
            email='newflow_client@test.com', password='pass12345',
            first_name='New', last_name='Client', role='client',
        )
        self.artisan_user = User.objects.create_user(
            email='newflow_artisan@test.com', password='pass12345',
            first_name='New', last_name='Artisan', role='artisan',
        )

    def test_get_or_create_then_send_first_message(self):
        self.client.force_authenticate(user=self.client_user)

        response = self.client.post('/api/chat/conversations/get_or_create/', {
            'recipient_id': self.artisan_user.id,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        conversation_id = response.data['id']

        send_response = self.client.post('/api/chat/messages/', {
            'conversation_id': conversation_id,
            'text': 'Hello from the debug flow test',
        })
        self.assertEqual(send_response.status_code, status.HTTP_201_CREATED, send_response.data)

    def test_get_or_create_is_idempotent(self):
        self.client.force_authenticate(user=self.client_user)
        first = self.client.post('/api/chat/conversations/get_or_create/', {
            'recipient_id': self.artisan_user.id,
        })
        second = self.client.post('/api/chat/conversations/get_or_create/', {
            'recipient_id': self.artisan_user.id,
        })
        self.assertEqual(first.data['id'], second.data['id'])


class FinalSignOffTests(APITestCase):
    """Explicit sign-off for the feature's core promise: whatever language a
    user picks in their profile, every message THEY receive arrives in that
    language — regardless of role (client or artisan/service-provider),
    and regardless of which language the other side actually typed in."""

    def setUp(self):
        self.provider = FakeTranslationProvider(
            translations={
                ("How are you today?", "en", "ha"): "Yaya kake yau?",
                ("Ina kwana?", "ha", "en"): "Good morning?",
            },
            detections={
                "How are you today?": "en",
                "Ina kwana?": "ha",
            },
        )
        self._original_provider = translation_service.provider
        translation_service.provider = self.provider

    def tearDown(self):
        translation_service.provider = self._original_provider

    def results(self, response):
        data = response.data
        return data if isinstance(data, list) else data['results']

    def test_client_picks_hausa_artisan_types_english_client_reads_hausa(self):
        client_user = User.objects.create_user(
            email='signoff_client@test.com', password='pass12345',
            first_name='Sign', last_name='Client', role='client',
            preferred_language='ha',
        )
        artisan_user = User.objects.create_user(
            email='signoff_artisan@test.com', password='pass12345',
            first_name='Sign', last_name='Artisan', role='artisan',
            preferred_language='en',
        )
        conversation = Conversation.objects.create()
        conversation.participants.add(client_user, artisan_user)

        # Artisan sends in English (their own language)
        self.client.force_authenticate(user=artisan_user)
        send = self.client.post('/api/chat/messages/', {
            'conversation_id': conversation.id,
            'text': 'How are you today?',
        })
        self.assertEqual(send.status_code, status.HTTP_201_CREATED)

        # Client (Hausa) reads it back — must arrive in Hausa
        self.client.force_authenticate(user=client_user)
        view = self.results(self.client.get(
            f'/api/chat/messages/?conversation_id={conversation.id}'
        ))[0]
        self.assertEqual(view['text'], 'Yaya kake yau?')
        self.assertEqual(view['original_text'], 'How are you today?')
        self.assertTrue(view['is_translated'])
        self.assertEqual(view['display_language'], 'ha')

    def test_reverse_artisan_picks_hausa_client_types_hausa_artisan_reads_hausa_unchanged(self):
        # And the "vice versa": an artisan who picked Hausa gets Hausa
        # messages shown as-is (no unnecessary translation).
        client_user = User.objects.create_user(
            email='signoff_client2@test.com', password='pass12345',
            first_name='Sign', last_name='Client2', role='client',
            preferred_language='ha',
        )
        artisan_user = User.objects.create_user(
            email='signoff_artisan2@test.com', password='pass12345',
            first_name='Sign', last_name='Artisan2', role='artisan',
            preferred_language='ha',
        )
        conversation = Conversation.objects.create()
        conversation.participants.add(client_user, artisan_user)

        self.client.force_authenticate(user=client_user)
        send = self.client.post('/api/chat/messages/', {
            'conversation_id': conversation.id,
            'text': 'Ina kwana?',
        })
        self.assertEqual(send.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=artisan_user)
        view = self.results(self.client.get(
            f'/api/chat/messages/?conversation_id={conversation.id}'
        ))[0]
        self.assertEqual(view['text'], 'Ina kwana?')
        self.assertFalse(view['is_translated'])
        self.assertEqual(self.provider.translate_calls, 0, "same-language pair must never call the provider")

    def test_reverse_artisan_picks_hausa_client_types_english_artisan_reads_hausa(self):
        client_user = User.objects.create_user(
            email='signoff_client3@test.com', password='pass12345',
            first_name='Sign', last_name='Client3', role='client',
            preferred_language='en',
        )
        artisan_user = User.objects.create_user(
            email='signoff_artisan3@test.com', password='pass12345',
            first_name='Sign', last_name='Artisan3', role='artisan',
            preferred_language='ha',
        )
        conversation = Conversation.objects.create()
        conversation.participants.add(client_user, artisan_user)

        self.client.force_authenticate(user=client_user)
        self.client.post('/api/chat/messages/', {
            'conversation_id': conversation.id,
            'text': 'How are you today?',
        })

        self.client.force_authenticate(user=artisan_user)
        view = self.results(self.client.get(
            f'/api/chat/messages/?conversation_id={conversation.id}'
        ))[0]
        self.assertEqual(view['text'], 'Yaya kake yau?')
        self.assertEqual(view['display_language'], 'ha')

    def test_changing_language_mid_conversation_affects_future_reads_immediately(self):
        # Simulates exactly what personal-info.tsx / artisan/profile.tsx do:
        # PATCH preferred_language, then re-read messages — no caching bug
        # should leave a reader stuck on their old language.
        client_user = User.objects.create_user(
            email='signoff_client4@test.com', password='pass12345',
            first_name='Sign', last_name='Client4', role='client',
            preferred_language='en',
        )
        artisan_user = User.objects.create_user(
            email='signoff_artisan4@test.com', password='pass12345',
            first_name='Sign', last_name='Artisan4', role='artisan',
            preferred_language='en',
        )
        conversation = Conversation.objects.create()
        conversation.participants.add(client_user, artisan_user)

        self.client.force_authenticate(user=artisan_user)
        self.client.post('/api/chat/messages/', {
            'conversation_id': conversation.id,
            'text': 'How are you today?',
        })

        self.client.force_authenticate(user=client_user)
        before = self.results(self.client.get(
            f'/api/chat/messages/?conversation_id={conversation.id}'
        ))[0]
        self.assertEqual(before['text'], 'How are you today?')  # same language, no translation yet

        # Client switches to Hausa via the profile endpoint, exactly like the app does
        patch = self.client.patch('/api/auth/profile/', {'preferred_language': 'ha'})
        self.assertEqual(patch.status_code, status.HTTP_200_OK)

        after = self.results(self.client.get(
            f'/api/chat/messages/?conversation_id={conversation.id}'
        ))[0]
        self.assertEqual(after['text'], 'Yaya kake yau?')
        self.assertTrue(after['is_translated'])


class ReadUnreadStatusTests(APITestCase):
    """The actual bug being fixed here: nothing on the frontend ever called
    mark_as_read, so a message's is_read never left False in the database —
    the unread badge could never clear, and a "read" message could reappear
    as unread later because it was never really marked read at all. These
    tests hit the real endpoints and re-query the DB fresh (never trusting
    an immediate response alone) to prove the status is actually persisted
    server-side, not just held in some screen's local state."""

    def setUp(self):
        # These tests only care about is_read/unread_count, never translated
        # content — swap in the fake provider (same as every other class in
        # this file) so message reads don't make a real, slow OpenAI call.
        self._original_provider = translation_service.provider
        translation_service.provider = FakeTranslationProvider()

        self.client_user = User.objects.create_user(
            email='readstatus_client@test.com', password='pass12345',
            first_name='Read', last_name='Client', role='client',
        )
        self.artisan_user = User.objects.create_user(
            email='readstatus_artisan@test.com', password='pass12345',
            first_name='Read', last_name='Artisan', role='artisan',
        )
        self.conversation = Conversation.objects.create()
        self.conversation.participants.add(self.client_user, self.artisan_user)

    def tearDown(self):
        translation_service.provider = self._original_provider

    def send_as(self, user, text):
        self.client.force_authenticate(user=user)
        return self.client.post('/api/chat/messages/', {
            'conversation_id': self.conversation.id,
            'text': text,
        })

    def mark_read_as(self, user):
        self.client.force_authenticate(user=user)
        return self.client.post('/api/chat/messages/mark_as_read/', {
            'conversation_id': self.conversation.id,
        })

    def unread_count_for(self, user):
        self.client.force_authenticate(user=user)
        response = self.client.get('/api/chat/conversations/')
        results = response.data if isinstance(response.data, list) else response.data['results']
        conv = next(c for c in results if c['id'] == self.conversation.id)
        return conv['unread_count']

    def test_new_message_defaults_to_unread(self):
        send = self.send_as(self.client_user, "Hello")
        message = Message.objects.get(id=send.data['id'])
        self.assertFalse(message.is_read)

    def test_unread_count_reflects_the_other_partys_unread_messages(self):
        self.send_as(self.client_user, "Are you available?")
        self.send_as(self.client_user, "Please respond")
        self.assertEqual(self.unread_count_for(self.artisan_user), 2)
        # The sender's own messages never count as their own unread.
        self.assertEqual(self.unread_count_for(self.client_user), 0)

    def test_mark_as_read_actually_persists_in_the_database(self):
        send = self.send_as(self.client_user, "Are you available?")
        message_id = send.data['id']

        response = self.mark_read_as(self.artisan_user)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Re-fetch fresh from the DB — not trusting the response alone —
        # to prove this is a real, persisted column value.
        message = Message.objects.get(id=message_id)
        self.assertTrue(message.is_read)

    def test_mark_as_read_clears_the_badge_and_it_stays_cleared(self):
        self.send_as(self.client_user, "Are you available?")
        self.assertEqual(self.unread_count_for(self.artisan_user), 1)

        self.mark_read_as(self.artisan_user)
        self.assertEqual(self.unread_count_for(self.artisan_user), 0)

        # The critical regression this fixes: leaving and coming back
        # (a fresh GET, simulating reopening the app) must NOT show the
        # already-read message as unread again.
        self.assertEqual(self.unread_count_for(self.artisan_user), 0)

    def test_mark_as_read_never_marks_the_readers_own_sent_messages(self):
        self.send_as(self.client_user, "Client's message")
        self.send_as(self.artisan_user, "Artisan's own message")

        self.mark_read_as(self.artisan_user)

        client_msg = Message.objects.get(text="Client's message")
        artisan_msg = Message.objects.get(text="Artisan's own message")
        self.assertTrue(client_msg.is_read, "the other party's message must be marked read")
        self.assertFalse(artisan_msg.is_read, "a user's own sent message is never 'unread' to mark")

    def test_mark_as_read_does_not_leak_into_other_conversations(self):
        other_artisan = User.objects.create_user(
            email='readstatus_other_artisan@test.com', password='pass12345',
            first_name='Other', last_name='Artisan', role='artisan',
        )
        other_conversation = Conversation.objects.create()
        other_conversation.participants.add(self.client_user, other_artisan)
        self.client.force_authenticate(self.client_user)
        other_send = self.client.post('/api/chat/messages/', {
            'conversation_id': other_conversation.id,
            'text': "Message in a different conversation",
        })

        self.send_as(self.client_user, "Message in the conversation being marked")
        self.mark_read_as(self.artisan_user)

        other_message = Message.objects.get(id=other_send.data['id'])
        self.assertFalse(other_message.is_read, "marking one conversation read must never touch another")

    def test_non_participant_cannot_mark_a_conversation_read(self):
        outsider = User.objects.create_user(
            email='readstatus_outsider@test.com', password='pass12345',
            first_name='Out', last_name='Sider', role='client',
        )
        send = self.send_as(self.client_user, "Are you available?")
        message_id = send.data['id']

        self.mark_read_as(outsider)  # not a participant — must be a no-op

        message = Message.objects.get(id=message_id)
        self.assertFalse(message.is_read, "a non-participant marking as read must not affect real participants' messages")
