from django.test import TestCase, RequestFactory
from django.urls import reverse
from unittest.mock import MagicMock
from profiles.views import AdminValidationView, tab_dashboard, tab_account, tab_offers, tab_students
from accounts.models import User, CompanyProfile, InstitutionProfile

class ProfilesViewsTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_admin_validation_context_merging(self):
        """Verify that companies and institutions are correctly merged in the context."""
        u1 = User.objects.create(username="c1", role=User.Role.COMPANY, email="c1@test.com")
        CompanyProfile.objects.create(user=u1, organisation_name="Comp1", is_approved=False)
        
        u2 = User.objects.create(username="i1", role=User.Role.INSTITUTION, email="i1@test.com")
        InstitutionProfile.objects.create(user=u2, organisation_name="Inst1", is_approved=False)

        request = self.factory.get("/profiles/admin-validation/")
        request.user = User.objects.create(username="admin", is_staff=True)
        
        view = AdminValidationView()
        view.setup(request)
        context = view.get_context_data()
        
        pending = context["pending_accounts"]
        self.assertEqual(len(pending), 2)
        types = {p["type"] for p in pending}
        names = {p["name"] for p in pending}
        self.assertIn("company", types)
        self.assertIn("institution", types)
        self.assertIn("Comp1", names)
        self.assertIn("Inst1", names)

    def test_tab_dashboard_get_only(self):
        request = self.factory.post("/")
        request.user = MagicMock(is_authenticated=True)
        response = tab_dashboard(request)
        self.assertEqual(response.status_code, 405)

    def test_tab_account_get_only(self):
        request = self.factory.post("/")
        request.user = MagicMock(is_authenticated=True)
        response = tab_account(request)
        self.assertEqual(response.status_code, 405)

    def test_tab_offers_get_only(self):
        request = self.factory.post("/")
        request.user = MagicMock(is_authenticated=True)
        response = tab_offers(request)
        self.assertEqual(response.status_code, 405)

    def test_tab_students_get_only(self):
        request = self.factory.post("/")
        request.user = MagicMock(is_authenticated=True)
        response = tab_students(request)
        self.assertEqual(response.status_code, 405)

    def test_admin_validation_view_access(self):
        """Verify correct redirect for non-staff users."""
        request = self.factory.get("/")
        request.user = MagicMock(is_staff=False, is_authenticated=True)
        view = AdminValidationView()
        view.setup(request)
        response = view.dispatch(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("profiles:account_space"))
