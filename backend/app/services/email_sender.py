import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)

EMAIL_BODY_TEMPLATE = """Dear {company} Team,

Your complimentary Microsoft 365 Security Assessment is now complete.

Please find your confidential security report attached to this email.

IMPORTANT: This report contains sensitive security findings about your Microsoft 365 environment.
Please share it only with your IT leadership and security team.

Report highlights included:
- Full Microsoft Entra ID (Azure AD) audit
- Exchange Online security review
- SharePoint Online configuration assessment
- Microsoft Teams security posture
- Microsoft Purview compliance review
- M365 Admin Portal configuration review
- AI-generated remediation roadmap

If you have questions about any findings or need help with remediation,
please don't hesitate to reach out to our team.

Best regards,
{from_name}

---
This report was generated using Monkey365 and AI-powered analysis.
All findings reflect the configuration at the time of the assessment.
"""


def build_email_message(
    to_email: str,
    company: str,
    pdf_path: str,
    from_email: str,
    from_name: str,
) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = f"Your M365 Security Assessment Report — {company}"

    body = EMAIL_BODY_TEMPLATE.format(company=company, from_name=from_name)
    msg.attach(MIMEText(body, "plain"))

    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            attachment = MIMEApplication(f.read(), _subtype="pdf")
            attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=f"M365_Security_Assessment_{company.replace(' ', '_')}.pdf",
            )
            msg.attach(attachment)

    return msg


def send_report_email(to_email: str, company: str, pdf_path: str) -> None:
    """Send the PDF report to the client via SMTP."""
    msg = build_email_message(
        to_email=to_email,
        company=company,
        pdf_path=pdf_path,
        from_email=settings.EMAIL_FROM,
        from_name=settings.EMAIL_FROM_NAME,
    )

    logger.info(f"Sending report email to {to_email} for {company}")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)

    logger.info(f"Report email sent to {to_email}")

    # Clean up PDF after sending
    if os.path.exists(pdf_path):
        os.unlink(pdf_path)
        logger.info(f"Cleaned up PDF: {pdf_path}")
