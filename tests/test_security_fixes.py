import unittest
from unittest.mock import MagicMock, patch

from backend import import_youtube_playlist
from backend.app import Handler

class PrivateFileTests(unittest.TestCase):
    def test_encoded_private_extensions_are_blocked(self):
        for path in ('/app.py', '/app.%70y', '/app.p%79', '/README.%6dd', '/.env', '/%2eenv'):
            with self.subTest(path=path):
                self.assertTrue(Handler.is_private_file(path))

    def test_public_assets_are_served(self):
        for path in ('/index.html', '/app.js', '/styles.css', '/catalog-data.js'):
            with self.subTest(path=path):
                self.assertFalse(Handler.is_private_file(path))

class VideoIdValidationTests(unittest.TestCase):
    def test_crafted_video_id_is_rejected_before_api_call(self):
        with patch.object(import_youtube_playlist, 'request_video') as request:
            with self.assertRaises(ValueError):
                import_youtube_playlist.fetch_single_video('key', 'https://youtu.be/AAAAAAAAAAA,"><img src=x onerror=alert(1)>')
            request.assert_not_called()

    def test_supported_video_links_still_import(self):
        item = {'items': [{'snippet': {'title': 'RP 900 Hunt Solo 5kk/h', 'description': '', 'channelTitle': 'x'}}]}
        links = ('dQw4w9WgXcQ', 'https://youtu.be/dQw4w9WgXcQ', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                 'https://www.youtube.com/shorts/dQw4w9WgXcQ', 'https://youtube.com/live/dQw4w9WgXcQ',
                 'https://www.youtube.com/embed/dQw4w9WgXcQ')
        for link in links:
            with self.subTest(link=link), patch.object(import_youtube_playlist, 'request_video', return_value=item):
                row = import_youtube_playlist.fetch_single_video('key', link, 'RP')[0]
                self.assertEqual(row['video_url'], 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')

class ForwardedForTests(unittest.TestCase):
    def test_rate_limit_uses_proxy_appended_address(self):
        handler = Handler.__new__(Handler)
        handler.headers = {'X-Forwarded-For': '203.0.113.7, 198.51.100.1'}
        handler.client_address = ('10.0.0.1', 1234)
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchone.return_value = (0,)
        with patch.dict('os.environ', {'SKAN_TRUST_PROXY_HEADERS': '1'}), \
             patch('backend.app.ensure_feedback_table'), \
             patch('backend.app.connect_database', return_value=connection):
            self.assertTrue(handler.allow_public_submission('feedback', {}))
        insert = connection.execute.call_args_list[-1]
        self.assertEqual(insert.args[1][1], '198.51.100.1')

if __name__ == '__main__':
    unittest.main()
