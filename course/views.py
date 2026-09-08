import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Avg, Max, Min, Count
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView
from django.core.paginator import Paginator
from django.conf import settings
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django_filters.views import FilterView

from accounts.models import User, Student
from core.models import Session, Semester, SiteConfiguration
from result.models import TakenCourse
from accounts.decorators import (
    student_required,
    org_admin_required,
    courses_read_required,
    course_materials_write_required,
    students_read_required,
)
from .forms import (
    ProgramForm,
    CourseAddForm,
    CourseAllocationForm,
    EditCourseAllocationForm,
    UploadFormFile,
    UploadFormVideo,
    UploadFormLink,
    ModuleForm,
    ModuleSplitForm,
)
from .filters import ProgramFilter, CourseAllocationFilter
from .utils import extract_docx_paragraphs, split_docx_into_topics
from .models import (
    Program,
    Course,
    CourseAllocation,
    Upload,
    UploadVideo,
    CourseLink,
    Module,
    ModuleProgress,
)


@method_decorator([login_required, courses_read_required], name="dispatch")
class ProgramFilterView(FilterView):
    filterset_class = ProgramFilter
    template_name = "course/program_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Programs"
        return context


@login_required
@org_admin_required
def program_add(request):
    if request.method == "POST":
        form = ProgramForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request, request.POST.get("title") + " program has been created."
            )
            return redirect("programs")
        else:
            messages.error(request, "Correct the error(S) below.")
    else:
        form = ProgramForm()

    return render(
        request,
        "course/program_add.html",
        {
            "title": "Add Program",
            "form": form,
        },
    )


@login_required
def program_detail(request, pk):
    program = Program.objects.get(pk=pk)
    courses = Course.objects.filter(program_id=pk).order_by("-year")
    credits = Course.objects.aggregate(Sum("credit"))

    paginator = Paginator(courses, 10)
    page = request.GET.get("page")

    courses = paginator.get_page(page)

    return render(
        request,
        "course/program_single.html",
        {
            "title": program.title,
            "program": program,
            "courses": courses,
            "credits": credits,
        },
    )


@login_required
@org_admin_required
def program_edit(request, pk):
    program = Program.objects.get(pk=pk)

    if request.method == "POST":
        form = ProgramForm(request.POST, instance=program)
        if form.is_valid():
            form.save()
            messages.success(
                request, str(request.POST.get("title")) + " program has been updated."
            )
            return redirect("programs")
    else:
        form = ProgramForm(instance=program)

    return render(
        request,
        "course/program_add.html",
        {"title": "Edit Program", "form": form},
    )


@login_required
@org_admin_required
def program_delete(request, pk):
    program = Program.objects.get(pk=pk)
    title = program.title
    program.delete()
    messages.success(request, "Program " + title + " has been deleted.")

    return redirect("programs")


# ########################################################


# ########################################################
# Course views
# ########################################################
@login_required
def course_single(request, slug):
    course = Course.objects.get(slug=slug)
    files = Upload.objects.filter(course__slug=slug)
    videos = UploadVideo.objects.filter(course__slug=slug)
    links = CourseLink.objects.filter(course__slug=slug)

    # lecturers = User.objects.filter(allocated_lecturer__pk=course.id)
    lecturers = CourseAllocation.objects.filter(courses__pk=course.id)

    return render(
        request,
        "course/course_single.html",
        {
            "title": course.title,
            "course": course,
            "files": files,
            "videos": videos,
            "links": links,
            "lecturers": lecturers,
            "media_url": settings.MEDIA_ROOT,
        },
    )


