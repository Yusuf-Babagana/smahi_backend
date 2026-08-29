from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Conversation, Message
from accounts.serializers import PublicUserSerializer
from core.languages import DEFAULT_LANGUAGE
from core.translation import translation_service

User = get_user_model()

class MessageSerializer(serializers.ModelSerializer):
    sender_email = serializers.EmailField(source='sender.email', read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender', 'sender_email', 'text', 'original_language', 'is_read', 'created_at']
        read_only_fields = ['sender', 'conversation', 'original_language']

    def to_representation(self, instance):
        """Automatic translation happens here, on read, for whoever is asking.

        `text` keeps its existing meaning ("what to display") so every
        existing client keeps working unmodified. `original_text` is always
        the untouched DB value; `is_translated`/`display_language` let the
        UI show a "Translated from X" / "View original" affordance.
        """
        data = super().to_representation(instance)

        request = self.context.get('request')
        target_language = DEFAULT_LANGUAGE
        if request is not None and getattr(request, 'user', None) is not None:
            target_language = getattr(request.user, 'preferred_language', '') or DEFAULT_LANGUAGE

        source_language = instance.original_language or DEFAULT_LANGUAGE
        original_text = instance.text
        display_text, was_translated = translation_service.translate(
            original_text, source_language, target_language
        )

        data['original_text'] = original_text
        data['display_language'] = target_language
        data['is_translated'] = was_translated
        data['text'] = display_text
        return data

class ConversationSerializer(serializers.ModelSerializer):
    # RBAC (item 11): a chat partner only needs enough to render the
    # conversation list (name, avatar) — the full UserSerializer was
    # exposing a partner's email, exact GPS, account_status,
    # registration_fee_paid, email_verified, and serial_number to anyone
    # they'd exchanged even one message with. Not an IDOR (correctly
    # scoped to actual participants via ConversationViewSet.get_queryset),
    # just broader than a chat UI needs.
    participants_details = PublicUserSerializer(source='participants', many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'participants', 'participants_details', 'last_message', 'unread_count', 'updated_at']
        read_only_fields = ['participants']

    def get_last_message(self, obj):
        last_msg = obj.messages.last()
        if last_msg:
            # Pass context through so the nested serializer's to_representation
            # can see request.user and translate the preview into their language
            # — without this, get_last_message silently ignored the request.
            return MessageSerializer(last_msg, context=self.context).data
        return None

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.messages.filter(is_read=False).exclude(sender=request.user).count()
        return 0
