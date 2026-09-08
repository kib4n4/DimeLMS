from datetime import datetime
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.crypto import get_random_string
import threading
from openpyxl import Workbook, load_workbook
from core.utils import send_html_email

# Excludes visually-ambiguous characters (0/O, 1/I/l) — the same charset
# Django's own (now-removed) UserManager.make_random_password() used.
PASSWORD_CHARS = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_password():
    return get_random_string(10, allowed_chars=PASSWORD_CHARS)


def generate_student_id():
    # Generate a username based on first and last name and registration date
    registered_year = datetime.now().strftime("%Y")
    students_count = get_user_model().objects.filter(is_student=True).count()
    return f"{settings.STUDENT_ID_PREFIX}-{registered_year}-{students_count}"


def generate_lecturer_id():
    # Generate a username based on first and last name and registration date
    registered_year = datetime.now().strftime("%Y")
    lecturers_count = get_user_model().objects.filter(is_lecturer=True).count()
    return f"{settings.LECTURER_ID_PREFIX}-{registered_year}-{lecturers_count}"


def generate_org_admin_id():
    # Generate a username based on first and last name and registration date
    registered_year = datetime.now().strftime("%Y")
    org_admins_count = get_user_model().objects.filter(is_org_admin=True).count()
    return f"{settings.ORG_ADMIN_ID_PREFIX}-{registered_year}-{org_admins_count}"


def generate_student_credentials():
    return generate_student_id(), generate_password()


def generate_lecturer_credentials():
    return generate_lecturer_id(), generate_password()


def generate_org_admin_credentials():
    return generate_org_admin_id(), generate_password()


class EmailThread(threading.Thread):
    def __init__(self, subject, recipient_list, template_name, context):
        self.subject = subject
        self.recipient_list = recipient_list
        self.template_name = template_name
        self.context = context
        threading.Thread.__init__(self)

    def run(self):
        send_html_email(
            subject=self.subject,
            recipient_list=self.recipient_list,
            template=self.template_name,
            context=self.context,
        )


LECTURER_BULK_UPLOAD_COLUMNS = ["first name", "last name", "email", "phone", "address"]


def build_lecturer_bulk_upload_template():
    """An .xlsx workbook with the required header row and one example row,
    for admins to fill in and re-upload via the bulk upload page."""
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Facilitators"
    sheet.append(["First Name", "Last Name", "Email", "Phone", "Address"])
    sheet.append(["Jane", "Doe", "jane.doe@example.com", "+1 555 010 0100", "123 Main St"])
    for column_cells in sheet.columns:
        length = max(len(str(cell.value)) for cell in column_cells)
        sheet.column_dimensions[column_cells[0].column_letter].width = length + 4
    return wb


def parse_lecturer_bulk_upload(uploaded_file):
    """
    Parse an uploaded .xlsx file of facilitators (columns: First Name, Last
    Name, Email, Phone, Address — matching the required fields on the
    single "Add Facilitator" form).

    Returns (created_users, row_errors) — row_errors is a list of
    {"row": int, "message": str} dicts, one per row that couldn't be
    imported. Valid rows are created immediately; a facilitator User is
    created with is_lecturer=True and no username/password — the
    post_save signal on User generates both and emails the credentials,
    exactly as it does for the single "Add Facilitator" form.
    """
    from .models import User  # deferred to avoid a circular import

    try:
        wb = load_workbook(uploaded_file, read_only=True, data_only=True)
    except Exception:
        return [], [{"row": 1, "message": "Couldn't read that file — make sure it's a valid .xlsx workbook."}]

    sheet = wb.active
    rows = sheet.iter_rows(values_only=True)

    try:
        header_row = next(rows)
    except StopIteration:
        return [], [{"row": 1, "message": "The file is empty."}]

    headers = [str(cell).strip().lower() if cell is not None else "" for cell in header_row]
    column_index = {name: headers.index(name) for name in LECTURER_BULK_UPLOAD_COLUMNS if name in headers}

    missing_columns = [name.title() for name in LECTURER_BULK_UPLOAD_COLUMNS if name not in column_index]
    if missing_columns:
        return [], [{
            "row": 1,
            "message": f"Missing required column(s): {', '.join(missing_columns)}.",
        }]

    def cell_value(row, field):
        index = column_index[field]
        value = row[index] if index < len(row) else None
        return str(value).strip() if value is not None else ""

    created_users = []
    row_errors = []

    for row_number, row in enumerate(rows, start=2):
        if row is None or all(cell in (None, "") for cell in row):
            continue  # skip fully blank rows

        first_name = cell_value(row, "first name")
        last_name = cell_value(row, "last name")
        email = cell_value(row, "email")
        phone = cell_value(row, "phone")
        address = cell_value(row, "address")

        missing_fields = [
            label
            for label, value in [
                ("First Name", first_name),
                ("Last Name", last_name),
                ("Email", email),
                ("Phone", phone),
                ("Address", address),
            ]
            if not value
        ]
        if missing_fields:
            row_errors.append({"row": row_number, "message": f"Missing {', '.join(missing_fields)}."})
            continue

        try:
            validate_email(email)
        except ValidationError:
            row_errors.append({"row": row_number, "message": f'"{email}" is not a valid email address.'})
            continue

        if User.objects.filter(email__iexact=email).exists():
            row_errors.append({"row": row_number, "message": f'An account with email "{email}" already exists.'})
            continue

        user = User.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            address=address,
            is_lecturer=True,
        )
        created_users.append(user)

    return created_users, row_errors


