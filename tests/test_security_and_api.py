import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.security import is_loopback, lan_mode_enabled, lan_token, _extract_token, http_is_authorized, websocket_is_authorized
from api.pipeline import clean_clip_title, _list_clips, ClipReviewItem
from pydantic import ValidationError


class TestSecurityAndApi(unittest.TestCase):
    def setUp(self):
        self.orig_host = os.environ.get("CLIPHUB_HOST")
        self.orig_token = os.environ.get("CLIPHUB_LAN_TOKEN")

    def tearDown(self):
        if self.orig_host is not None:
            os.environ["CLIPHUB_HOST"] = self.orig_host
        else:
            os.environ.pop("CLIPHUB_HOST", None)
        if self.orig_token is not None:
            os.environ["CLIPHUB_LAN_TOKEN"] = self.orig_token
        else:
            os.environ.pop("CLIPHUB_LAN_TOKEN", None)

    def test_is_loopback(self):
        self.assertTrue(is_loopback("127.0.0.1"))
        self.assertTrue(is_loopback("::1"))
        self.assertTrue(is_loopback("localhost"))
        self.assertTrue(is_loopback("testclient"))
        self.assertFalse(is_loopback("192.168.1.50"))
        self.assertFalse(is_loopback("10.0.0.1"))
        self.assertFalse(is_loopback(None))
        self.assertFalse(is_loopback(""))

    def test_token_extraction(self):
        # 1. Header
        headers = {"x-cliphub-token": "secret123"}
        self.assertEqual(_extract_token(headers, {}, {}), "secret123")
        
        # 2. Authorization Bearer
        headers = {"authorization": "Bearer secret_bearer"}
        self.assertEqual(_extract_token(headers, {}, {}), "secret_bearer")
        
        # 3. Cookie
        cookies = {"cliphub_lan_token": "secret_cookie"}
        self.assertEqual(_extract_token({}, cookies, {}), "secret_cookie")
        
        # 4. Query param
        query = {"token": "secret_query"}
        self.assertEqual(_extract_token({}, {}, query), "secret_query")
        
        # None when empty
        self.assertIsNone(_extract_token({}, {}, {}))

    def test_lan_authorization_logic(self):
        os.environ["CLIPHUB_HOST"] = "0.0.0.0"
        os.environ["CLIPHUB_LAN_TOKEN"] = "secure_token_999"

        # Loopback client always authorized
        req_local = MagicMock()
        req_local.client.host = "127.0.0.1"
        self.assertTrue(http_is_authorized(req_local))

        # Remote client without token rejected
        req_remote_bad = MagicMock()
        req_remote_bad.client.host = "192.168.1.100"
        req_remote_bad.headers = {}
        req_remote_bad.cookies = {}
        req_remote_bad.query_params = {}
        self.assertFalse(http_is_authorized(req_remote_bad))

        # Remote client with valid token accepted
        req_remote_good = MagicMock()
        req_remote_good.client.host = "192.168.1.100"
        req_remote_good.headers = {"x-cliphub-token": "secure_token_999"}
        req_remote_good.cookies = {}
        req_remote_good.query_params = {}
        self.assertTrue(http_is_authorized(req_remote_good))

    def test_clean_clip_title(self):
        self.assertEqual(clean_clip_title("clip_01_Why_Sleep_Matters.mp4"), "Why Sleep Matters")
        self.assertEqual(clean_clip_title("1. How To Focus Better"), "How To Focus Better")
        self.assertEqual(clean_clip_title(""), "Untitled Clip")
        self.assertEqual(clean_clip_title(None), "Untitled Clip")

    def test_clip_review_item_validation(self):
        # Valid clip
        item = ClipReviewItem(start_ms=1000, end_ms=45000, title="Valid Clip")
        self.assertEqual(item.start_ms, 1000)
        self.assertEqual(item.end_ms, 45000)

        # Invalid: end <= start
        with self.assertRaises(ValidationError):
            ClipReviewItem(start_ms=5000, end_ms=4000, title="Invalid Range")

        with self.assertRaises(ValidationError):
            ClipReviewItem(start_ms=5000, end_ms=5000, title="Zero Duration")


if __name__ == "__main__":
    unittest.main()
