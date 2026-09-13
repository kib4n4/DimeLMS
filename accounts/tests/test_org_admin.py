from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from accounts.models import User
from core.models import Institution


class OrgAdminAddViewTests(TestCase):
    """A Super Admin can only create an org admin for an institution that
    already exists — the institution ModelChoiceField is required and
    scoped to Institution.objects.all(), and creating one from an
    institution's own page preselects it and returns there afterwards."""

    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(
            name="Acme University", code="ACM001"
        )
        cls.superuser = User.objects.create_superuser(
            username="super", email="super@example.com", password="pw"
        )

    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)

    def _payload(self, **overrides):
        payload = {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "address": "123 Street",
            "phone": "0700000000",
        }
        payload.update(overrides)
        return payload

    def test_institution_is_required(self):
        self.client.force_login(self.superuser)
        response = self.client.post(reverse("add_org_admin"), self._payload())
        self.assertEqual(response.status_code, 200)
        self.assertIn("institution", response.context["form"].errors)
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())

    def test_attach_org_admin_preselects_institution_and_returns_to_detail(self):
        self.client.force_login(self.superuser)
        add_url = reverse("add_org_admin")

        form_page = self.client.get(f"{add_url}?institution={self.institution.pk}")
        self.assertContains(
            form_page, f'name="from_institution" value="{self.institution.pk}"'
        )

        response = self.client.post(
            add_url,
            self._payload(
                institution=self.institution.pk,
                from_institution=str(self.institution.pk),
            ),
        )
        self.assertRedirects(
            response,
            reverse("institution_detail", kwargs={"pk": self.institution.pk}),
        )
        admin = User.objects.get(email="jane@example.com")
        self.assertTrue(admin.is_org_admin)
        self.assertEqual(admin.institution_id, self.institution.pk)

    def test_institution_detail_lists_its_org_admins(self):
        User.objects.create_user(
            username="orgadmin",
            email="org@example.com",
            password="pw",
            first_name="Existing",
            last_name="Admin",
            is_org_admin=True,
            institution=self.institution,
        )
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse("institution_detail", kwargs={"pk": self.institution.pk})
        )
        self.assertContains(response, "Existing Admin")
