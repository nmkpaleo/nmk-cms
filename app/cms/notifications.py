from __future__ import annotations

import json
import logging
from typing import Iterable
from urllib import error as urlerror
from urllib import request as urlrequest

from django.conf import settings
from django.core.mail import send_mail
from django.urls import NoReverseMatch, reverse

logger = logging.getLogger(__name__)


def _status_label(media, status: str | None) -> str:
    if not status:
        return "Unknown"
    try:
        return media.QCStatus(status).label
    except ValueError:
        return str(status)


def _actor_label(user) -> str:
    if not user:
        return "System"
    full_name = getattr(user, "get_full_name", lambda: "")()
    if full_name:
        return full_name
    username = getattr(user, "get_username", None)
    if callable(username):
        return username()
    return str(user)


def _media_label(media) -> str:
    if getattr(media, "file_name", None):
        return media.file_name
    media_location = getattr(media, "media_location", None)
    if media_location:
        return str(media_location)
    return f"Media {media.pk}"


def _absolute_url(path: str) -> str:
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    base_url = getattr(settings, "QC_NOTIFICATION_BASE_URL", "") or getattr(
        settings, "SITE_URL", ""
    )
    base_url = base_url.rstrip("/")
    if base_url:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base_url}{path}"
    return path


def _resolve_qc_url(media, new_status: str) -> str:
    try:
        if new_status == media.QCStatus.PENDING_INTERN:
            return reverse("media_intern_qc", args=[media.uuid])
        if new_status in {
            media.QCStatus.PENDING_EXPERT,
            media.QCStatus.APPROVED,
            media.QCStatus.REJECTED,
        }:
            return reverse("media_expert_qc", args=[media.uuid])
    except NoReverseMatch:
        logger.debug("QC reverse lookup failed for media %s", media.pk, exc_info=True)
    return media.get_absolute_url()


def _send_slack_message(webhook_url: str, payload: dict[str, object]) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=5):
            return
    except urlerror.URLError:
        logger.exception("Unable to post Slack notification to %s", webhook_url)


def _send_email(subject: str, message: str, recipients: Iterable[str]) -> None:
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    try:
        send_mail(subject, message, from_email, list(recipients), fail_silently=False)
    except Exception:
        logger.exception("Unable to send QC notification email")


def notify_media_qc_transition(media, old_status: str, new_status: str, user=None, note: str | None = None) -> None:
    """Send Slack and/or email notifications for media QC transitions."""

    recipients = getattr(settings, "QC_NOTIFICATION_EMAILS", None) or []
    webhook_url = getattr(settings, "QC_SLACK_WEBHOOK_URL", "")
    if not recipients and not webhook_url:
        return

    media_name = _media_label(media)
    old_label = _status_label(media, old_status)
    new_label = _status_label(media, new_status)
    actor = _actor_label(user)
    qc_path = _resolve_qc_url(media, new_status)
    qc_url = _absolute_url(qc_path)
    media_url = _absolute_url(media.get_absolute_url())

    note_line = f"Note: {note}" if note else ""
    message_lines = [
        f"{media_name} moved from {old_label} to {new_label}.",
        f"Changed by {actor}.",
    ]
    if note_line:
        message_lines.append(note_line)
    if qc_url:
        message_lines.append(f"QC workflow: {qc_url}")
    if media_url:
        message_lines.append(f"Media record: {media_url}")

    body = "\n".join(message_lines)
    subject = f"[Media QC] {media_name} → {new_label}"

    if recipients:
        _send_email(subject, body, recipients)

    if webhook_url:
        slack_lines = [
            f"*{media_name}* moved from {old_label} to *{new_label}*.",
            f"Changed by {actor}.",
        ]
        if note:
            slack_lines.append(f"Note: {note}")
        if qc_url:
            slack_lines.append(f"<{qc_url}|Open QC>")
        if media_url:
            slack_lines.append(f"Media record: {media_url}")

        payload = {
            "text": "\n".join(slack_lines),
        }
        _send_slack_message(webhook_url, payload)
