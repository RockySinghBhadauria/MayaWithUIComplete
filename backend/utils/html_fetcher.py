"""SEC EDGAR HTTP client.

Consolidates the duplicated urllib fetch-and-parse pattern used across
the original MAYA codebase into a single reusable class.
"""
import time
import urllib.request
import urllib.error

from bs4 import BeautifulSoup

import config
from core.logging_config import get_logger

logger = get_logger('html_fetcher')


class SECFetcher(object):
    """HTTP client for SEC EDGAR pages with rate limiting and retries."""

    def __init__(self, max_retries=3, delay=None, user_agent=None):
        self.max_retries = max_retries
        self.delay = delay if delay is not None else config.SEC_REQUEST_DELAY
        self.user_agent = user_agent or config.SEC_USER_AGENT
        self._last_request_time = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rate_limit(self):
        """Sleep if necessary to honour SEC rate-limiting requirements."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def _build_request(self, url):
        """Return a ``urllib.request.Request`` with the correct headers."""
        req = urllib.request.Request(url)
        req.add_header('User-Agent', self.user_agent)
        return req

    def _fetch_raw(self, url):
        """Fetch *url* with retries and return the raw response bytes.

        Returns ``None`` when all retry attempts are exhausted.
        """
        for attempt in range(1, self.max_retries + 1):
            # Check stop signal before each attempt
            import builtins
            if getattr(builtins, '_maya_stop_pipeline', False):
                logger.info("Stop signal — aborting fetch for %s", url)
                return None

            try:
                self._rate_limit()
                req = self._build_request(url)
                response = urllib.request.urlopen(req, timeout=15)
                self._last_request_time = time.time()
                return response.read()
            except urllib.error.HTTPError as exc:
                logger.warning(
                    'HTTP %s for %s (attempt %d/%d)',
                    exc.code, url, attempt, self.max_retries,
                )
            except urllib.error.URLError as exc:
                logger.warning(
                    'URL error for %s: %s (attempt %d/%d)',
                    url, exc.reason, attempt, self.max_retries,
                )
            except Exception as exc:
                logger.warning(
                    'Unexpected error fetching %s: %s (attempt %d/%d)',
                    url, exc, attempt, self.max_retries,
                )

            # Back off a little before retrying
            if attempt < self.max_retries:
                time.sleep(self.delay)

        logger.error('All %d attempts failed for %s', self.max_retries, url)
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_page(self, url):
        """Fetch *url* and return a ``BeautifulSoup`` (html.parser) object.

        Returns ``None`` if the request fails after all retries.
        """
        data = self._fetch_raw(url)
        if data is None:
            return None
        try:
            return BeautifulSoup(data, 'html.parser')
        except Exception as exc:
            logger.error('Failed to parse HTML from %s: %s', url, exc)
            return None

    def fetch_xml(self, url):
        """Fetch *url* and return a ``BeautifulSoup`` (xml parser) object.

        Intended for RSS / Atom feeds from SEC EDGAR.
        Returns ``None`` if the request fails after all retries.
        """
        data = self._fetch_raw(url)
        if data is None:
            return None
        try:
            return BeautifulSoup(data, features='xml')
        except Exception as exc:
            logger.error('Failed to parse XML from %s: %s', url, exc)
            return None
