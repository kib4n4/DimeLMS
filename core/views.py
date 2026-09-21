from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count

from accounts.decorators import admin_required, org_admin_required, courses_read_required
from accounts.models import User, Student
from course.models import Course
from result.models import TakenCourse
from .forms import SessionForm, SemesterForm, NewsAndEventsForm, InstitutionForm
from .models import (
    NewsAndEvents,
    ActivityLog,
    Session,
    Semester,
    SiteConfiguration,
    Institution,
)


# ########################################################
# Institutions — Super Admin only. This is the tenant boundary every org
# admin, facilitator, and student is scoped to (see core.institution).
# ########################################################
@login_required
@admin_required
def institution_list_view(request):
    institutions = Institution.objects.all()
    return render(
        request,
        "core/institution_list.html",
        {"title": "Institutions", "institutions": institutions},
    )


@login_required
@admin_required
def institution_detail_view(request, pk):
    """Everything attached to one institution — its programs (each with
    their courses) and its people — on a single page, with the controls to
    attach a new program or course to it. Super Admin only."""
    institution = get_object_or_404(Institution, pk=pk)
    programs = list(
        institution.programs.all().prefetch_related("course_set").order_by("title")
    )
    members = institution.members.all()
    org_admins = list(members.filter(is_org_admin=True).order_by("first_name", "last_name"))
    return render(
        request,
        "core/institution_detail.html",
        {
            "title": institution.name,
            "institution": institution,
            "programs": programs,
            "org_admins": org_admins,
            "course_count": sum(len(p.course_set.all()) for p in programs),
            "org_admin_count": len(org_admins),
            "lecturer_count": members.filter(is_lecturer=True).count(),
            "student_count": members.filter(is_student=True).count(),
        },
    )


@login_required
@org_admin_required
def organization_profile_view(request):
    """An org admin's read-only view of their own organization's profile as
    it stands in the LMS. A superuser isn't tied to one institution, so
    send them to the full list instead."""
    institution = request.user.institution
    if institution is None:
        if request.user.is_superuser:
            return redirect("institution_list")
        messages.info(request, "Your account isn't linked to an organization yet.")
        return redirect("home")
    return render(
        request,
        "core/organization_profile.html",
        {"title": "Organization", "institution": institution},
    )


@login_required
@admin_required
def institution_add_view(request):
    if request.method == "POST":
        form = InstitutionForm(request.POST)
        if form.is_valid():
            institution = form.save()
            messages.success(
                request,
                f'Institution "{institution.name}" has been created. '
                "Add an org admin for it below to put it to use.",
            )
            return redirect("institution_detail", pk=institution.pk)
        else:
            messages.error(request, "Correct the error(s) below.")
    else:
        form = InstitutionForm()
    return render(
        request,
        "core/institution_form.html",
        {"title": "Add Institution", "form": form},
    )


@login_required
@admin_required
def institution_edit_view(request, pk):
    institution = get_object_or_404(Institution, pk=pk)
    if request.method == "POST":
        form = InstitutionForm(request.POST, instance=institution)
        if form.is_valid():
            form.save()
            messages.success(
                request, f'Institution "{institution.name}" has been updated.'
            )
            return redirect("institution_list")
        else:
            messages.error(request, "Correct the error(s) below.")
    else:
        form = InstitutionForm(instance=institution)
    return render(
        request,
        "core/institution_form.html",
        {"title": f"Edit — {institution.name}", "form": form},
    )


@login_required
@admin_required
def institution_delete_view(request, pk):
    institution = get_object_or_404(Institution, pk=pk)
    if institution.programs.exists() or institution.members.exists():
        messages.error(
            request,
            f'"{institution.name}" still has programs or accounts attached — '
            "move or remove those first.",
        )
        return redirect("institution_list")
    name = institution.name
    institution.delete()
    messages.success(request, f'Institution "{name}" has been deleted.')
    return redirect("institution_list")


# ########################################################
# Site configuration
# ########################################################
@login_required
@org_admin_required
def toggle_course_registration(request):
    if request.method == "POST":
        config = SiteConfiguration.get_solo()
        config.course_registration_open = not config.course_registration_open
        config.save()
        if config.course_registration_open:
            messages.success(request, "Course registration is now open to students.")
        else:
            messages.success(request, "Course registration is now closed to students.")
    return redirect("admin_panel")


@login_required
@org_admin_required
def set_read_aloud_voice(request):
    if request.method == "POST":
        config = SiteConfiguration.get_solo()
        config.read_aloud_voice_name = request.POST.get("voice_name", "").strip()
        config.read_aloud_voice_lang = request.POST.get("voice_lang", "").strip()
        config.save()
        messages.success(request, "Default read-aloud voice has been updated.")
    return redirect("admin_panel")


