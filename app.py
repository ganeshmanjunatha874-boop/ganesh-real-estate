import os
from pathlib import Path
from decimal import Decimal, InvalidOperation
from functools import wraps

import razorpay
from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, jsonify, redirect,
    render_template, request, url_for
)
from flask_login import (
    LoginManager, UserMixin, current_user,
    login_required, login_user, logout_user
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv(Path(__file__).resolve().parent/".env")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "")
if len(app.config["SECRET_KEY"]) < 32:
    raise RuntimeError("Set a SECRET_KEY of at least 32 characters in .env")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///ganesh_real_estate.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"

FEE_PAISE = 5000
CURRENCY = "INR"
PROPERTY_TYPES = ("House", "Apartment", "Land", "Plot", "Commercial")


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)


class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    property_type = db.Column(db.String(40), nullable=False)
    location = db.Column(db.String(180), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Numeric(14, 2), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(24), default="awaiting_payment", nullable=False)
    payment_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    order_id = db.Column(db.String(100), unique=True, nullable=False)
    payment_id = db.Column(db.String(100), unique=True, nullable=True)
    amount_paise = db.Column(db.Integer, nullable=False, default=FEE_PAISE)
    status = db.Column(db.String(20), default="created", nullable=False)


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def gateway_client():
    key_id = os.getenv("RAZORPAY_KEY_ID", "").strip()
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
    if not key_id or not key_secret:
        return None
    return razorpay.Client(auth=(key_id, key_secret))


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def common_template_values():
    return {
        "current_language": request.cookies.get("language", "en"),
        "fee_rupees": FEE_PAISE // 100,
    }


@app.get("/language/<lang>")
def set_language(lang):
    if lang not in ("en", "kn"):
        abort(400)
    response = redirect(request.referrer or url_for("index"))
    response.set_cookie("language", lang, max_age=31536000, samesite="Lax")
    return response


