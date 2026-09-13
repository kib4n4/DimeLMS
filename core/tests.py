from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from accounts.models import User
from course.models import Program, Course
from core.forms import InstitutionForm
from core.models import Institution


class InstitutionDetailViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name="Acme University")
        cls.program = Program.objects.create(
            title="Computer Science", summary="x", institution=cls.institution
        )
        Course.objects.create(title="Intro to CS", code="CS101", program=cls.program)

        cls.superuser = User.objects.create_superuser(
            username="super", email="super@example.com", password="pw"
        )
        cls.org_admin = User.objects.create_user(
            username="orgadmin", email="org@example.com", password="pw",
            is_org_admin=True, institution=cls.institution,
        )

    def setUp(self):
        # LANGUAGE_CODE is "en-us" but LANGUAGES only offers "en"; pin the
        # active language so reverse() and the i18n URL prefix agree.
        translation.activate("en")
        self.addCleanup(translation.deactivate)

    def test_superuser_sees_programs_and_courses(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse("institution_detail", kwargs={"pk": self.institution.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acme University")
        self.assertContains(response, "Computer Science")
        self.assertContains(response, "Intro to CS")

    def test_non_superuser_is_redirected(self):
        self.client.force_login(self.org_admin)
        response = self.client.get(
            reverse("institution_detail", kwargs={"pk": self.institution.pk})
        )
        self.assertEqual(response.status_code, 302)

    def test_attach_program_preselects_institution_and_returns_to_detail(self):
        self.client.force_login(self.superuser)
        add_url = reverse("add_program")

        form_page = self.client.get(f"{add_url}?institution={self.institution.pk}")
        self.assertContains(
            form_page, f'name="from_institution" value="{self.institution.pk}"'
        )

        response = self.client.post(
            add_url,
            {
                "institution": self.institution.pk,
                "title": "Mathematics",
                "summary": "y",
                "from_institution": str(self.institution.pk),
            },
        )
        self.assertRedirects(
            response,
            reverse("institution_detail", kwargs={"pk": self.institution.pk}),
        )
        self.assertTrue(
            Program.objects.filter(
                title="Mathematics", institution=self.institution
            ).exists()
        )

    def test_list_links_to_detail(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("institution_list"))
        self.assertContains(
            response,
            reverse("institution_detail", kwargs={"pk": self.institution.pk}),
        )


class OrganizationProfileViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(
            name="Dime Consultants Limited",
            code="DIME001",
            email="info@dime.co.ke",
            phone="254768528200",
            contact_name="Brian Aleri",
        )
        cls.org_admin = User.objects.create_user(
            username="orgadmin", email="org@example.com", password="pw",
            is_org_admin=True, institution=cls.institution,
        )
        cls.unlinked_admin = User.objects.create_user(
            username="lonely", email="lonely@example.com", password="pw",
            is_org_admin=True,
        )
        cls.superuser = User.objects.create_superuser(
            username="super", email="super@example.com", password="pw"
        )

    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)

    def test_org_admin_sees_own_organization_profile(self):
        self.client.force_login(self.org_admin)
        response = self.client.get(reverse("organization_profile"))
        self.assertEqual(response.status_code, 200)
        for value in ("Dime Consultants Limited", "DIME001", "info@dime.co.ke",
                      "254768528200", "Brian Aleri"):
            self.assertContains(response, value)

    def test_student_is_denied(self):
        student = User.objects.create_user(
            username="stud", email="s@example.com", password="pw",
            is_student=True, institution=self.institution,
        )
        self.client.force_login(student)
        response = self.client.get(reverse("organization_profile"))
        self.assertEqual(response.status_code, 302)

    def test_org_admin_without_institution_is_redirected(self):
        self.client.force_login(self.unlinked_admin)
        response = self.client.get(reverse("organization_profile"))
        self.assertRedirects(response, reverse("home"))

    def test_superuser_is_sent_to_institution_list(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("organization_profile"))
        self.assertRedirects(response, reverse("institution_list"))


class InstitutionAddViewTests(TestCase):
    def setUp(self):
        translation.activate("en")
        self.addCleanup(translation.deactivate)

    def test_creating_an_institution_lands_on_its_detail_page(self):
        superuser = User.objects.create_superuser(
            username="super", email="super@example.com", password="pw"
        )
        self.client.force_login(superuser)
        response = self.client.post(
            reverse("institution_add"),
            {"name": "New Org", "code": "NEW001", "is_active": True},
        )
        institution = Institution.objects.get(name="New Org")
        self.assertRedirects(
            response,
            reverse("institution_detail", kwargs={"pk": institution.pk}),
        )


class InstitutionFormTests(TestCase):
    def test_code_is_required(self):
        form = InstitutionForm(data={"name": "New Org", "is_active": True})
        self.assertFalse(form.is_valid())
        self.assertIn("code", form.errors)

    def test_valid_with_code(self):
        form = InstitutionForm(
            data={"name": "New Org", "code": "NEW001", "is_active": True}
        )
        self.assertTrue(form.is_valid(), form.errors)
