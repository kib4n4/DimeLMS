from django.http.response import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.views import LoginView
from django.views.generic import CreateView, ListView
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.contrib.auth.forms import PasswordChangeForm
from django_filters.views import FilterView
from core.models import Session, Semester, SiteConfiguration
from course.models import Course
from result.models import TakenCourse
from .decorators import org_admin_required, students_read_required
from .forms import (
    StaffAddForm,
    StudentAddForm,
    ProfileUpdateForm,
    ParentAddForm,
    ProgramUpdateForm,
    EmailAuthenticationForm,
    LecturerBulkUploadForm,
    StudentBulkUploadForm,
)
from .models import User, Student, Parent
from .filters import LecturerFilter, StudentFilter
from .utils import (
    parse_lecturer_bulk_upload,
    build_lecturer_bulk_upload_template,
    parse_student_bulk_upload,
    build_student_bulk_upload_template,
)

# to generate pdf from template we need the following
from django.http import HttpResponse
from django.template.loader import get_template  # to get template which render as pdf
from xhtml2pdf import pisa
from django.template.loader import (
    render_to_string,
)  # to render a template into a string


class EmailLoginView(LoginView):
    """Login by email (see EmailAuthenticationForm), expiring the session on
    browser close unless "Remember me" is checked."""

    form_class = EmailAuthenticationForm
    template_name = "registration/login.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        if not self.request.POST.get("remember_me"):
            self.request.session.set_expiry(0)
        return response


def validate_username(request):
    username = request.GET.get("username", None)
    data = {"is_taken": User.objects.filter(username__iexact=username).exists()}
    return JsonResponse(data)


def register(request):
    if request.method == "POST":
        form = StudentAddForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Account created successfully.")
        else:
            messages.error(
                request, "Something is not correct, please fill all fields correctly."
            )
    else:
        form = StudentAddForm()
    return render(request, "registration/register.html", {"form": form})


@login_required
def profile(request):
    """Show profile of any user that fire out the request"""
    current_session = Session.objects.filter(is_current_session=True).first()
    current_semester = Semester.objects.filter(
        is_current_semester=True, session=current_session
    ).first()

    if request.user.is_lecturer:
        courses = Course.objects.filter(
            allocated_course__lecturer__pk=request.user.id
        ).filter(semester=current_semester)
        return render(
            request,
            "accounts/profile.html",
            {
                "title": request.user.get_full_name,
                "courses": courses,
                "current_session": current_session,
                "current_semester": current_semester,
            },
        )
    elif request.user.is_student:
        level = Student.objects.get(student__pk=request.user.id)
        try:
            parent = Parent.objects.get(student=level)
        except:
            parent = "no parent set"
        courses = TakenCourse.objects.filter(
            student__student__id=request.user.id, course__level=level.level
        )
        context = {
            "title": request.user.get_full_name,
            "parent": parent,
            "courses": courses,
            "level": level,
            "current_session": current_session,
            "current_semester": current_semester,
        }
        return render(request, "accounts/profile.html", context)
    else:
        staff = User.objects.filter(is_lecturer=True)
        return render(
            request,
            "accounts/profile.html",
            {
                "title": request.user.get_full_name,
                "staff": staff,
                "current_session": current_session,
                "current_semester": current_semester,
            },
        )


# function that generate pdf by taking Django template and its context,
def render_to_pdf(template_name, context):
    """Renders a given template to PDF format."""
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'filename="profile.pdf"'  # Set default filename

    template = render_to_string(template_name, context)
    pdf = pisa.CreatePDF(template, dest=response)
    if pdf.err:
        return HttpResponse("We had some problems generating the PDF")

    return response


