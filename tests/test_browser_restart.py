"""A browser that closes mid-run (sleep, crash) is restarted instead of failing every later word."""
from pathlib import Path
import tomllib
import unittest
from unittest.mock import Mock, patch

from app.app_config import Config
from app.sources import SourceContext

ROOT = Path(__file__).resolve().parents[1]


class BrowserRestartTests(unittest.TestCase):
    def setUp(self):
        data = tomllib.loads((ROOT / 'config.toml').read_text(encoding='utf-8'))
        data['dictionary_cache'] = {'enabled': False}
        self.ctx = SourceContext(Config(ROOT / 'config.toml', data))
        self.launched = []

        def launch():
            browser = Mock()
            browser.is_connected.return_value = True
            self.ctx.browser, self.ctx.playwright = browser, Mock()
            self.launched.append(browser)
        self.ctx._launch_browser = launch

    def tearDown(self):
        self.ctx.browser = self.ctx.playwright = None
        self.ctx.close()

    def test_disconnected_browser_is_replaced_before_the_next_page(self):
        with self.ctx.page():
            pass
        self.launched[0].is_connected.return_value = False
        with patch('builtins.print') as printed, self.ctx.page() as page:
            self.assertIs(page, self.launched[1].new_page.return_value)
        self.assertEqual(len(self.launched), 2)
        self.launched[0].close.assert_called()
        self.assertIn('restarting', printed.call_args[0][0])

    def test_closed_error_on_new_page_gets_one_fresh_attempt_other_errors_do_not(self):
        with self.ctx.page():
            pass
        self.launched[0].new_page.side_effect = Exception('Browser.new_page: Target page, context or browser has been closed')
        with patch('builtins.print'), self.ctx.page() as page:
            self.assertIs(page, self.launched[1].new_page.return_value)
        self.launched[1].new_page.side_effect = ValueError('something else')
        with self.assertRaises(ValueError), self.ctx.page():
            pass
        self.assertEqual(len(self.launched), 2)

    def test_a_browser_that_keeps_dying_stops_being_restarted(self):
        with patch('builtins.print'):
            for _ in range(SourceContext.MAX_BROWSER_RESTARTS + 1):  # First one is the launch.
                with self.ctx.page():
                    pass
                self.ctx.browser.is_connected.return_value = False
            with self.assertRaisesRegex(RuntimeError, 'keeps closing'):
                with self.ctx.page():
                    pass
        with self.assertRaisesRegex(RuntimeError, 'keeps closing'):
            with self.ctx.page():
                pass


if __name__ == '__main__':
    unittest.main()
