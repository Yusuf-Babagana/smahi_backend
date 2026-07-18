"""
Live website context for the S-MAHII AI assistant.

Fetches the public S-MAHII website (homepage + optional extra pages such as
/contact or /coordinators), strips the HTML down to readable text, and caches
the result so the assistant always answers from the site's CURRENT content —
coordinator phone numbers, announcements, service areas — without redeploys.

Configure in .env / settings:
    SMAHI_WEBSITE_URL   e.g. https://www.smahi.ng
    SMAHI_INFO_PAGES    optional comma-separated paths, e.g. /contact,/coordinators

NOTE: on a PythonAnywhere FREE account, outbound requests only reach
whitelisted domains, so the website itself is unreachable from the server.
Fallback: a GitHub Action (.github/workflows/mirror-site.yml) refreshes a
copy of the site in this repo every 6 hours, and raw.githubusercontent.com
IS whitelisted — so when the direct fetch fails we read the mirror instead.
"""

import re
import time
import urllib.request
from html.parser import HTMLParser

from django.conf import settings

SITE_CACHE_TTL_SECONDS = 10 * 60   # re-fetch the website at most every 10 min
SITE_CONTEXT_MAX_CHARS = 12000     # keep the prompt (and cost) bounded

# Kept fresh by .github/workflows/mirror-site.yml; reachable from
# PythonAnywhere free tier where the website's own domain is not.
SITE_MIRROR_URL = (
    'https://raw.githubusercontent.com/Yusuf-Babagana/smahi_backend/main/site_mirror.html'
)

_site_cache = {'fetched_at': 0.0, 'text': ''}


class _TextExtractor(HTMLParser):
    """Strips an HTML page down to its visible text."""

    _SKIP_TAGS = {'script', 'style', 'noscript', 'svg', 'head'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._chunks = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data.strip())

    def get_text(self):
        return '\n'.join(self._chunks)


def _fetch_page_text(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'S-MAHII-Assistant/1.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read(500_000).decode('utf-8', errors='replace')
    parser = _TextExtractor()
    parser.feed(html)
    return re.sub(r'\n{3,}', '\n\n', parser.get_text())


def get_site_context():
    """
    Returns the website's text content, cached for SITE_CACHE_TTL_SECONDS.
    Never raises: if the site is unreachable, returns the last good copy
    (or '' on cold start) so chat keeps working.
    """
    base_url = getattr(settings, 'SMAHI_WEBSITE_URL', '').strip().rstrip('/')
    if not base_url:
        return ''

    now = time.time()
    if now - _site_cache['fetched_at'] < SITE_CACHE_TTL_SECONDS:
        return _site_cache['text']

    urls = [base_url]
    for path in getattr(settings, 'SMAHI_INFO_PAGES', '').split(','):
        path = path.strip()
        if path:
            urls.append(base_url + '/' + path.lstrip('/'))

    sections = []
    for url in urls:
        try:
            sections.append('--- Page: %s ---\n%s' % (url, _fetch_page_text(url)))
        except Exception:
            continue  # one broken page must not take the assistant down

    if not sections:
        # Direct fetch blocked (e.g. PythonAnywhere free-tier proxy):
        # fall back to the GitHub-hosted mirror of the site.
        try:
            sections.append(
                '--- Page: %s (mirror) ---\n%s'
                % (base_url, _fetch_page_text(SITE_MIRROR_URL))
            )
        except Exception:
            pass

    if sections:
        _site_cache['text'] = '\n\n'.join(sections)[:SITE_CONTEXT_MAX_CHARS]
    _site_cache['fetched_at'] = now  # even on total failure, don't retry every request
    return _site_cache['text']
