import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

# Database helpers
from database import create_document
from schemas import ContactLead

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ContactMessage(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    message: str = Field(..., min_length=1, max_length=5000)


def send_email_smtp(subject: str, html_body: str, text_body: str) -> None:
    """Send email using SMTP with environment configuration.

    Required env vars:
    - EMAIL_HOST
    - EMAIL_PORT (e.g., 587)
    - EMAIL_USER
    - EMAIL_PASS
    - EMAIL_FROM (defaults to EMAIL_USER)
    - EMAIL_TO (recipient). If not set, falls back to EMAIL_USER
    """
    host = os.getenv("EMAIL_HOST")
    port = int(os.getenv("EMAIL_PORT", "587"))
    user = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    sender = os.getenv("EMAIL_FROM") or user
    recipient = os.getenv("EMAIL_TO") or os.getenv("PERSONAL_EMAIL") or "hemenbhasin@gmail.com"

    if not host or not user or not password:
        raise RuntimeError("Email service is not configured on the server (set EMAIL_HOST, EMAIL_USER, EMAIL_PASS).")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    part1 = MIMEText(text_body, "plain")
    part2 = MIMEText(html_body, "html")
    msg.attach(part1)
    msg.attach(part2)

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port) as server:
        server.starttls(context=context)
        server.login(user, password)
        server.sendmail(sender, [recipient], msg.as_string())


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.post("/api/contact")
def contact(msg: ContactMessage):
    subject = "New portfolio contact"
    html = f"""
    <h2>New message from portfolio</h2>
    <p><strong>Name:</strong> {msg.name}</p>
    <p><strong>Email:</strong> {msg.email}</p>
    <p><strong>Message:</strong><br/>{msg.message.replace('\n','<br/>')}</p>
    """
    text = f"New message from portfolio\nName: {msg.name}\nEmail: {msg.email}\n\n{msg.message}"

    delivered = False
    delivery_error: Optional[str] = None

    # Try email delivery if configured; never fail the endpoint for config issues
    try:
        send_email_smtp(subject, html, text)
        delivered = True
    except Exception as e:
        # Capture the error but don't expose sensitive details to client
        delivery_error = str(e)

    # Persist the lead regardless of email delivery outcome
    try:
        lead = ContactLead(
            name=msg.name,
            email=msg.email,
            message=msg.message,
            delivered=delivered,
            error=(delivery_error[:300] if delivery_error else None),
        )
        create_document("contactlead", lead)
    except Exception:
        # If DB write fails, still respond based on email delivery alone
        pass

    if delivered:
        return {"ok": True, "message": "Message sent successfully"}
    else:
        # Graceful fallback: acknowledge receipt even if email not configured
        return {
            "ok": True,
            "message": "Message received. We'll get back to you soon.",
            "note": "Email delivery not configured on server; message saved.",
        }


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        # Try to import database module
        from database import db
        
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            
            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