# ########################################################
# News & Events
# ########################################################
@login_required
def home_view(request):
    items = NewsAndEvents.objects.all().order_by("-updated_date")
    context = {
        "title": "News & Events",
        "items": items,
    }
    return render(request, "core/index.html", context)


@login_required
@org_admin_required
def dashboard_view(request):
    logs = ActivityLog.objects.all().order_by("-created_at")[:10]
    gender_count = Student.get_gender_count()

    # Student level breakdown (e.g. Bachelor Degree / Master Degree).
    level_display = dict(Student._meta.get_field("level").choices)
    level_rows = (
        Student.objects.exclude(level__isnull=True)
        .values("level")
        .annotate(count=Count("id"))
        .order_by("level")
    )
    level_labels = [str(level_display.get(row["level"], row["level"])) for row in level_rows]
    level_values = [row["count"] for row in level_rows]

    # Students enrolled per program.
    program_rows = (
        Student.objects.exclude(program__isnull=True)
        .values("program__title")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    program_labels = [row["program__title"] for row in program_rows]
    program_values = [row["count"] for row in program_rows]

    # Average total score per program, from courses students have taken.
    grade_rows = (
        TakenCourse.objects.exclude(course__program__isnull=True)
        .values("course__program__title")
        .annotate(avg_total=Avg("total"))
        .order_by("course__program__title")
    )
    grade_labels = [row["course__program__title"] for row in grade_rows]
    grade_values = [round(float(row["avg_total"]), 1) for row in grade_rows]

    # Operational checklist: things an admin would actually want to act on.
    current_session = Session.objects.filter(is_current_session=True).first()
    current_semester = Semester.objects.filter(is_current_semester=True).first()
    unallocated_courses = Course.objects.filter(allocated_course__isnull=True).order_by("title")
    site_config = SiteConfiguration.get_solo()

    context = {
        "student_count": User.objects.get_student_count(),
        "lecturer_count": User.objects.get_lecturer_count(),
        "superuser_count": User.objects.get_superuser_count(),
        "males_count": gender_count["M"],
        "females_count": gender_count["F"],
        "logs": logs,
        "level_labels": level_labels,
        "level_values": level_values,
        "program_labels": program_labels,
        "program_values": program_values,
        "grade_labels": grade_labels,
        "grade_values": grade_values,
        "current_session": current_session,
        "current_semester": current_semester,
        "unallocated_courses": unallocated_courses,
        "site_config": site_config,
    }
    return render(request, "core/dashboard.html", context)


@login_required
@org_admin_required
def post_add(request):
    if request.method == "POST":
        form = NewsAndEventsForm(request.POST, request.FILES)
        title = request.POST.get("title")
        if form.is_valid():
            form.save()

            messages.success(request, (title + " has been uploaded."))
            return redirect("home")
        else:
            messages.error(request, "Please correct the error(s) below.")
    else:
        form = NewsAndEventsForm()
    return render(
        request,
        "core/post_add.html",
        {
            "title": "Add Post",
            "form": form,
        },
    )


@login_required
@org_admin_required
def edit_post(request, pk):
    instance = get_object_or_404(NewsAndEvents, pk=pk)
    if request.method == "POST":
        form = NewsAndEventsForm(request.POST, request.FILES, instance=instance)
        title = request.POST.get("title")
        if form.is_valid():
            form.save()

            messages.success(request, (title + " has been updated."))
            return redirect("home")
        else:
            messages.error(request, "Please correct the error(s) below.")
    else:
        form = NewsAndEventsForm(instance=instance)
    return render(
        request,
        "core/post_add.html",
        {
            "title": "Edit Post",
            "form": form,
        },
    )


@login_required
@org_admin_required
def delete_post(request, pk):
    post = get_object_or_404(NewsAndEvents, pk=pk)
    title = post.title
    post.delete()
    messages.success(request, (title + " has been deleted."))
    return redirect("home")


# ########################################################
# Session
# ########################################################
@login_required
@courses_read_required
def session_list_view(request):
    """Show list of all sessions"""
    sessions = Session.objects.all().order_by("-is_current_session", "-session")
    return render(request, "core/session_list.html", {"sessions": sessions})


@login_required
@org_admin_required
def session_add_view(request):
    """check request method, if POST we add session otherwise show empty form"""
    if request.method == "POST":
        form = SessionForm(request.POST)
        if form.is_valid():
            data = form.data.get(
                "is_current_session"
            )  # returns string of 'True' if the user selected Yes
            print(data)
            if data == "true":
                sessions = Session.objects.all()
                if sessions:
                    for session in sessions:
                        if session.is_current_session == True:
                            unset = Session.objects.get(is_current_session=True)
                            unset.is_current_session = False
                            unset.save()
                    form.save()
                else:
                    form.save()
            else:
                form.save()
            messages.success(request, "Session added successfully. ")
            return redirect("session_list")

    else:
        form = SessionForm()
    return render(request, "core/session_update.html", {"form": form})


@login_required
@org_admin_required
def session_update_view(request, pk):
    session = Session.objects.get(pk=pk)
    if request.method == "POST":
        form = SessionForm(request.POST, instance=session)
        data = form.data.get("is_current_session")
        if data == "true":
            sessions = Session.objects.all()
            if sessions:
                for session in sessions:
                    if session.is_current_session == True:
                        unset = Session.objects.get(is_current_session=True)
                        unset.is_current_session = False
                        unset.save()

            if form.is_valid():
                form.save()
                messages.success(request, "Session updated successfully. ")
                return redirect("session_list")
        else:
            form = SessionForm(request.POST, instance=session)
            if form.is_valid():
                form.save()
                messages.success(request, "Session updated successfully. ")
                return redirect("session_list")

    else:
        form = SessionForm(instance=session)
    return render(request, "core/session_update.html", {"form": form})


@login_required
@org_admin_required
def session_delete_view(request, pk):
    session = get_object_or_404(Session, pk=pk)

    if session.is_current_session:
        messages.error(request, "You cannot delete current session")
        return redirect("session_list")
    else:
        session.delete()
        messages.success(request, "Session successfully deleted")
    return redirect("session_list")


# ########################################################


# ########################################################
# Semester
# ########################################################
@login_required
@courses_read_required
def semester_list_view(request):
    semesters = Semester.objects.all().order_by("-is_current_semester", "-semester")
    return render(
        request,
        "core/semester_list.html",
        {
            "semesters": semesters,
        },
    )


@login_required
@org_admin_required
def semester_add_view(request):
    if request.method == "POST":
        form = SemesterForm(request.POST)
        if form.is_valid():
            data = form.data.get(
                "is_current_semester"
            )  # returns string of 'True' if the user selected Yes
            if data == "True":
                semester = form.data.get("semester")
                ss = form.data.get("session")
                session = Session.objects.get(pk=ss)
                try:
                    if Semester.objects.get(semester=semester, session=ss):
                        messages.error(
                            request,
                            semester
                            + " semester in "
                            + session.session
                            + " session already exist",
                        )
                        return redirect("add_semester")
                except:
                    semesters = Semester.objects.all()
                    sessions = Session.objects.all()
                    if semesters:
                        for semester in semesters:
                            if semester.is_current_semester == True:
                                unset_semester = Semester.objects.get(
                                    is_current_semester=True
                                )
                                unset_semester.is_current_semester = False
                                unset_semester.save()
                        for session in sessions:
                            if session.is_current_session == True:
                                unset_session = Session.objects.get(
                                    is_current_session=True
                                )
                                unset_session.is_current_session = False
                                unset_session.save()

                    new_session = request.POST.get("session")
                    set_session = Session.objects.get(pk=new_session)
                    set_session.is_current_session = True
                    set_session.save()
                    form.save()
                    messages.success(request, "Semester added successfully.")
                    return redirect("semester_list")

            form.save()
            messages.success(request, "Semester added successfully. ")
            return redirect("semester_list")
    else:
        form = SemesterForm()
    return render(request, "core/semester_update.html", {"form": form})


@login_required
@org_admin_required
def semester_update_view(request, pk):
    semester = Semester.objects.get(pk=pk)
    if request.method == "POST":
        if (
            request.POST.get("is_current_semester") == "True"
        ):  # returns string of 'True' if the user selected yes for 'is current semester'
            unset_semester = Semester.objects.get(is_current_semester=True)
            unset_semester.is_current_semester = False
            unset_semester.save()
            unset_session = Session.objects.get(is_current_session=True)
            unset_session.is_current_session = False
            unset_session.save()
            new_session = request.POST.get("session")
            form = SemesterForm(request.POST, instance=semester)
            if form.is_valid():
                set_session = Session.objects.get(pk=new_session)
                set_session.is_current_session = True
                set_session.save()
                form.save()
                messages.success(request, "Semester updated successfully !")
                return redirect("semester_list")
        else:
            form = SemesterForm(request.POST, instance=semester)
            if form.is_valid():
                form.save()
                return redirect("semester_list")

    else:
        form = SemesterForm(instance=semester)
    return render(request, "core/semester_update.html", {"form": form})


@login_required
@org_admin_required
def semester_delete_view(request, pk):
    semester = get_object_or_404(Semester, pk=pk)
    if semester.is_current_semester:
        messages.error(request, "You cannot delete current semester")
        return redirect("semester_list")
    else:
        semester.delete()
        messages.success(request, "Semester successfully deleted")
    return redirect("semester_list")