STUDENT_BULK_UPLOAD_COLUMNS = [
    "first name",
    "last name",
    "email",
    "phone",
    "address",
    "gender",
    "level",
    "program",
]

# Accepts either the stored value or the friendlier display label from the
# single "Add Student" form's dropdowns, case-insensitively.
_GENDER_INPUT_MAP = {"m": "M", "male": "M", "f": "F", "female": "F"}
_LEVEL_INPUT_MAP = {
    "bachelor": "Bachelor",
    "bachelor degree": "Bachelor",
    "master": "Master",
    "master degree": "Master",
}


def build_student_bulk_upload_template():
    """An .xlsx workbook with the required header row and one example row,
    for admins to fill in and re-upload via the bulk upload page."""
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Students"
    sheet.append(
        ["First Name", "Last Name", "Email", "Phone", "Address", "Gender", "Level", "Program"]
    )
    sheet.append(
        ["Jane", "Doe", "jane.doe@example.com", "+1 555 010 0100", "123 Main St", "Female", "Bachelor", "B.Sc Computer Science"]
    )
    for column_cells in sheet.columns:
        length = max(len(str(cell.value)) for cell in column_cells)
        sheet.column_dimensions[column_cells[0].column_letter].width = length + 4
    return wb


def parse_student_bulk_upload(uploaded_file):
    """
    Parse an uploaded .xlsx file of students (columns: First Name, Last
    Name, Email, Phone, Address, Gender, Level, Program — matching the
    required fields on the single "Add Student" form).

    Returns (created_users, row_errors) — row_errors is a list of
    {"row": int, "message": str} dicts, one per row that couldn't be
    imported. Valid rows are created immediately: a User with
    is_student=True (no username/password — the post_save signal
    generates and emails both, same as the single "Add Student" form),
    plus the linked Student profile (level + program) the User model
    alone doesn't carry.
    """
    from .models import User, Student  # deferred to avoid a circular import
    from course.models import Program

    try:
        wb = load_workbook(uploaded_file, read_only=True, data_only=True)
    except Exception:
        return [], [{"row": 1, "message": "Couldn't read that file — make sure it's a valid .xlsx workbook."}]

    sheet = wb.active
    rows = sheet.iter_rows(values_only=True)

    try:
        header_row = next(rows)
    except StopIteration:
        return [], [{"row": 1, "message": "The file is empty."}]

    headers = [str(cell).strip().lower() if cell is not None else "" for cell in header_row]
    column_index = {name: headers.index(name) for name in STUDENT_BULK_UPLOAD_COLUMNS if name in headers}

    missing_columns = [name.title() for name in STUDENT_BULK_UPLOAD_COLUMNS if name not in column_index]
    if missing_columns:
        return [], [{
            "row": 1,
            "message": f"Missing required column(s): {', '.join(missing_columns)}.",
        }]

    def cell_value(row, field):
        index = column_index[field]
        value = row[index] if index < len(row) else None
        return str(value).strip() if value is not None else ""

    created_users = []
    row_errors = []

    for row_number, row in enumerate(rows, start=2):
        if row is None or all(cell in (None, "") for cell in row):
            continue  # skip fully blank rows

        first_name = cell_value(row, "first name")
        last_name = cell_value(row, "last name")
        email = cell_value(row, "email")
        phone = cell_value(row, "phone")
        address = cell_value(row, "address")
        gender_input = cell_value(row, "gender")
        level_input = cell_value(row, "level")
        program_input = cell_value(row, "program")

        missing_fields = [
            label
            for label, value in [
                ("First Name", first_name),
                ("Last Name", last_name),
                ("Email", email),
                ("Phone", phone),
                ("Address", address),
                ("Gender", gender_input),
                ("Level", level_input),
                ("Program", program_input),
            ]
            if not value
        ]
        if missing_fields:
            row_errors.append({"row": row_number, "message": f"Missing {', '.join(missing_fields)}."})
            continue

        try:
            validate_email(email)
        except ValidationError:
            row_errors.append({"row": row_number, "message": f'"{email}" is not a valid email address.'})
            continue

        if User.objects.filter(email__iexact=email).exists():
            row_errors.append({"row": row_number, "message": f'An account with email "{email}" already exists.'})
            continue

        gender = _GENDER_INPUT_MAP.get(gender_input.lower())
        if not gender:
            row_errors.append({
                "row": row_number,
                "message": f'"{gender_input}" is not a valid gender — use Male or Female.',
            })
            continue

        level = _LEVEL_INPUT_MAP.get(level_input.lower())
        if not level:
            row_errors.append({
                "row": row_number,
                "message": f'"{level_input}" is not a valid level — use Bachelor or Master.',
            })
            continue

        program = Program.objects.filter(title__iexact=program_input).first()
        if not program:
            row_errors.append({
                "row": row_number,
                "message": f'No program named "{program_input}" exists.',
            })
            continue

        user = User.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            address=address,
            gender=gender,
            is_student=True,
        )
        Student.objects.create(student=user, level=level, program=program)
        created_users.append(user)

    return created_users, row_errors


def send_new_account_email(user, password):
    if user.is_student:
        template_name = "accounts/email/new_student_account_confirmation.html"
    elif user.is_org_admin:
        template_name = "accounts/email/new_org_admin_account_confirmation.html"
    else:
        template_name = "accounts/email/new_lecturer_account_confirmation.html"
    email = {
        "subject": "Your DIME LMS account confirmation and credentials",
        "recipient_list": [user.email],
        "template_name": template_name,
        "context": {"user": user, "password": password},
    }
    EmailThread(**email).start()
