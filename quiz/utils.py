import datetime
import ipaddress
import os
import random
import re
import socket
import string
from io import BytesIO
from urllib.parse import urlparse

import docx
import pypdf
import requests
from django.utils.text import slugify


def random_string_generator(size=10, chars=string.ascii_lowercase + string.digits):
    return "".join(random.choice(chars) for _ in range(size))


def unique_slug_generator(instance, new_slug=None):
    """
    This is for a Django project and it assumes your instance
    has a model with a slug field and a title character (char) field.
    """
    if new_slug is not None:
        slug = new_slug
    else:
        slug = slugify(instance.title)

    Klass = instance.__class__
    qs_exists = Klass.objects.filter(slug=slug).exists()
    if qs_exists:
        new_slug = "{slug}-{randstr}".format(
            slug=slug, randstr=random_string_generator(size=4)
        )
        return unique_slug_generator(instance, new_slug=new_slug)
    return slug


# ########################################################
# Quiz import from a document (.docx / .pdf) or a link to one
# ########################################################

QUESTION_RE = re.compile(r"^\s*(\d+)[.)]\s+(\S.*)$")
CHOICE_RE = re.compile(r"^\s*([A-Za-z])[.)]\s+(\S.*)$")
ANSWER_RE = re.compile(r"^\s*Answer\s*:\s*([A-Za-z])\s*$", re.IGNORECASE)
EXPLANATION_RE = re.compile(r"^\s*Explanation\s*:\s*(\S.*)$", re.IGNORECASE)

MAX_QUIZ_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB


class QuizDocumentError(Exception):
    """A document/link couldn't be turned into quiz text at all — as
    opposed to a per-question parsing problem, which is reported per-row
    instead of raised."""


def extract_text_from_docx(file_obj):
    document = docx.Document(file_obj)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def extract_text_from_pdf(file_obj):
    reader = pypdf.PdfReader(file_obj)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def extract_quiz_text(filename, content_bytes):
    """Dispatches to the right extractor based on the file's extension."""
    lower_name = (filename or "").lower()
    if lower_name.endswith(".docx"):
        return extract_text_from_docx(BytesIO(content_bytes))
    if lower_name.endswith(".pdf"):
        return extract_text_from_pdf(BytesIO(content_bytes))
    raise QuizDocumentError("Only .docx or .pdf files are supported.")


def parse_quiz_document(text):
    """
    Parses quiz questions out of plain text following this pattern:

        1. Question text goes here?
        A) First choice
        B) Second choice
        C) Third choice
        Answer: B
        Explanation: optional note shown after the question is answered.

        2. An essay question just omits the choices and the Answer line.
        Explanation: optional.

    Returns (questions, row_errors). `questions` is a list of dicts:
    {"number", "content", "type": "mc"|"essay", "choices": [(text, is_correct), ...], "explanation"}.
    `row_errors` is a list of {"question": <number or None>, "message": str}
    for a question block that couldn't be turned into a valid question —
    those are reported back, never guessed at.
    """
    blocks = []
    current = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = QUESTION_RE.match(line)
        if match:
            if current:
                blocks.append(current)
            current = {
                "number": int(match.group(1)),
                "content": match.group(2),
                "choice_lines": [],
                "answer_letter": None,
                "explanation": "",
            }
            continue

        if current is None:
            continue  # ignore any text before the first numbered question

        match = ANSWER_RE.match(line)
        if match:
            current["answer_letter"] = match.group(1).upper()
            continue

        match = EXPLANATION_RE.match(line)
        if match:
            current["explanation"] = match.group(1)
            continue

        match = CHOICE_RE.match(line)
        if match:
            current["choice_lines"].append((match.group(1).upper(), match.group(2)))
            continue

        # a wrapped continuation of the question text itself
        current["content"] += " " + line

    if current:
        blocks.append(current)

    questions = []
    row_errors = []

    for block in blocks:
        number = block["number"]

        if not block["choice_lines"]:
            questions.append(
                {
                    "number": number,
                    "content": block["content"],
                    "type": "essay",
                    "choices": [],
                    "explanation": block["explanation"],
                }
            )
            continue

        if len(block["choice_lines"]) < 2:
            row_errors.append(
                {
                    "question": number,
                    "message": "Needs at least two choices, or none at all for an essay question.",
                }
            )
            continue

        letters = [letter for letter, _ in block["choice_lines"]]
        if not block["answer_letter"]:
            row_errors.append(
                {"question": number, "message": 'Missing an "Answer: <letter>" line.'}
            )
            continue

        if block["answer_letter"] not in letters:
            row_errors.append(
                {
                    "question": number,
                    "message": f'Answer "{block["answer_letter"]}" doesn\'t match any of its choices ({", ".join(letters)}).',
                }
            )
            continue

        questions.append(
            {
                "number": number,
                "content": block["content"],
                "type": "mc",
                "choices": [
                    (choice_text, letter == block["answer_letter"])
                    for letter, choice_text in block["choice_lines"]
                ],
                "explanation": block["explanation"],
            }
        )

    if not questions and not row_errors:
        row_errors.append(
            {
                "question": None,
                "message": 'No numbered questions were found. Start each question with "1.", "2.", etc.',
            }
        )

    return questions, row_errors


def _is_publicly_routable_host(hostname):
    """Rejects loopback/private/link-local/reserved addresses — a basic
    SSRF guard for fetch_quiz_document below."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def fetch_quiz_document(url):
    """
    Downloads a quiz document from a direct link to a hosted .docx or .pdf
    file (e.g. a Google Docs/Drive "download" link, or any publicly
    reachable file URL) — NOT an arbitrary webpage. Guards against SSRF:
    only http(s), only a publicly routable host (checked before AND after
    following redirects), response capped at MAX_QUIZ_DOCUMENT_BYTES.

    Returns (filename, content_bytes). Raises QuizDocumentError on any
    failure, with a message safe to show the facilitator.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise QuizDocumentError("Only http:// or https:// links are supported.")
    if not parsed.hostname or not _is_publicly_routable_host(parsed.hostname):
        raise QuizDocumentError("That link can't be reached.")

    try:
        response = requests.get(
            url,
            timeout=10,
            stream=True,
            allow_redirects=True,
            headers={"User-Agent": "DimeLMS-QuizImport/1.0"},
        )
    except requests.RequestException:
        raise QuizDocumentError("Couldn't download that link.")

    with response:
        final_host = urlparse(response.url).hostname
        if not final_host or not _is_publicly_routable_host(final_host):
            raise QuizDocumentError("That link can't be reached.")

        if response.status_code != 200:
            raise QuizDocumentError(
                f"The link returned an error (HTTP {response.status_code})."
            )

        content = response.raw.read(MAX_QUIZ_DOCUMENT_BYTES + 1, decode_content=True)
        if len(content) > MAX_QUIZ_DOCUMENT_BYTES:
            raise QuizDocumentError("That file is too large (10 MB max).")

        content_type = response.headers.get("Content-Type", "").lower()
        filename = parsed.path.rsplit("/", 1)[-1] or "document"
        if "pdf" in content_type and not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        elif "wordprocessingml" in content_type and not filename.lower().endswith(".docx"):
            filename += ".docx"

    return filename, content