@app.get("/")
def index():
    query = request.args.get("q", "").strip()[:180]
    kind = request.args.get("type", "").strip()
    properties = Property.query.filter_by(status="approved")
    if query:
        pattern = f"%{query}%"
        properties = properties.filter(
            db.or_(Property.title.ilike(pattern), Property.location.ilike(pattern))
        )
    if kind in PROPERTY_TYPES:
        properties = properties.filter_by(property_type=kind)
    return render_template(
        "index.html",
        properties=properties.order_by(Property.created_at.desc()).all(),
        property_types=PROPERTY_TYPES,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or len(name) > 120 or "@" not in email or len(email) > 255:
            flash("Enter a valid name and email.", "error")
        elif len(password) < 10:
            flash("Password must contain at least 10 characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
        else:
            user = User(
                name=name, email=email,
                password_hash=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("index"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin" if current_user.is_admin else "index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("admin" if user.is_admin else "index"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/submit", methods=["GET", "POST"])
@login_required
def submit_property():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        kind = request.form.get("property_type", "")
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        try:
            price = Decimal(request.form.get("price", "0"))
        except (InvalidOperation, TypeError):
            price = Decimal("0")

        if (not title or len(title) > 160 or not location or len(location) > 180
                or not description or len(description) > 5000):
            flash("Please complete all property details correctly.", "error")
        elif kind not in PROPERTY_TYPES:
            flash("Choose a valid property type.", "error")
        elif not price.is_finite() or price <= 0 or price > Decimal("999999999999"):
            flash("Enter a valid property price.", "error")
        else:
            prop = Property(
                title=title, property_type=kind, location=location,
                description=description, price=price, owner_id=current_user.id,
                status="pending_review" if current_user.is_admin else "awaiting_payment"
            )
            db.session.add(prop)
            db.session.commit()
            if current_user.is_admin:
                flash("Admin listing created without a fee.", "success")
                return redirect(url_for("admin"))
            return redirect(url_for("pay", property_id=prop.id))
    return render_template("submit_property.html", property_types=PROPERTY_TYPES)


@app.get("/property/<int:property_id>")
def property_detail(property_id):
    prop = db.get_or_404(Property, property_id)
    if prop.status != "approved":
        if not current_user.is_authenticated:
            abort(404)
        if not current_user.is_admin and prop.owner_id != current_user.id:
            abort(404)
    return render_template("property.html", prop=prop)


@app.get("/pay/<int:property_id>")
@login_required
def pay(property_id):
    prop = db.get_or_404(Property, property_id)
    if current_user.is_admin:
        flash("Admin listings do not require payment.", "info")
        return redirect(url_for("admin"))
    if prop.owner_id != current_user.id:
        abort(403)
    if prop.status not in ("awaiting_payment", "payment_pending"):
        flash("This listing is not awaiting payment.", "info")
        return redirect(url_for("property_detail", property_id=prop.id))

    client = gateway_client()
    if client is None:
        return render_template("pay.html", prop=prop, key_id=None, order=None)

    order = client.order.create({
        "amount": FEE_PAISE,
        "currency": CURRENCY,
        "receipt": f"property-{prop.id}-user-{current_user.id}",
        "notes": {"property_id": str(prop.id), "user_id": str(current_user.id)},
    })
    existing = Payment.query.filter_by(order_id=order["id"]).first()
    if not existing:
        db.session.add(Payment(
            property_id=prop.id, user_id=current_user.id,
            order_id=order["id"], amount_paise=FEE_PAISE,
        ))
    prop.status = "payment_pending"
    db.session.commit()
    return render_template(
        "pay.html", prop=prop, key_id=os.getenv("RAZORPAY_KEY_ID"), order=order
    )


@app.post("/payment/verify")
@login_required
def verify_payment():
    data = request.get_json(silent=True) or {}
    order_id = str(data.get("razorpay_order_id", ""))
    payment_id = str(data.get("razorpay_payment_id", ""))
    signature = str(data.get("razorpay_signature", ""))
    record = Payment.query.filter_by(
        order_id=order_id, user_id=current_user.id,
        amount_paise=FEE_PAISE, status="created"
    ).first()
    if not record or not payment_id or not signature:
        return jsonify(error="Invalid payment details."), 400

    client = gateway_client()
    if client is None:
        return jsonify(error="Payments are not configured."), 503
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })
        details = client.payment.fetch(payment_id)
    except Exception:
        app.logger.exception("Gateway payment verification failed")
        return jsonify(error="Payment verification failed."), 400

    if details.get("order_id") != order_id or details.get("amount") != FEE_PAISE:
        return jsonify(error="Payment amount or order does not match."), 400
    if details.get("currency") != CURRENCY or details.get("status") != "captured":
        return jsonify(error="Payment has not been captured."), 400
    if Payment.query.filter_by(payment_id=payment_id).first():
        return jsonify(error="This payment has already been used."), 409

    record.payment_id = payment_id
    record.status = "verified"
    prop = db.session.get(Property, record.property_id)
    if prop is None or prop.owner_id != current_user.id:
        db.session.rollback()
        return jsonify(error="Property not found."), 404
    prop.payment_id = payment_id
    prop.status = "pending_review"
    db.session.commit()
    return jsonify(message="Payment verified. Listing awaits admin approval.")


@app.get("/admin")
@admin_required
def admin():
    properties = Property.query.order_by(Property.created_at.desc()).all()
    payments = Payment.query.order_by(Payment.id.desc()).all()
    return render_template("admin.html", properties=properties, payments=payments)


@app.post("/admin/property/<int:property_id>/<action>")
@admin_required
def review_property(property_id, action):
    prop = db.get_or_404(Property, property_id)
    if action == "approve":
        if prop.status != "pending_review":
            abort(400, "Only listings awaiting review can be approved.")
        # Non-admin customer listings require a recorded, verified payment.
        owner = db.session.get(User, prop.owner_id)
        if owner is None:
            abort(400, "Listing owner not found.")
        if not owner.is_admin:
            verified = Payment.query.filter_by(
                property_id=prop.id, user_id=owner.id, status="verified"
            ).first()
            if not verified:
                abort(400, "A verified payment is required.")
        prop.status = "approved"
    elif action == "reject":
        if prop.status == "approved":
            abort(400, "An approved listing cannot be rejected here.")
        prop.status = "rejected"
    else:
        abort(400)
    db.session.commit()
    flash("Property status updated.", "success")
    return redirect(url_for("admin"))


@app.errorhandler(403)
def forbidden(_error):
    return render_template("message.html", message="Access denied."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("message.html", message="Page not found."), 404


@app.errorhandler(413)
def too_large(_error):
    return render_template("message.html", message="Request too large (8 MB limit)."), 413


def create_admin():
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not email or not password or "@" not in email:
        raise RuntimeError("Configure ADMIN_EMAIL and ADMIN_PASSWORD in .env")
    user = User.query.filter_by(email=email).first()
    if user is None:
        user = User(
            name="Ganesh Real Estate Admin", email=email,
            password_hash=generate_password_hash(password), is_admin=True
        )
        db.session.add(user)
    else:
        user.is_admin = True
    db.session.commit()


with app.app_context():
    db.create_all()
    create_admin()


if __name__ == "__main__":
    # Debug is deliberately off by default.
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
