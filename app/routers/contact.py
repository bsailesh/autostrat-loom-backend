"""
Public contact form endpoint. Deliberately requires no auth — this is the
"Request a trial" / "Talk to sales" form on the marketing site, submitted by
people who aren't customers yet.

Every submission is stored in the database first, then an email is attempted.
If SMTP isn't configured or the send fails, the submission is not lost — it's
still in `contact_messages` and `email_sent` just reads false, so nothing
depends on the email succeeding.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.email_service import send_email
from app.models import ContactMessage
from app.schemas import ContactAck, ContactRequest

router = APIRouter(prefix="/contact", tags=["contact"])


@router.post("", response_model=ContactAck)
def submit_contact_form(payload: ContactRequest, db: Session = Depends(get_db)):
    settings = get_settings()

    body = (
        f"New AutoStrat Loom contact form submission\n\n"
        f"Name: {payload.full_name}\n"
        f"Email: {payload.work_email}\n"
        f"Company: {payload.company or '(not given)'}\n"
        f"Role: {payload.role or '(not given)'}\n"
        f"Interested in: {payload.interest}\n\n"
        f"Message:\n{payload.message}\n"
    )

    sent = send_email(
        to=settings.contact_email_to,
        subject=f"Loom contact form: {payload.full_name} ({payload.company or payload.work_email})",
        body=body,
    )

    record = ContactMessage(
        full_name=payload.full_name,
        work_email=payload.work_email,
        company=payload.company,
        role=payload.role,
        interest=payload.interest,
        message=payload.message,
        email_sent=sent,
    )
    db.add(record)
    db.commit()

    # Always a generic ack to the public caller, regardless of whether the
    # email send succeeded — email delivery status isn't this form's
    # business, and we don't want to reveal SMTP internals either way.
    return ContactAck()
