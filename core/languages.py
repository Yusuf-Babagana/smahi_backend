"""Central language configuration for the messaging translation system.

Single source of truth for supported language codes/names — imported by
accounts.models (User.preferred_language), chat.models (Message.
original_language), and core.translation. Uses standard ISO 639-1 codes.
Add a language here and it becomes available everywhere without touching
any other file.
"""

SUPPORTED_LANGUAGES = [
    ('en', 'English'),
    ('ha', 'Hausa'),
    ('ar', 'Arabic'),
    ('fr', 'French'),
    ('es', 'Spanish'),
    ('pt', 'Portuguese'),
    ('de', 'German'),
    ('it', 'Italian'),
    ('zh', 'Chinese'),
    ('ja', 'Japanese'),
    ('ko', 'Korean'),
    ('tr', 'Turkish'),
    ('sw', 'Swahili'),
    ('yo', 'Yoruba'),
    ('ig', 'Igbo'),
]

SUPPORTED_LANGUAGE_CODES = {code for code, _ in SUPPORTED_LANGUAGES}

LANGUAGE_NAMES = dict(SUPPORTED_LANGUAGES)

DEFAULT_LANGUAGE = 'en'


def language_name(code: str) -> str:
    """Human-readable name for a language code, falling back to the code itself."""
    return LANGUAGE_NAMES.get(code, code)
