from django.contrib import admin
from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ['sender', 'text', 'original_language', 'is_read', 'created_at']
    readonly_fields = ['created_at']
    show_change_link = True


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'participant_list', 'created_at', 'updated_at']
    search_fields = ['participants__email', 'participants__first_name', 'participants__last_name']
    filter_horizontal = ['participants']
    inlines = [MessageInline]

    def participant_list(self, obj):
        return ', '.join(u.email for u in obj.participants.all())
    participant_list.short_description = 'Participants'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'sender', 'text_preview', 'is_read', 'created_at']
    list_filter = ['is_read', 'original_language']
    search_fields = ['text', 'sender__email']
    autocomplete_fields = ['conversation', 'sender']

    def text_preview(self, obj):
        return obj.text[:60] + ('…' if len(obj.text) > 60 else '')
    text_preview.short_description = 'Text'