@login_required
@students_read_required
def profile_single(request, id):
    """Show profile of any selected user"""
    if request.user.id == id:
        return redirect("/profile/")

    current_session = Session.objects.filter(is_current_session=True).first()
    current_semester = Semester.objects.filter(
        is_current_semester=True, session=current_session
    ).first()

    user = User.objects.get(pk=id)
    """
    If download_pdf exists, instead of calling render_to_pdf directly, 
    pass the context dictionary built for the specific user type 
    (lecturer, student, or superuser) to the render_to_pdf function.
    """
    if request.GET.get("download_pdf"):
        if user.is_lecturer:
            courses = Course.objects.filter(allocated_course__lecturer__pk=id).filter(
                semester=current_semester
            )
            context = {
                "title": user.get_full_name,
                "user": user,
                "user_type": "Facilitator",
                "courses": courses,
                "current_session": current_session,
                "current_semester": current_semester,
            }
        elif user.is_student:
            student = Student.objects.get(student__pk=id)
            courses = TakenCourse.objects.filter(
                student__student__id=id, course__level=student.level
            )
            context = {
                "title": user.get_full_name,
                "user": user,
                "user_type": "student",
                "courses": courses,
                "student": student,
                "current_session": current_session,
                "current_semester": current_semester,
            }
        else:
            context = {
                "title": user.get_full_name,
                "user": user,
                "user_type": "superuser",
                "current_session": current_session,
                "current_semester": current_semester,
            }
        return render_to_pdf("pdf/profile_single.html", context)

    else:
        if user.is_lecturer:
            courses = Course.objects.filter(allocated_course__lecturer__pk=id).filter(
                semester=current_semester
            )
            context = {
                "title": user.get_full_name,
                "user": user,
                "user_type": "Facilitator",
                "courses": courses,
                "current_session": current_session,
                "current_semester": current_semester,
            }
            return render(request, "accounts/profile_single.html", context)
        elif user.is_student:
            student = Student.objects.get(student__pk=id)
            courses = TakenCourse.objects.filter(
                student__student__id=id, course__level=student.level
            )
            context = {
                "title": user.get_full_name,
                "user": user,
                "user_type": "student",
                "courses": courses,
                "student": student,
                "current_session": current_session,
                "current_semester": current_semester,
            }
            return render(request, "accounts/profile_single.html", context)
        else:
            context = {
                "title": user.get_full_name,
                "user": user,
                "user_type": "superuser",
                "current_session": current_session,
                "current_semester": current_semester,
            }
            return render(request, "accounts/profile_single.html", context)


@login_required
@org_admin_required
def admin_panel(request):
    return render(
        request,
        "setting/admin_panel.html",
        {
            "title": request.user.get_full_name,
            "site_config": SiteConfiguration.get_solo(),
        },
    )


# ########################################################


# ########################################################
# Setting views
# ########################################################
@login_required
def profile_update(request):
    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect("profile")
        else:
            messages.error(request, "Please correct the error(s) below.")
    else:
        form = ProfileUpdateForm(instance=request.user)
    return render(
        request,
        "setting/profile_info_change.html",
        {
            "title": "Setting",
            "form": form,
        },
    )


@login_required
def change_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your password was successfully updated!")
            return redirect("profile")
        else:
            messages.error(request, "Please correct the error(s) below. ")
    else:
        form = PasswordChangeForm(request.user)
    return render(
        request,
        "setting/password_change.html",
        {
            "form": form,
        },
    )


# ########################################################


@login_required
@org_admin_required
def staff_add_view(request):
    if request.method == "POST":
        form = StaffAddForm(request.POST)
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        email = request.POST.get("email")

        if form.is_valid():

            form.save()
            messages.success(
                request,
                "Account for facilitator "
                + first_name
                + " "
                + last_name
                + " has been created. An email with account credentials will be sent to "
                + email
                + " within a minute.",
            )
            return redirect("lecturer_list")
    else:
        form = StaffAddForm()

    context = {
        "title": "Facilitator Add",
        "form": form,
    }

    return render(request, "accounts/add_staff.html", context)


