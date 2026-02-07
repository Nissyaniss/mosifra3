from django.test import TestCase
from unittest.mock import patch
from accounts.views import _send_two_factor_code, SESSION_CODE_KEY
from accounts.models import User

class AccountsTests(TestCase):
    def test_send_two_factor_code_uses_secrets(self):
        """Verify that the secure secrets module is used instead of random."""
        session = {}
        with patch("accounts.views.secrets.SystemRandom") as mock_secrets:
            # mock randint to return a known value
            mock_secrets.return_value.randint.return_value = 123456
            _send_two_factor_code(session, "test@test.com", "Subject", "Template {code}")
            
            mock_secrets.return_value.randint.assert_called_once()
            self.assertEqual(session[SESSION_CODE_KEY], "123456")

    def test_send_two_factor_code_structure(self):
        """Verify the code is a 6-digit string."""
        session = {}
        _send_two_factor_code(session, "test@test.com", "S", "T {code}")
        code = session[SESSION_CODE_KEY]
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_login_view_sends_code(self):
        """Verify that logging in redirects to 2FA page."""
        User.objects.create_user(email="login@test.com", password="password", username="login@test.com")
        response = self.client.post("/accounts/login/", {"username": "login@test.com", "password": "password"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/two-factor/")
        self.assertIn(SESSION_CODE_KEY, self.client.session)
