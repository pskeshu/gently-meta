"""
Notification Service for gently-meta

Handles email notifications and alerts for experiment submissions,
approvals, rejections, and status updates.
"""

import json
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional


@dataclass
class NotificationConfig:
    """Notification service configuration."""
    enabled: bool = False
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: str = "experiments@gently-meta.org"
    base_url: str = "https://gently-meta.org"


class NotificationService:
    """
    Manages notifications for the gently-meta coordination system.
    Supports email notifications with optional extension points for
    other channels (Slack, Teams, webhooks, etc.).
    """

    def __init__(self, config_path: str = "notification_config.json"):
        self.config = self._load_config(config_path)
        self.reviewers: dict[str, list[str]] = {}
        self._load_reviewers()

    def _load_config(self, config_path: str) -> NotificationConfig:
        """Load notification configuration."""
        path = Path(config_path)

        # Override with environment variables
        config = NotificationConfig(
            enabled=os.getenv("NOTIFICATIONS_ENABLED", "false").lower() == "true",
            smtp_server=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=os.getenv("SMTP_USER"),
            smtp_password=os.getenv("SMTP_PASSWORD"),
            from_email=os.getenv("FROM_EMAIL", "experiments@gently-meta.org"),
            base_url=os.getenv("BASE_URL", "https://gently-meta.org"),
        )

        # Load file config if exists
        if path.exists():
            with open(path, 'r') as f:
                file_config = json.load(f)
                if not os.getenv("NOTIFICATIONS_ENABLED"):
                    config.enabled = file_config.get("enabled", False)
                if not os.getenv("SMTP_SERVER"):
                    config.smtp_server = file_config.get("smtp_server", config.smtp_server)
                if not os.getenv("SMTP_PORT"):
                    config.smtp_port = file_config.get("smtp_port", config.smtp_port)
                if not os.getenv("FROM_EMAIL"):
                    config.from_email = file_config.get("from_email", config.from_email)
                if not os.getenv("BASE_URL"):
                    config.base_url = file_config.get("base_url", config.base_url)

                # Load reviewers mapping
                self.reviewers = file_config.get("reviewers", {})

        return config

    def _load_reviewers(self):
        """Set default reviewers if not loaded from config."""
        if not self.reviewers:
            self.reviewers = {
                "DiSPIM": ["dispim-reviewer@lab.org"],
                "confocal": ["confocal-reviewer@lab.org"],
                "widefield": ["widefield-reviewer@lab.org"],
                "light_sheet": ["lightsheet-reviewer@lab.org"],
                "default": ["imaging-team@lab.org"],
            }

    def _send_email(
        self,
        to_addresses: list[str],
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> bool:
        """
        Send an email notification.

        Returns:
            True if sent (or would be sent if disabled), False on error
        """
        if not self.config.enabled:
            print(f"[NOTIFICATION] (disabled) To: {', '.join(to_addresses)}")
            print(f"   Subject: {subject}")
            print(f"   Body: {body_text[:200]}...")
            return True

        if not all([self.config.smtp_server, self.config.smtp_user, self.config.smtp_password]):
            print("[ERROR] SMTP not fully configured")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.config.from_email
            msg["To"] = ", ".join(to_addresses)
            msg["Subject"] = subject

            msg.attach(MIMEText(body_text, "plain"))
            if body_html:
                msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.send_message(msg)

            print(f"[NOTIFICATION] Email sent to {', '.join(to_addresses)}")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to send email: {e}")
            return False

    def get_reviewers(self, microscope_system: str) -> list[str]:
        """Get reviewer email addresses for a microscope system."""
        return self.reviewers.get(
            microscope_system,
            self.reviewers.get("default", [])
        )

    def notify_new_submission(
        self,
        request_id: str,
        microscope_system: str,
        requester_name: str,
        requester_institution: str,
        priority: str,
        scientific_rationale: str,
    ):
        """Notify reviewers of a new experiment submission."""
        reviewer_emails = self.get_reviewers(microscope_system)

        if not reviewer_emails:
            print(f"[WARNING] No reviewers configured for {microscope_system}")
            return

        priority_color = {
            "urgent": "red",
            "high": "orange",
            "medium": "black",
            "low": "gray",
        }.get(priority, "black")

        subject = f"[gently-meta] New {priority.upper()} request for {microscope_system}"

        body_text = f"""
New Experiment Submission

Request ID: {request_id}
Microscope System: {microscope_system}
Requester: {requester_name} ({requester_institution})
Priority: {priority.upper()}
Submitted: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

Scientific Rationale:
{scientific_rationale[:500]}{'...' if len(scientific_rationale) > 500 else ''}

Review this request at:
{self.config.base_url}/review/{request_id}

---
gently-meta Coordination System
        """.strip()

        body_html = f"""
<html>
<body style="font-family: sans-serif;">
    <h2>New Experiment Submission</h2>
    <table style="border-collapse: collapse;">
        <tr><td style="padding: 4px 8px;"><strong>Request ID:</strong></td><td>{request_id}</td></tr>
        <tr><td style="padding: 4px 8px;"><strong>Microscope:</strong></td><td>{microscope_system}</td></tr>
        <tr><td style="padding: 4px 8px;"><strong>Requester:</strong></td><td>{requester_name} ({requester_institution})</td></tr>
        <tr><td style="padding: 4px 8px;"><strong>Priority:</strong></td><td style="color: {priority_color}; font-weight: bold;">{priority.upper()}</td></tr>
        <tr><td style="padding: 4px 8px;"><strong>Submitted:</strong></td><td>{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</td></tr>
    </table>
    <h3>Scientific Rationale</h3>
    <p style="background: #f5f5f5; padding: 10px; border-radius: 4px;">
        {scientific_rationale[:500]}{'...' if len(scientific_rationale) > 500 else ''}
    </p>
    <p><a href="{self.config.base_url}/review/{request_id}" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">Review Request</a></p>
    <hr>
    <small style="color: #666;">gently-meta Coordination System</small>
</body>
</html>
        """.strip()

        self._send_email(reviewer_emails, subject, body_text, body_html)

    def notify_approval(
        self,
        requester_email: str,
        request_id: str,
        reviewer_name: str,
        comments: Optional[str] = None,
        scheduled_date: Optional[str] = None,
    ):
        """Notify requester that their experiment has been approved."""
        subject = "[gently-meta] Your experiment has been approved"

        schedule_info = f"\nScheduled for: {scheduled_date}" if scheduled_date else "\nScheduling: To be determined"
        comments_info = f"\n\nReviewer comments:\n{comments}" if comments else ""

        body_text = f"""
Your experiment request has been approved!

Request ID: {request_id}
Reviewed by: {reviewer_name}
Status: APPROVED{schedule_info}{comments_info}

Track your experiment at:
{self.config.base_url}/experiments/{request_id}

You will receive notifications when your experiment begins and when results are ready.

---
gently-meta Coordination System
        """.strip()

        body_html = f"""
<html>
<body style="font-family: sans-serif;">
    <h2 style="color: green;">Experiment Approved</h2>
    <p>Your experiment request has been approved!</p>
    <table style="border-collapse: collapse;">
        <tr><td style="padding: 4px 8px;"><strong>Request ID:</strong></td><td>{request_id}</td></tr>
        <tr><td style="padding: 4px 8px;"><strong>Reviewed by:</strong></td><td>{reviewer_name}</td></tr>
        <tr><td style="padding: 4px 8px;"><strong>Status:</strong></td><td style="color: green; font-weight: bold;">APPROVED</td></tr>
        {f'<tr><td style="padding: 4px 8px;"><strong>Scheduled:</strong></td><td>{scheduled_date}</td></tr>' if scheduled_date else '<tr><td style="padding: 4px 8px;"><strong>Scheduling:</strong></td><td>To be determined</td></tr>'}
    </table>
    {f'<p><strong>Reviewer comments:</strong> {comments}</p>' if comments else ''}
    <p><a href="{self.config.base_url}/experiments/{request_id}" style="background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">Track Experiment</a></p>
    <hr>
    <small style="color: #666;">gently-meta Coordination System</small>
</body>
</html>
        """.strip()

        self._send_email([requester_email], subject, body_text, body_html)

    def notify_rejection(
        self,
        requester_email: str,
        request_id: str,
        reviewer_name: str,
        comments: str,
    ):
        """Notify requester that their experiment was not approved."""
        subject = "[gently-meta] Experiment request update"

        body_text = f"""
Your experiment request has been reviewed.

Request ID: {request_id}
Reviewed by: {reviewer_name}
Status: NOT APPROVED

Reviewer comments:
{comments}

You may revise and resubmit your request with additional information.
View your request at:
{self.config.base_url}/experiments/{request_id}

---
gently-meta Coordination System
        """.strip()

        body_html = f"""
<html>
<body style="font-family: sans-serif;">
    <h2>Experiment Request Update</h2>
    <table style="border-collapse: collapse;">
        <tr><td style="padding: 4px 8px;"><strong>Request ID:</strong></td><td>{request_id}</td></tr>
        <tr><td style="padding: 4px 8px;"><strong>Reviewed by:</strong></td><td>{reviewer_name}</td></tr>
        <tr><td style="padding: 4px 8px;"><strong>Status:</strong></td><td>NOT APPROVED</td></tr>
    </table>
    <h3>Reviewer Comments</h3>
    <blockquote style="background: #f5f5f5; padding: 10px; border-left: 4px solid #dc3545; margin: 10px 0;">
        {comments}
    </blockquote>
    <p>You may revise and resubmit your request with additional information.</p>
    <p><a href="{self.config.base_url}/experiments/{request_id}">View your request</a></p>
    <hr>
    <small style="color: #666;">gently-meta Coordination System</small>
</body>
</html>
        """.strip()

        self._send_email([requester_email], subject, body_text, body_html)

    def notify_status_change(
        self,
        requester_email: str,
        request_id: str,
        old_status: str,
        new_status: str,
        details: Optional[str] = None,
    ):
        """Notify requester of experiment status change."""
        subject = f"[gently-meta] Experiment status: {new_status}"

        details_info = f"\n\nDetails:\n{details}" if details else ""

        body_text = f"""
Your experiment status has been updated.

Request ID: {request_id}
Previous Status: {old_status}
New Status: {new_status}{details_info}

Track your experiment at:
{self.config.base_url}/experiments/{request_id}

---
gently-meta Coordination System
        """.strip()

        self._send_email([requester_email], subject, body_text)

    def notify_completion(
        self,
        requester_email: str,
        request_id: str,
        results_location: Optional[str] = None,
        quality_summary: Optional[str] = None,
    ):
        """Notify requester that their experiment is complete."""
        subject = "[gently-meta] Your experiment is complete!"

        results_info = f"\nResults available at: {results_location}" if results_location else ""
        quality_info = f"\n\nQuality summary:\n{quality_summary}" if quality_summary else ""

        body_text = f"""
Your experiment has been completed!

Request ID: {request_id}
Status: COMPLETED
Completion time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}{results_info}{quality_info}

Access your data at:
{self.config.base_url}/experiments/{request_id}

Thank you for using gently-meta!

---
gently-meta Coordination System
        """.strip()

        body_html = f"""
<html>
<body style="font-family: sans-serif;">
    <h2 style="color: green;">Experiment Complete!</h2>
    <table style="border-collapse: collapse;">
        <tr><td style="padding: 4px 8px;"><strong>Request ID:</strong></td><td>{request_id}</td></tr>
        <tr><td style="padding: 4px 8px;"><strong>Status:</strong></td><td style="color: green; font-weight: bold;">COMPLETED</td></tr>
        <tr><td style="padding: 4px 8px;"><strong>Completion time:</strong></td><td>{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</td></tr>
        {f'<tr><td style="padding: 4px 8px;"><strong>Results:</strong></td><td><a href="{results_location}">{results_location}</a></td></tr>' if results_location else ''}
    </table>
    {f'<h3>Quality Summary</h3><p style="background: #f5f5f5; padding: 10px; border-radius: 4px;">{quality_summary}</p>' if quality_summary else ''}
    <p><a href="{self.config.base_url}/experiments/{request_id}" style="background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">Access Your Data</a></p>
    <p>Thank you for using gently-meta!</p>
    <hr>
    <small style="color: #666;">gently-meta Coordination System</small>
</body>
</html>
        """.strip()

        self._send_email([requester_email], subject, body_text, body_html)


def main():
    """Test notification service."""
    print("=== gently-meta Notification Service ===\n")

    service = NotificationService()

    print(f"Notifications enabled: {service.config.enabled}")
    print(f"Configured reviewers: {list(service.reviewers.keys())}\n")

    print("Testing notifications (will log, not send)...\n")

    service.notify_new_submission(
        request_id="test-123",
        microscope_system="DiSPIM",
        requester_name="Dr. Test User",
        requester_institution="University of Testing",
        priority="high",
        scientific_rationale="Study cell division dynamics in HeLa cells using fast volumetric imaging to capture mitotic spindle formation.",
    )

    print()

    service.notify_approval(
        requester_email="testuser@university.edu",
        request_id="test-123",
        reviewer_name="Ryan",
        comments="Excellent use case for DiSPIM",
        scheduled_date="2025-11-20T09:00:00",
    )


if __name__ == "__main__":
    main()