@login_required
@org_admin_required
def lecturer_bulk_upload_view(request):
    row_errors = []
    created_users = []

    if request.method == "POST":
        form = LecturerBulkUploadForm(request.POST, request.FILES)
        if form.is_valid():
            created_users, row_errors = parse_lecturer_bulk_upload(
                form.cleaned_data["excel_file"]
            )
            if created_users:
                messages.success(
                    request,
                    f"{len(created_users)} facilitator account(s) created. "
                    "Each will receive an email with their login credentials.",
                )
            if row_errors:
                messages.error(
                    request,
                    f"{len(row_errors)} row(s) could not be imported — see details below.",
                )
            form = LecturerBulkUploadForm()
    else:
        form = LecturerBulkUploadForm()

    context = {
        "title": "Bulk Upload Facilitators",
        "form": form,
        "row_errors": row_errors,
        "created_count": len(created_users),
    }
    return render(request, "accounts/lecturer_bulk_upload.html", context)


@login_required
@org_admin_required
def lecturer_bulk_upload_template(request):
    wb = build_lecturer_bulk_upload_template()
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = (
        'attachment; filename="facilitators_bulk_upload_template.xlsx"'
    )
    wb.save(response)
    return response


@login_required
@org_admin_required
def edit_staff(request, pk):
    instance = get_object_or_404(User, is_lecturer=True, pk=pk)
    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, request.FILES, instance=instance)
        full_name = instance.get_full_name
        if form.is_valid():
            form.save()

            messages.success(request, "Facilitator " + full_name + " has been updated.")
            return redirect("lecturer_list")
        else:
            messages.error(request, "Please correct the error below.")
    else:
        form = ProfileUpdateForm(instance=instance)
    return render(
        request,
        "accounts/edit_lecturer.html",
        {
            "title": "Edit Facilitator",
            "form": form,
        },
    )


@method_decorator([login_required, org_admin_required], name="dispatch")
class LecturerFilterView(FilterView):
    filterset_class = LecturerFilter
    queryset = User.objects.filter(is_lecturer=True)
    template_name = "accounts/lecturer_list.html"
    paginate_by = 10  # if pagination is desired

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Facilitators"
        return context


# lecturers list pdf
@login_required
@org_admin_required
def render_lecturer_pdf_list(request):
    lecturers = User.objects.filter(is_lecturer=True)
    template_path = "pdf/lecturer_list.html"
    context = {"lecturers": lecturers}
    response = HttpResponse(
        content_type="application/pdf"
    )  # convert the response to pdf
    response["Content-Disposition"] = 'filename="lecturers_list.pdf"'
    # find the template and render it.
    template = get_template(template_path)
    html = template.render(context)
    # create a pdf
    pisa_status = pisa.CreatePDF(html, dest=response)
    # if error then show some funny view
    if pisa_status.err:
        return HttpResponse("We had some errors <pre>" + html + "</pre>")
    return response


# @login_required
# @lecturer_required
# def delete_staff(request, pk):
#     staff = get_object_or_404(User, pk=pk)
#     staff.delete()
#     return redirect('lecturer_list')


@login_required
@org_admin_required
def delete_staff(request, pk):
    lecturer = get_object_or_404(User, pk=pk)
    full_name = lecturer.get_full_name
    lecturer.delete()
    messages.success(request, "Facilitator " + full_name + " has been deleted.")
    return redirect("lecturer_list")


# ########################################################


# ########################################################
# Student views
# ########################################################
@login_required
@org_admin_required
def student_add_view(request):
    if request.method == "POST":
        form = StudentAddForm(request.POST)
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        email = request.POST.get("email")
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Account for "
                + first_name
                + " "
                + last_name
                + " has been created. An email with account credentials will be sent to "
                + email
                + " within a minute.",
            )
            return redirect("student_list")
        else:
            messages.error(request, "Correct the error(s) below.")
    else:
        form = StudentAddForm()

    return render(
        request,
        "accounts/add_student.html",
        {"title": "Add Student", "form": form},
    )