@login_required
@org_admin_required
def course_add(request, pk):
    users = User.objects.all()
    if request.method == "POST":
        form = CourseAddForm(request.POST)
        course_name = request.POST.get("title")
        course_code = request.POST.get("code")
        if form.is_valid():
            form.save()
            messages.success(
                request, (course_name + "(" + course_code + ")" + " has been created.")
            )
            return redirect("program_detail", pk=request.POST.get("program"))
        else:
            messages.error(request, "Correct the error(s) below.")
    else:
        form = CourseAddForm(initial={"program": Program.objects.get(pk=pk)})

    return render(
        request,
        "course/course_add.html",
        {
            "title": "Add Course",
            "form": form,
            "program": pk,
            "users": users,
        },
    )


@login_required
@org_admin_required
def course_edit(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if request.method == "POST":
        form = CourseAddForm(request.POST, instance=course)
        course_name = request.POST.get("title")
        course_code = request.POST.get("code")
        if form.is_valid():
            form.save()
            messages.success(
                request, (course_name + "(" + course_code + ")" + " has been updated.")
            )
            return redirect("program_detail", pk=request.POST.get("program"))
        else:
            messages.error(request, "Correct the error(s) below.")
    else:
        form = CourseAddForm(instance=course)

    return render(
        request,
        "course/course_add.html",
        {
            "title": "Edit Course",
            # 'form': form, 'program': pk, 'course': pk
            "form": form,
        },
    )


@login_required
@org_admin_required
def course_delete(request, slug):
    course = Course.objects.get(slug=slug)
    # course_name = course.title
    course.delete()
    messages.success(request, "Course " + course.title + " has been deleted.")

    return redirect("program_detail", pk=course.program.id)


# ########################################################


# ########################################################
# Course Allocation
# ########################################################
@method_decorator([login_required, org_admin_required], name="dispatch")
class CourseAllocationFormView(CreateView):
    form_class = CourseAllocationForm
    template_name = "course/course_allocation_form.html"

    def get_form_kwargs(self):
        kwargs = super(CourseAllocationFormView, self).get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        # if a staff has been allocated a course before update it else create new
        lecturer = form.cleaned_data["lecturer"]
        selected_courses = form.cleaned_data["courses"]
        courses = ()
        for course in selected_courses:
            courses += (course.pk,)
        # print(courses)

        try:
            a = CourseAllocation.objects.get(lecturer=lecturer)
        except:
            a = CourseAllocation.objects.create(lecturer=lecturer)
        for i in range(0, selected_courses.count()):
            a.courses.add(courses[i])
            a.save()
        return redirect("course_allocation_view")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Assign Course"
        return context


@method_decorator([login_required, org_admin_required], name="dispatch")
class CourseAllocationFilterView(FilterView):
    filterset_class = CourseAllocationFilter
    template_name = "course/course_allocation_view.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Course Allocations"
        return context


@login_required
@org_admin_required
def edit_allocated_course(request, pk):
    allocated = get_object_or_404(CourseAllocation, pk=pk)
    if request.method == "POST":
        form = EditCourseAllocationForm(request.POST, instance=allocated)
        if form.is_valid():
            form.save()
            messages.success(request, "course assigned has been updated.")
            return redirect("course_allocation_view")
    else:
        form = EditCourseAllocationForm(instance=allocated)

    return render(
        request,
        "course/course_allocation_form.html",
        {"title": "Edit Course Allocated", "form": form, "allocated": pk},
    )


@login_required
@org_admin_required
def deallocate_course(request, pk):
    course = CourseAllocation.objects.get(pk=pk)
    course.delete()
    messages.success(request, "successfully deallocate!")
    return redirect("course_allocation_view")


# ########################################################


# ########################################################
# File Upload views
# ########################################################
@login_required
@course_materials_write_required
def handle_file_upload(request, slug):
    course = Course.objects.get(slug=slug)
    if request.method == "POST":
        form = UploadFormFile(request.POST, request.FILES, course=course)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.course = course
            obj.save()

            messages.success(
                request, (request.POST.get("title") + " has been uploaded.")
            )
            return redirect("course_detail", slug=slug)
    else:
        form = UploadFormFile(course=course)
    return render(
        request,
        "upload/upload_file_form.html",
        {"title": "File Upload", "form": form, "course": course},
    )


@login_required
@course_materials_write_required
def handle_file_edit(request, slug, file_id):
    course = Course.objects.get(slug=slug)
    instance = Upload.objects.get(pk=file_id)
    if request.method == "POST":
        form = UploadFormFile(request.POST, request.FILES, instance=instance, course=course)
        # file_name = request.POST.get('name')
        if form.is_valid():
            form.save()
            messages.success(
                request, (request.POST.get("title") + " has been updated.")
            )
            return redirect("course_detail", slug=slug)
    else:
        form = UploadFormFile(instance=instance, course=course)

    return render(
        request,
        "upload/upload_file_form.html",
        {"title": instance.title, "form": form, "course": course},
    )


@login_required
@course_materials_write_required
def handle_file_delete(request, slug, file_id):
    file = Upload.objects.get(pk=file_id)
    # file_name = file.name
    file.delete()

    messages.success(request, (file.title + " has been deleted."))
    return redirect("course_detail", slug=slug)


@login_required
def document_single(request, slug, file_id):
    """
    In-page reading view for a course document — PDFs render inline via
    the browser's own PDF viewer; .docx files show their extracted text.
    Anything else (legacy .doc, xls/xlsx, ppt/pptx, zip/rar/7zip) has no
    viewer_kind and isn't linked here — those keep the plain download
    link on the course page instead.
    """
    course = get_object_or_404(Course, slug=slug)
    document = get_object_or_404(Upload, pk=file_id, course=course)

    if not document.viewer_kind:
        return redirect(document.file.url)

    paragraphs = None
    extraction_error = None
    if document.viewer_kind == "docx":
        try:
            document.file.open("rb")
            paragraphs = extract_docx_paragraphs(document.file)
        except Exception:
            extraction_error = "This document couldn't be opened for preview."
        finally:
            document.file.close()

    readable_siblings = [
        upload
        for upload in Upload.objects.filter(course=course).order_by("upload_time", "pk")
        if upload.viewer_kind
    ]
    position = next(
        (i for i, upload in enumerate(readable_siblings) if upload.pk == document.pk),
        None,
    )
    previous_doc = (
        readable_siblings[position - 1] if position is not None and position > 0 else None
    )
    next_doc = (
        readable_siblings[position + 1]
        if position is not None and position < len(readable_siblings) - 1
        else None
    )

    return render(
        request,
        "upload/document_single.html",
        {
            "course": course,
            "document": document,
            "paragraphs": paragraphs,
            "extraction_error": extraction_error,
            "previous_doc": previous_doc,
            "next_doc": next_doc,
        },
    )


# ########################################################
# Video Upload views
# ########################################################
@login_required
@course_materials_write_required
def handle_video_upload(request, slug):
    course = Course.objects.get(slug=slug)
    if request.method == "POST":
        form = UploadFormVideo(request.POST, request.FILES, course=course)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.course = course
            obj.save()

            messages.success(
                request, (request.POST.get("title") + " has been uploaded.")
            )
            return redirect("course_detail", slug=slug)
    else:
        form = UploadFormVideo(course=course)
    return render(
        request,
        "upload/upload_video_form.html",
        {"title": "Video Upload", "form": form, "course": course},
    )


@login_required
# @course_materials_write_required
def handle_video_single(request, slug, video_slug):
    course = get_object_or_404(Course, slug=slug)
    video = get_object_or_404(UploadVideo, slug=video_slug)
    return render(request, "upload/video_single.html", {"video": video})


@login_required
@course_materials_write_required
def handle_video_edit(request, slug, video_slug):
    course = Course.objects.get(slug=slug)
    instance = UploadVideo.objects.get(slug=video_slug)
    if request.method == "POST":
        form = UploadFormVideo(request.POST, request.FILES, instance=instance, course=course)
        if form.is_valid():
            form.save()
            messages.success(
                request, (request.POST.get("title") + " has been updated.")
            )
            return redirect("course_detail", slug=slug)
    else:
        form = UploadFormVideo(instance=instance, course=course)

    return render(
        request,
        "upload/upload_video_form.html",
        {"title": instance.title, "form": form, "course": course},
    )


@login_required
@course_materials_write_required
def handle_video_delete(request, slug, video_slug):
    video = get_object_or_404(UploadVideo, slug=video_slug)
    # video = UploadVideo.objects.get(slug=video_slug)
    video.delete()

    messages.success(request, (video.title + " has been deleted."))
    return redirect("course_detail", slug=slug)


# ########################################################
# YouTube link "upload" views
# ########################################################
@login_required
@course_materials_write_required
def handle_link_upload(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if request.method == "POST":
        form = UploadFormLink(request.POST, course=course)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.course = course
            obj.save()

            messages.success(
                request, (request.POST.get("title") + " has been added.")
            )
            return redirect("course_detail", slug=slug)
    else:
        form = UploadFormLink(course=course)
    return render(
        request,
        "upload/upload_link_form.html",
        {"title": "Add YouTube Link", "form": form, "course": course},
    )


@login_required
def handle_link_single(request, slug, link_slug):
    course = get_object_or_404(Course, slug=slug)
    link = get_object_or_404(CourseLink, slug=link_slug)
    return render(request, "upload/link_single.html", {"link": link})


@login_required
@course_materials_write_required
def handle_link_edit(request, slug, link_slug):
    course = get_object_or_404(Course, slug=slug)
    instance = get_object_or_404(CourseLink, slug=link_slug)
    if request.method == "POST":
        form = UploadFormLink(request.POST, instance=instance, course=course)
        if form.is_valid():
            form.save()
            messages.success(
                request, (request.POST.get("title") + " has been updated.")
            )
            return redirect("course_detail", slug=slug)
    else:
        form = UploadFormLink(instance=instance, course=course)

    return render(
        request,
        "upload/upload_link_form.html",
        {"title": instance.title, "form": form, "course": course},
    )


@login_required
@course_materials_write_required
def handle_link_delete(request, slug, link_slug):
    link = get_object_or_404(CourseLink, slug=link_slug)
    link.delete()

    messages.success(request, (link.title + " has been deleted."))
    return redirect("course_detail", slug=slug)


# ########################################################


# ########################################################
# Modules & progress tracking
# ########################################################
@login_required
@courses_read_required
def module_list(request, slug):
    """
    Everyone who can read the course can see its modules. A registered
    student additionally sees their own per-module progress bar and the
    course's overall completion; a facilitator/org admin/superuser sees
    duration + manage controls plus a link to the class-wide tracker.
    """
    course = get_object_or_404(Course, slug=slug)
    modules = course.modules.all()

    student = None
    is_registered_student = False
    progress_by_module = {}
    course_progress = None
    if request.user.is_student:
        student = Student.objects.filter(student=request.user).first()
        is_registered_student = bool(
            student and TakenCourse.objects.filter(student=student, course=course).exists()
        )
        if is_registered_student:
            progress_by_module = {
                p.module_id: p
                for p in ModuleProgress.objects.filter(student=student, module__course=course)
            }
            course_progress = course.progress_for_student(student)

    modules = list(modules)
    for module in modules:
        module.my_progress = progress_by_module.get(module.id)

    return render(
        request,
        "course/module_list.html",
        {
            "title": f"Modules — {course.title}",
            "course": course,
            "modules": modules,
            "course_progress": course_progress,
            "is_registered_student": is_registered_student,
        },
    )


@login_required
@course_materials_write_required
def module_add(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if request.method == "POST":
        form = ModuleForm(request.POST, course=course)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.course = course
            obj.save()
            low, high = course.recommended_module_duration
            if not (low <= obj.duration_minutes <= high):
                messages.warning(
                    request,
                    f'"{obj.title}" was saved, but {obj.duration_minutes} minutes is '
                    f"outside the recommended {low}–{high} minute range for a "
                    f"{course.get_length_type_display()}.",
                )
            messages.success(request, f'Module "{obj.title}" has been created.')
            return redirect("module_list", slug=slug)
    else:
        form = ModuleForm(course=course)
    return render(
        request,
        "course/module_form.html",
        {"title": "Add Module", "form": form, "course": course},
    )


@login_required
@course_materials_write_required
def module_split_view(request, slug):
    """
    Auto-generates one Module per top-level topic detected in an uploaded
    .docx — each "Heading 1"-styled paragraph starts a new topic; its
    module's `content` is everything until the next Heading 1, including
    any sub-headings (Heading 2, 3, ...) in between. See
    course.utils.split_docx_into_topics.
    """
    course = get_object_or_404(Course, slug=slug)
    if request.method == "POST":
        form = ModuleSplitForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                topics = split_docx_into_topics(form.cleaned_data["document"])
            except Exception:
                form.add_error("document", "Couldn't read that file — make sure it's a valid .docx.")
                return render(
                    request,
                    "course/module_split.html",
                    {"title": "Split Document Into Modules", "course": course, "form": form},
                )

            if not topics:
                form.add_error(
                    "document",
                    'No "Heading 1" paragraphs were found. Style each top-level topic\'s '
                    "title as Heading 1 before uploading — sub-headings (Heading 2, 3, "
                    "...) are fine and become part of that topic's content instead of "
                    "a topic of their own.",
                )
                return render(
                    request,
                    "course/module_split.html",
                    {"title": "Split Document Into Modules", "course": course, "form": form},
                )

            low, high = course.recommended_module_duration
            default_duration = round((low + high) / 2)
            starting_order = course.modules.count()

            created_modules = []
            with transaction.atomic():
                for position, topic in enumerate(topics, start=1):
                    module = Module.objects.create(
                        course=course,
                        title=topic["title"][:200],
                        content=topic["content"],
                        order=starting_order + position,
                        duration_minutes=default_duration,
                    )
                    created_modules.append(module)

            messages.success(
                request,
                f"Created {len(created_modules)} module(s) from \"{form.cleaned_data['document'].name}\". "
                f"Each was given a {default_duration}-minute default duration — adjust as needed.",
            )
            return redirect("module_list", slug=slug)
    else:
        form = ModuleSplitForm()

    return render(
        request,
        "course/module_split.html",
        {"title": "Split Document Into Modules", "course": course, "form": form},
    )


@login_required
@course_materials_write_required
def module_edit(request, slug, pk):
    course = get_object_or_404(Course, slug=slug)
    instance = get_object_or_404(Module, pk=pk, course=course)
    if request.method == "POST":
        form = ModuleForm(request.POST, instance=instance, course=course)
        if form.is_valid():
            form.save()
            messages.success(request, f'Module "{instance.title}" has been updated.')
            return redirect("module_list", slug=slug)
    else:
        form = ModuleForm(instance=instance, course=course)
    return render(
        request,
        "course/module_form.html",
        {"title": f"Edit — {instance.title}", "form": form, "course": course},
    )


@login_required
@course_materials_write_required
def module_delete(request, slug, pk):
    course = get_object_or_404(Course, slug=slug)
    module = get_object_or_404(Module, pk=pk, course=course)
    title = module.title
    module.delete()
    messages.success(request, f'Module "{title}" has been deleted.')
    return redirect("module_list", slug=slug)


@login_required
@courses_read_required
def module_detail(request, slug, pk):
    course = get_object_or_404(Course, slug=slug)
    module = get_object_or_404(Module, pk=pk, course=course)

    student = None
    progress = None
    can_track = False
    if request.user.is_student:
        student = Student.objects.filter(student=request.user).first()
        if student and TakenCourse.objects.filter(student=student, course=course).exists():
            can_track = True
            progress, _created = ModuleProgress.objects.get_or_create(
                student=student, module=module
            )

    siblings = list(course.modules.all())
    position = next((i for i, m in enumerate(siblings) if m.pk == module.pk), None)
    previous_module = siblings[position - 1] if position is not None and position > 0 else None
    next_module = (
        siblings[position + 1]
        if position is not None and position < len(siblings) - 1
        else None
    )

    return render(
        request,
        "course/module_detail.html",
        {
            "title": module.title,
            "course": course,
            "module": module,
            "files": module.uploads.all(),
            "videos": module.videos.all(),
            "links": module.links.all(),
            "progress": progress,
            "can_track": can_track,
            "previous_module": previous_module,
            "next_module": next_module,
        },
    )


@login_required
@student_required
@require_POST
def record_module_progress(request, pk):
    """
    Browser-side progress heartbeat (see module_detail.html's tracker
    script). Body: {"seconds": <int seconds of engaged time since the last
    heartbeat>}. Adds that to the student's ModuleProgress for this module
    (capped at the module's target duration) and returns the updated
    totals so the page can redraw its progress bar without a reload.
    """
    module = get_object_or_404(Module, pk=pk)
    student = Student.objects.filter(student=request.user).first()
    if not student or not TakenCourse.objects.filter(
        student=student, course=module.course
    ).exists():
        return HttpResponseForbidden("Not registered for this course.")

    # The periodic heartbeat sends JSON; the unload-time flush (sent via
    # navigator.sendBeacon, which can't set custom headers) sends a plain
    # form body instead so the CSRF middleware can validate it the normal
    # way — accept either.
    try:
        payload = json.loads(request.body or "{}")
        seconds = int(payload.get("seconds", 0))
    except (ValueError, TypeError):
        try:
            seconds = int(request.POST.get("seconds", 0))
        except (TypeError, ValueError):
            return HttpResponseBadRequest("Invalid payload.")
    if seconds < 0:
        return HttpResponseBadRequest("Invalid payload.")
    seconds = min(seconds, 300)  # ignore implausible single-heartbeat jumps

    progress, _created = ModuleProgress.objects.get_or_create(
        student=student, module=module
    )
    target = module.duration_seconds
    progress.seconds_covered = min(progress.seconds_covered + seconds, target) if target else progress.seconds_covered
    if target and progress.seconds_covered >= target and not progress.completed:
        progress.completed = True
        progress.completed_at = timezone.now()
    progress.save()

    return JsonResponse(
        {
            "seconds_covered": progress.seconds_covered,
            "percent": progress.percent_covered,
            "completed": progress.completed,
            "course_percent": module.course.progress_for_student(student),
        }
    )


@method_decorator([login_required, students_read_required], name="dispatch")
class CourseTrackerRosterView(ListView):
    """Facilitator/org admin/superuser view of every registered student's
    progress through a course's modules."""

    template_name = "course/course_tracker_roster.html"
    context_object_name = "rows"

    def get_course(self):
        return get_object_or_404(Course, slug=self.kwargs["slug"])

    def get_queryset(self):
        course = self.get_course()
        taken = TakenCourse.objects.filter(course=course).select_related(
            "student", "student__student"
        )
        rows = []
        for tc in taken:
            rows.append(
                {
                    "student": tc.student,
                    "percent": course.progress_for_student(tc.student),
                }
            )
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.get_course()
        context["title"] = f"Class progress — {course.title}"
        context["course"] = course
        context["modules"] = course.modules.all()
        return context


# ########################################################


# ########################################################
# Course Registration
# ########################################################
@login_required
@student_required
def course_registration(request):
    if request.method == "POST":
        if not SiteConfiguration.get_solo().course_registration_open:
            messages.error(
                request,
                "Course registration is currently closed. Contact your administrator.",
            )
            return redirect("course_registration")
        student = Student.objects.get(student__pk=request.user.id)
        ids = ()
        data = request.POST.copy()
        data.pop("csrfmiddlewaretoken", None)  # remove csrf_token
        for key in data.keys():
            ids = ids + (str(key),)
        for s in range(0, len(ids)):
            course = Course.objects.get(pk=ids[s])
            obj = TakenCourse.objects.create(student=student, course=course)
            obj.save()
        messages.success(request, "Courses registered successfully!")
        return redirect("course_registration")
    else:
        current_semester = Semester.objects.filter(is_current_semester=True).first()
        if not current_semester:
            messages.error(request, "No active semester found.")
            return render(request, "course/course_registration.html")

        # student = Student.objects.get(student__pk=request.user.id)
        student = get_object_or_404(Student, student__id=request.user.id)
        taken_courses = TakenCourse.objects.filter(student__student__id=request.user.id)
        t = ()
        for i in taken_courses:
            t += (i.course.pk,)

        courses = (
            Course.objects.filter(
                program__pk=student.program.id,
                level=student.level,
                semester=current_semester,
            )
            .exclude(id__in=t)
            .order_by("year")
        )
        all_courses = Course.objects.filter(
            level=student.level, program__pk=student.program.id
        )

        no_course_is_registered = False  # Check if no course is registered
        all_courses_are_registered = False

        registered_courses = Course.objects.filter(level=student.level).filter(id__in=t)
        if (
            registered_courses.count() == 0
        ):  # Check if number of registered courses is 0
            no_course_is_registered = True

        if registered_courses.count() == all_courses.count():
            all_courses_are_registered = True

        total_first_semester_credit = 0
        total_sec_semester_credit = 0
        total_registered_credit = 0
        for i in courses:
            if i.semester and i.semester.semester == "First":
                total_first_semester_credit += int(i.credit)
            if i.semester and i.semester.semester == "Second":
                total_sec_semester_credit += int(i.credit)
        for i in registered_courses:
            total_registered_credit += int(i.credit)
        context = {
            "is_calender_on": True,
            "all_courses_are_registered": all_courses_are_registered,
            "no_course_is_registered": no_course_is_registered,
            "current_semester": current_semester,
            "courses": courses,
            "total_first_semester_credit": total_first_semester_credit,
            "total_sec_semester_credit": total_sec_semester_credit,
            "registered_courses": registered_courses,
            "total_registered_credit": total_registered_credit,
            "student": student,
            "registration_open": SiteConfiguration.get_solo().course_registration_open,
        }
        return render(request, "course/course_registration.html", context)


@login_required
@student_required
def course_drop(request):
    if request.method == "POST":
        if not SiteConfiguration.get_solo().course_registration_open:
            messages.error(
                request,
                "Course registration is currently closed. Contact your administrator.",
            )
            return redirect("course_registration")
        student = Student.objects.get(student__pk=request.user.id)
        ids = ()
        data = request.POST.copy()
        data.pop("csrfmiddlewaretoken", None)  # remove csrf_token
        for key in data.keys():
            ids = ids + (str(key),)
        for s in range(0, len(ids)):
            course = Course.objects.get(pk=ids[s])
            obj = TakenCourse.objects.get(student=student, course=course)
            obj.delete()
        messages.success(request, "Successfully Dropped!")
        return redirect("course_registration")
    return redirect("course_registration")


# ########################################################


@login_required
def user_course_list(request):
    if request.user.is_lecturer:
        courses = Course.objects.filter(allocated_course__lecturer__pk=request.user.id)

        return render(request, "course/user_course_list.html", {"courses": courses})

    elif request.user.is_student:
        student = Student.objects.get(student__pk=request.user.id)
        taken_courses = TakenCourse.objects.filter(
            student__student__id=student.student.id
        )
        courses = Course.objects.filter(level=student.level).filter(
            program__pk=student.program.id
        )
        for taken in taken_courses:
            taken.progress = taken.course.progress_for_student(student)

        return render(
            request,
            "course/user_course_list.html",
            {"student": student, "taken_courses": taken_courses, "courses": courses},
        )

    else:
        return render(request, "course/user_course_list.html")
