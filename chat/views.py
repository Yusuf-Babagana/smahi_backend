from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django.db.models import Q
from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer
from core.translation import translation_service

class ConversationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer

    def get_queryset(self):
        return self.request.user.conversations.all()

    @action(detail=False, methods=['post'])
    def get_or_create(self, request):
        recipient_id = request.data.get('recipient_id')
        if not recipient_id:
            return Response({'error': 'recipient_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            recipient_id = int(recipient_id)
        except (TypeError, ValueError):
            return Response({'error': 'recipient_id must be a valid user id'}, status=status.HTTP_400_BAD_REQUEST)

        if recipient_id == request.user.id:
            return Response({'error': 'You cannot start a conversation with yourself'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if conversation already exists
        conversation = Conversation.objects.filter(participants=request.user).filter(participants__id=recipient_id).first()

        if not conversation:
            conversation = Conversation.objects.create()
            conversation.participants.add(request.user, recipient_id)
        
        serializer = self.get_serializer(conversation)
        return Response(serializer.data)

class MessageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer

    def get_queryset(self):
        conversation_id = self.request.query_params.get('conversation_id')
        if not conversation_id:
            return Message.objects.none()
        
        # Ensure the user is a participant in this conversation
        return Message.objects.filter(
            conversation_id=conversation_id,
            conversation__participants=self.request.user
        )

    def perform_create(self, serializer):
        conversation_id = self.request.data.get('conversation_id')
        try:
            conversation = Conversation.objects.get(id=conversation_id, participants=self.request.user)
        except (Conversation.DoesNotExist, ValueError, TypeError):
            raise ValidationError({'conversation_id': 'Invalid conversation, or you are not a participant.'})

        # Detect the language of what was actually typed, not what the
        # sender has chosen as their preference — those two silently
        # diverge whenever someone types in a language other than their own
        # (an artisan whose preferred_language is Hausa answering a client
        # in English, a bilingual user, etc.). Trusting the stored
        # preference blindly mislabeled those messages' original_language,
        # which made the "same language, don't translate" check fire
        # incorrectly and left the recipient stuck seeing the untranslated
        # original. Detection only costs one small (max_tokens=5) call and
        # is cached like everything else the translation service does, so
        # it's cheap; the stored preference is now just the fallback for
        # when detection itself fails (API error, empty text).
        sender = self.request.user
        text = serializer.validated_data.get('text', '')
        original_language = translation_service.detect_language(text) or sender.preferred_language or 'en'

        serializer.save(sender=sender, conversation=conversation, original_language=original_language)

    @action(detail=False, methods=['post'])
    def mark_as_read(self, request):
        conversation_id = request.data.get('conversation_id')
        if not conversation_id:
            return Response({'error': 'conversation_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        Message.objects.filter(
            conversation_id=conversation_id,
            conversation__participants=request.user
        ).exclude(sender=request.user).update(is_read=True)
        
        return Response({'status': 'messages marked as read'})
