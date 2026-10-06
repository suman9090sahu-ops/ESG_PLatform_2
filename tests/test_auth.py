"""
Authentication Test Suite for MEIL ESG CONTROL TOWER.

Validates:
- Successful login and session initialization
- Failed login with invalid credentials and generic error response
- Inactive user login denial
- Secure logout and session invalidation
- Login redirection (role-based deterministic routing)
- Protection against Open Redirect attacks
- Authenticated password change with validation
- Password reset workflow
- Audit logging of authentication events (LOGIN_SUCCESS, LOGIN_FAILURE, LOGOUT, PASSWORD_CHANGE)
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import AuthAuditLog, Role, UserRole

User = get_user_model()


class AuthenticationTests(TestCase):
    """Test suite for authentication workflows and security controls."""

    def setUp(self):
        self.client = Client()
        self.password = "ValidPass123!@#"

        # Create base active user
        self.user = User.objects.create_user(
            username="test_user",
            email="test@meilgroup.com",
            password=self.password,
            first_name="Test",
            last_name="Operator",
            is_active=True,
        )

        # Create inactive user
        self.inactive_user = User.objects.create_user(
            username="inactive_user",
            email="inactive@meilgroup.com",
            password=self.password,
            is_active=False,
        )

        # Create Site Manager role
        self.site_role = Role.objects.create(
            code=Role.Code.SITE_MANAGER,
            name="Site Manager",
        )
        UserRole.objects.create(user=self.user, role=self.site_role, is_primary=True)

    def test_login_page_renders_200(self):
        """Login page renders with 200 OK and accessible form elements."""
        response = self.client.get(reverse("core:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Username / Enterprise ID")
        self.assertContains(response, "Password")
        self.assertContains(response, 'id="loginSubmitBtn"')

    def test_login_success_with_valid_credentials(self):
        """User logs in successfully and is redirected to role dashboard."""
        response = self.client.post(
            reverse("core:login"),
            {
                "username": "test_user",
                "password": self.password,
                "remember_me": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        # Primary role is SITE_MANAGER -> should redirect to site manager dashboard
        self.assertEqual(response.url, reverse("core:site_manager_dashboard"))

        # Verify audit log recorded LOGIN_SUCCESS
        audit_entry = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.LOGIN_SUCCESS,
            user=self.user,
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertTrue(audit_entry.success)

    def test_login_failure_with_invalid_credentials(self):
        """Invalid credentials rejected, user remains unauthenticated, audit log created."""
        response = self.client.post(
            reverse("core:login"),
            {
                "username": "test_user",
                "password": "WrongPassword999!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid credentials")

        # Verify audit log recorded LOGIN_FAILURE
        audit_entry = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.LOGIN_FAILURE,
            username_attempted="test_user",
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertFalse(audit_entry.success)

    def test_inactive_user_cannot_login(self):
        """Deactivated account cannot sign in."""
        response = self.client.post(
            reverse("core:login"),
            {
                "username": "inactive_user",
                "password": self.password,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This enterprise account has been deactivated")

    def test_logout_invalidates_session(self):
        """Logout invalidates user session and redirects to login with confirmation."""
        self.client.login(username="test_user", password=self.password)
        response = self.client.get(reverse("core:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:login"))

        # Verify user is now logged out
        dashboard_response = self.client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(dashboard_response.status_code, 302)
        self.assertIn(reverse("core:login"), dashboard_response.url)

        # Verify audit log recorded LOGOUT
        audit_entry = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.LOGOUT,
            user=self.user,
        ).first()
        self.assertIsNotNone(audit_entry)

    def test_open_redirect_attack_prevention(self):
        """Malicious external next URLs are rejected in favor of role dashboard."""
        malicious_urls = [
            "https://attacker-phishing.com/steal-session",
            "//attacker-phishing.com",
            "javascript:alert(1)",
        ]
        for bad_url in malicious_urls:
            response = self.client.post(
                reverse("core:login"),
                {
                    "username": "test_user",
                    "password": self.password,
                    "next": bad_url,
                },
            )
            self.assertEqual(response.status_code, 302)
            # Must redirect to safe internal role dashboard, NEVER to bad_url
            self.assertEqual(response.url, reverse("core:site_manager_dashboard"))

    def test_safe_internal_next_url_honored(self):
        """Safe internal next URL is honored upon authentication."""
        safe_next = reverse("core:ui_preview")
        response = self.client.post(
            reverse("core:login"),
            {
                "username": "test_user",
                "password": self.password,
                "next": safe_next,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, safe_next)

    def test_password_change_requires_authentication(self):
        """Unauthenticated user redirected to login when accessing password change."""
        response = self.client.get(reverse("core:password_change"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("core:login"), response.url)

    def test_password_change_success(self):
        """Authenticated user successfully changes password and session is updated."""
        self.client.login(username="test_user", password=self.password)
        new_password = "NewSuperSecurePass456!@#"
        response = self.client.post(
            reverse("core:password_change"),
            {
                "old_password": self.password,
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:password_change_done"))

        # Verify new password works
        self.client.logout()
        login_res = self.client.login(username="test_user", password=new_password)
        self.assertTrue(login_res)

        # Verify audit log recorded PASSWORD_CHANGE
        audit_entry = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.PASSWORD_CHANGE,
            user=self.user,
        ).first()
        self.assertIsNotNone(audit_entry)

    def test_password_reset_request_workflow(self):
        """Password reset request dispatches email and creates audit event."""
        response = self.client.post(
            reverse("core:password_reset"),
            {"email": "test@meilgroup.com"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:password_reset_done"))

        audit_entry = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.PASSWORD_RESET_REQUEST,
            username_attempted="test@meilgroup.com",
        ).first()
        self.assertIsNotNone(audit_entry)
