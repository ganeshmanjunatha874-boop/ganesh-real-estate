# Ganesh Real Estate (Flask starter)

Features:
- Customer registration and login
- Property listing and search
- English/Kannada language switcher (some content is translated; extend translations before launch)
- ₹50 customer listing fee via Razorpay Checkout
- Admin dashboard; admin-created listings are fee-exempt
- Payment signature and captured-payment verification before review

## Setup on Windows / VS Code

1. Extract this ZIP into a new folder. Keep your existing project backed up.
2. Open the extracted folder in VS Code.
3. In Terminal, run:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```
   If PowerShell activation is blocked, use Command Prompt and run `.venv\Scripts\activate.bat`.
4. Copy `.env.example` to `.env`.
5. Set `SECRET_KEY` to a random secret at least 32 characters long. Set a private `ADMIN_EMAIL` and strong `ADMIN_PASSWORD`.
6. For payment testing, add Razorpay TEST key ID and TEST secret to `.env`. Do not use live keys until you've tested and reviewed the app.
7. Start the app:
   ```powershell
   python app.py
   ```
8. Visit http://127.0.0.1:5000

The database is created automatically. The configured admin account is created or promoted on startup. Use the email/password configured in `.env` to sign in.

## Important limitations before public launch

This is a starter project, not production-ready. It does not yet include property image uploads, email/phone verification, a customer enquiry workflow, payment webhooks, rate limiting, audit logging, database migrations, or an Android client/API. Payment handling should be reviewed and tested with the gateway before live use. Do not deploy with Flask debug mode enabled. Use HTTPS, production secrets, a production WSGI server, and a managed database for public deployment. Never commit `.env` or share gateway secrets.
