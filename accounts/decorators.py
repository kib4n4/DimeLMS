from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect


def _role_decorator(test_func):
    """Build a decorator factory from a `user -> bool` predicate, matching
    this module's existing call shape: usable as `@my_decorator` (function
    passed directly by Python) or `@my_decorator(redirect_to="/somewhere/")`,
    and callable directly as a plain predicate when `function` is omitted."""

    def decorator(function=None, redirect_to="/"):
        def wrapper(request, *args, **kwargs):
            if test_func(request.user):
                return function(request, *args, **kwargs) if function else None
            return redirect(redirect_to)

        return wrapper if function else test_func

    return decorator


# ############################################################################
# Role checks. Every one of these requires the account to be active, then
# checks the role flag(s) — a superuser always passes, since Super Admin is
# granted every permission below.
# ############################################################################

admin_required = _role_decorator(
    lambda user: user.is_active and user.is_superuser
)
"""Superuser only. Reserved for site-wide settings a Super Admin alone owns."""

org_admin_required = _role_decorator(
    lambda user: user.is_active and (user.is_org_admin or user.is_superuser)
)
"""Org Admin or Super Admin. The write gate for facilitators, students,
programs & courses, sessions, semesters, course allocations and events."""

lecturer_required = _role_decorator(
    lambda user: user.is_active and (user.is_lecturer or user.is_superuser)
)
"""Facilitator or Super Admin. The read/write gate for quizzes, and for a
facilitator's own course materials and score entry — deliberately excludes
Org Admin, who has no quiz access per the permission matrix."""

student_required = _role_decorator(
    lambda user: user.is_active and (user.is_student or user.is_superuser)
)
"""Student or Super Admin."""

students_read_required = _role_decorator(
    lambda user: user.is_active
    and (user.is_superuser or user.is_org_admin or user.is_lecturer)
)
"""Read access to the student roster: Super Admin, Org Admin, or a
Facilitator viewing their students. Students themselves aren't on this list —
there's no "view other students" permission for a student account."""

courses_read_required = _role_decorator(
    lambda user: user.is_active
    and (
        user.is_superuser
        or user.is_org_admin
        or user.is_lecturer
        or user.is_student
    )
)
"""Read access to programs/courses, sessions/semesters, and exam results:
every signed-in role reads these — only add/edit/delete is restricted."""

sessions_read_required = courses_read_required
exams_read_required = courses_read_required

exams_write_required = students_read_required
"""Write access to exam results (score entry): Super Admin, Org Admin, or a
Facilitator entering scores for their own allocated courses — same role set
as students_read_required, named separately since it's a different resource."""

course_materials_write_required = students_read_required
"""Write access to a course's materials (files, videos, YouTube links): Super
Admin, Org Admin, or the Facilitator managing their own course's content —
deliberately excludes Students. Same role set as students_read_required and
exams_write_required, named separately for readability at the call site."""