@login_required
@org_admin_required
def student_bulk_upload_view(request):
    row_errors = []
    created_users = []

    if request.method == "POST":
        form = StudentBulkUploadForm(request.POST, request.FILES)
        if form.is_valid():
            created_users, row_errors = parse_student_bulk_upload(
                form.cleaned_data["excel_file"]
            )
            if created_users:
                messages.success(
                    request,
                    f"{len(created_users)} student account(s) created. "
                    "Each will receive an email with their login credentials.",
                )
            if row_errors:
                messages.error(
                    request,
                    f"{len(row_errors)} row(s) could not be imported — see details below.",
                )
            form = StudentBulkUploadForm()
    else:
        form = StudentBulkUploadForm()

    context = {
        "title": "Bulk Upload Students",
        "form": form,
        "row_errors": row_errors,
        "created_count": len(created_users),
    }
    return render(request, "accounts/student_bulk_upload.html", context)


@login_required
@org_admin_required
def student_bulk_upload_template(request):
    wb = build_student_bulk_upload_template()
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = (
        'attachment; filename="students_bulk_upload_template.xlsx"'
    )
    wb.save(response)
    return response


@login_required
@org_admin_required
def edit_student(request, pk):
    # instance = User.objects.get(pk=pk)
    instance = get_object_or_404(User, is_student=True, pk=pk)
    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, request.FILES, instance=instance)
        full_name = instance.get_full_name
        if form.is_valid():
            form.save()

            messages.success(request, ("Student " + full_name + " has been updated."))
            return redirect("student_list")
        else:
            messages.error(request, "Please correct the error below.")
    else:
        form = ProfileUpdateForm(instance=instance)
    return render(
        request,
        "accounts/edit_student.html",
        {
            "title": "Edit-profile",
            "form": form,
        },
    )


@method_decorator([login_required, students_read_required], name="dispatch")
class StudentListView(FilterView):
    queryset = Student.objects.all()
    filterset_class = StudentFilter
    template_name = "accounts/student_list.html"
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Students"
        return context


# student list pdf
@login_required
@students_read_required
def render_student_pdf_list(request):
    students = Student.objects.all()
    template_path = "pdf/student_list.html"
    context = {"students": students}
    response = HttpResponse(
        content_type="application/pdf"
    )  # convert the response to pdf
    response["Content-Disposition"] = 'filename="students_list.pdf"'
    # find the template and render it.
    template = get_template(template_path)
    html = template.render(context)
    # create a pdf
    pisa_status = pisa.CreatePDF(html, dest=response)
    # if error then show some funny view
    if pisa_status.err:
        return HttpResponse("We had some errors <pre>" + html + "</pre>")
    return response


@login_required
@org_admin_required
def delete_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    # full_name = student.user.get_full_name
    student.delete()
    messages.success(request, "Student has been deleted.")
    return redirect("student_list")


@login_required
@org_admin_required
def edit_student_program(request, pk):

    instance = get_object_or_404(Student, student_id=pk)
    user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = ProgramUpdateForm(request.POST, request.FILES, instance=instance)
        full_name = user.get_full_name
        if form.is_valid():
            form.save()
            messages.success(request, message=full_name + " program has been updated.")
            url = (
                "/accounts/profile/" + user.id.__str__() + "/detail/"
            )  # Botched job, must optimize
            return redirect(to=url)
        else:
            messages.error(request, "Please correct the error(s) below.")
    else:
        form = ProgramUpdateForm(instance=instance)
    return render(
        request,
        "accounts/edit_student_program.html",
        context={"title": "Edit-program", "form": form, "student": instance},
    )


# ########################################################


class ParentAdd(CreateView):
    model = Parent
    form_class = ParentAddForm
    template_name = "accounts/parent_form.html"


# def parent_add(request):
#     if request.method == 'POST':
#         form = ParentAddForm(request.POST)
#         if form.is_valid():
#             form.save()
#             return redirect('student_list')
#     else:
#         form = ParentAddForm(request.POST)
