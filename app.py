import logging

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from flask_mail import Mail, Message
from wtforms import StringField, TextAreaField, SubmitField, SelectMultipleField
from wtforms.validators import DataRequired, Email, Length
from wtforms.widgets import CheckboxInput, ListWidget
import ephem
from datetime import datetime
import os
import requests
import psycopg2
from flask_wtf.csrf import CSRFProtect
from markupsafe import Markup, escape

app = Flask(__name__)
csrf = CSRFProtect(app)

# Załaduj konfigurację
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # PRODUKCJA - Railway (ma DATABASE_URL)
    print("🚀 Tryb produkcji - Railway")

    # Railway czasem używa postgres://, a SQLAlchemy wymaga postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-secret-key-change-this')
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')  # Railway Variable!

    if not app.config['SECRET_KEY']:
        print("❌ BRAK SECRET_KEY – dodaj w Railway → Variables!")
    
    # Brevo API
    app.config['BREVO_API_KEY'] = os.environ.get('BREVO_API_KEY')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')
    app.config['MAIL_ADMIN'] = os.environ.get('MAIL_ADMIN')

    # PostgreSQL - opcje połączenia
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 5,
        'max_overflow': 10,
        'echo': False,
    }

    print(f"✅ PostgreSQL skonfigurowany")
    print(f"   Database: {database_url.split('@')[1] if '@' in database_url else 'hidden'}")
    print(f"✅ Brevo API Key: {'Ustawiony' if app.config['BREVO_API_KEY'] else '❌ BRAK!'}")
else:
    # LOKALNIE - config.py
    print("💻 Tryb lokalny - config.py")

    try:
        import config

        db_uri = config.SQLALCHEMY_DATABASE_URI
        if 'sqlite' in db_uri and '?' not in db_uri:
            db_uri += '?timeout=30'

        app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = config.SQLALCHEMY_TRACK_MODIFICATIONS
        app.config['SECRET_KEY'] = config.SECRET_KEY

        # SQLite - specjalne opcje
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'connect_args': {
                'check_same_thread': False,
                'timeout': 30
            },
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': 1,
            'max_overflow': 0
        }

        # Brevo API
        app.config['BREVO_API_KEY'] = config.BREVO_API_KEY
        app.config['MAIL_DEFAULT_SENDER'] = config.MAIL_DEFAULT_SENDER
        app.config['MAIL_ADMIN'] = config.MAIL_ADMIN

        print(f"✅ SQLite skonfigurowany: {db_uri}")

    except ImportError as e:
        print("⚠️  BŁĄD: Brak pliku config.py i brak DATABASE_URL!")
        print("   Lokalnie: Stwórz plik config.py")
        print("   Railway: Dodaj PostgreSQL database")
        raise RuntimeError("Brak konfiguracji bazy danych!") from e

db = SQLAlchemy(app)
mail = Mail(app)


# Automatyczne zamykanie sesji
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()


# Model bazy danych dla wydarzeń
class Event(db.Model):
    __tablename__ = 'event'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    duration = db.Column(db.String(50), nullable=False)
    spots_total = db.Column(db.Integer, default=10)
    spots_taken = db.Column(db.Integer, default=0)
    image = db.Column(db.String(200), nullable=True)
    registrations = db.relationship('Registration', backref='event', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Event {self.title}>'

    @property
    def spots_available(self):
        return self.spots_total - self.spots_taken

    @property
    def is_full(self):
        return self.spots_taken >= self.spots_total

    @property
    def is_past(self):
        return self.date <= datetime.now()


# Model dla zapisów uczestników
class Registration(db.Model):
    __tablename__ = 'registration'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    message = db.Column(db.Text, nullable=True)
    registered_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f'<Registration {self.name} -> {self.event.title}>'


# Formularz zapisu
class RegistrationForm(FlaskForm):
    name = StringField('Imię i nazwisko', validators=[
        DataRequired(message='Pole wymagane'),
        Length(min=2, max=100, message='Imię musi mieć od 2 do 100 znaków')
    ])
    email = StringField('Email', validators=[
        DataRequired(message='Pole wymagane'),
        Email(message='Nieprawidłowy adres email')
    ])
    phone = StringField('Telefon (opcjonalnie)', validators=[
        Length(max=20, message='Numer telefonu jest za długi')
    ])
    message = TextAreaField('Wiadomość (opcjonalnie)', validators=[
        Length(max=500, message='Wiadomość może mieć maksymalnie 500 znaków')
    ])
    submit = SubmitField('Zapisz się')


class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    topics = db.Column(db.String(255), nullable=True)
    message = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)


    def __repr__(self):
        return f'<ContactMessage {self.name} - {self.topics}>'


# Widget dla checkboxów
class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


class ContactForm(FlaskForm):
    name = StringField('Imię i nazwisko', validators=[
        DataRequired(message='Pole wymagane'),
        Length(min=2, max=100, message='Imię musi mieć od 2 do 100 znaków')
    ])
    email = StringField('Email', validators=[
        DataRequired(message='Pole wymagane'),
        Email(message='Nieprawidłowy adres email')
    ])
    phone = StringField('Telefon (opcjonalnie)', validators=[
        Length(max=20, message='Numer telefonu jest za długi')
    ])
    topics = MultiCheckboxField('Interesuję się', choices=[
        ('olejki', 'Olejki eteryczne'),
        ('woda', 'Woda wodorowa'),
        ('joga', 'Joga'),
        ('zielone', 'Zielona żywność'),
        ('kregi', 'Kręgi męskie'),
        ('inne', 'Inne')
    ])
    message = TextAreaField('Wiadomość', validators=[
        DataRequired(message='Pole wymagane'),
        Length(min=10, max=1000, message='Wiadomość musi mieć od 10 do 1000 znaków')
    ])
    submit = SubmitField('Wyślij wiadomość')


def get_moon_phase(date):
    """Oblicza fazę Księżyca dla danej daty"""
    moon = ephem.Moon(date)
    illumination = moon.moon_phase * 100

    if illumination < 1:
        phase_name = "Nów"
        emoji = "🌑"
    elif illumination < 25:
        phase_name = "Przybywający sierp"
        emoji = "🌒"
    elif illumination < 45:
        phase_name = "Pierwsza kwadra"
        emoji = "🌓"
    elif illumination < 55:
        phase_name = "Przybywający garb"
        emoji = "🌔"
    elif illumination < 99:
        phase_name = "Pełnia"
        emoji = "🌕"
    elif illumination >= 99:
        phase_name = "Pełnia"
        emoji = "🌕"

    next_day = ephem.Moon(ephem.Date(date) + 1)
    if next_day.moon_phase < moon.moon_phase:
        if 55 < illumination < 99:
            phase_name = "Malejący garb"
            emoji = "🌖"
        elif 45 < illumination <= 55:
            phase_name = "Ostatnia kwadra"
            emoji = "🌗"
        elif 25 < illumination <= 45:
            phase_name = "Ostatnia kwadra"
            emoji = "🌗"
        elif 1 <= illumination <= 25:
            phase_name = "Malejący sierp"
            emoji = "🌘"

    return {
        'emoji': emoji,
        'name': phase_name,
        'illumination': round(illumination, 1)
    }


def format_polish_date(date):
    """Formatuje datę po polsku"""
    polish_months = {
        1: 'stycznia', 2: 'lutego', 3: 'marca', 4: 'kwietnia',
        5: 'maja', 6: 'czerwca', 7: 'lipca', 8: 'sierpnia',
        9: 'września', 10: 'października', 11: 'listopada', 12: 'grudnia'
    }

    polish_days = {
        0: 'poniedziałek', 1: 'wtorek', 2: 'środa', 3: 'czwartek',
        4: 'piątek', 5: 'sobota', 6: 'niedziela'
    }

    day_name = polish_days[date.weekday()]
    month_name = polish_months[date.month]

    return f"{day_name}, {date.day} {month_name} {date.year}, godz. {date.strftime('%H:%M')}"


def truncate_text(text, length=100):
    """Obcina tekst do określonej długości"""
    if len(text) <= length:
        return text
    return text[:length].rsplit(' ', 1)[0] + '...'


def send_email_brevo(to_email, to_name, subject, html_content, text_content=None):
    """Wysyła email przez Brevo API"""
    url = "https://api.brevo.com/v3/smtp/email"
    
    headers = {
        "accept": "application/json",
        "api-key": app.config['BREVO_API_KEY'],
        "content-type": "application/json"
    }
    
    payload = {
        "sender": {
            "name": "Moc Pięciu Żywiołów",
            "email": app.config['MAIL_DEFAULT_SENDER']
        },
        "to": [
            {
                "email": to_email,
                "name": to_name
            }
        ],
        "subject": subject,
        "htmlContent": html_content
    }
    
    if text_content:
        payload["textContent"] = text_content
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        print(f"✅ Email wysłany do {to_email} (Message ID: {response.json().get('messageId')})")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Błąd wysyłania emaila do {to_email}: {e}")
        if hasattr(e.response, 'text'):
            print(f"   Odpowiedź API: {e.response.text}")
        return False


def send_registration_email(registration):
    """Wysyła email z potwierdzeniem zapisu na wydarzenie"""
    event = registration.event
    moon_phase = get_moon_phase(event.date)

    # Email do uczestnika
    html_body = f"""
    <!DOCTYPE html>
    <html lang="pl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Potwierdzenie zapisu</title>
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #4CAF50; text-align: center;">✅ Potwierdzenie zapisu</h1>

            <p>Witaj <strong>{registration.name}</strong>!</p>

            <p>Dziękujemy za zapis na wydarzenie!</p>

            <div style="background-color: #f5f5f5; padding: 20px; border-radius: 5px; margin: 20px 0;">
                <h2 style="color: #333; margin-top: 0;">🔥 {event.title}</h2>
                <p><strong>📅 Data:</strong> {format_polish_date(event.date)}</p>
                <p><strong>📍 Miejsce:</strong> {event.location}</p>
                <p><strong>⏱ Czas trwania:</strong> {event.duration}</p>
                <p><strong>🌙 Faza Księżyca:</strong> {moon_phase['emoji']} {moon_phase['name']}</p>
            </div>

            <div style="background-color: #e3f2fd; padding: 15px; border-left: 4px solid #2196F3; margin: 20px 0;">
                <h3 style="margin-top: 0;">Twoje dane:</h3>
                <p><strong>Imię i nazwisko:</strong> {registration.name}</p>
                <p><strong>Email:</strong> {registration.email}</p>
                {f"<p><strong>Telefon:</strong> {registration.phone}</p>" if registration.phone else ""}
            </div>

            <p style="text-align: center; margin-top: 30px;">
                W razie pytań skontaktuj się z nami.<br>
                Do zobaczenia!
            </p>

            <p style="text-align: center; color: #666; font-size: 12px; margin-top: 30px;">
                Zespół Moc Pięciu Żywiołów<br>
                <em>Email wysłany automatycznie</em>
            </p>
        </div>
    </body>
    </html>
    """

    text_body = f"""
Witaj {registration.name}!

Dziękujemy za zapis na wydarzenie!

WYDARZENIE:
{event.title}
Data: {format_polish_date(event.date)}
Miejsce: {event.location}
Czas trwania: {event.duration}
Faza Księżyca: {moon_phase['emoji']} {moon_phase['name']}

TWOJE DANE:
Imię i nazwisko: {registration.name}
Email: {registration.email}
{f"Telefon: {registration.phone}" if registration.phone else ""}

W razie pytań skontaktuj się z nami.
Do zobaczenia!

Zespół Moc Pięciu Żywiołów
    """

    send_email_brevo(
        to_email=registration.email,
        to_name=registration.name,
        subject=f'Potwierdzenie zapisu: {event.title}',
        html_content=html_body,
        text_content=text_body
    )

    # Email do admina
    admin_body = f"""Nowy uczestnik zapisał się na wydarzenie!

📅 WYDARZENIE:
━━━━━━━━━━━━━━━━━━━━━━
{event.title}
Data: {format_polish_date(event.date)}
Miejsce: {event.location}

👤 UCZESTNIK:
━━━━━━━━━━━━━━━━━━━━━━
Imię i nazwisko: {registration.name}
Email: {registration.email}
Telefon: {registration.phone or 'Nie podano'}
{f"Wiadomość: {registration.message}" if registration.message else ""}

📊 STAN ZAPISÓW:
━━━━━━━━━━━━━━━━━━━━━━
Zajęte miejsca: {event.spots_taken}/{event.spots_total}
Wolne miejsca: {event.spots_available}
{f"⚠️ UWAGA: Pozostało tylko {event.spots_available} miejsc!" if event.spots_available <= 3 else ""}
{"🔴 PEŁNE - to było ostatnie miejsce!" if event.is_full else ""}

---
Data zapisu: {registration.registered_at.strftime('%d.%m.%Y %H:%M')}
"""

    send_email_brevo(
        to_email=app.config['MAIL_ADMIN'],
        to_name="Admin",
        subject=f'Nowy zapis na wydarzenie: {event.title}',
        html_content=f"<pre>{admin_body}</pre>",
        text_content=admin_body
    )


def send_contact_email(contact_message_id):
    """Wysyła email z potwierdzeniem kontaktu"""
    contact_msg = ContactMessage.query.get(contact_message_id)
    if not contact_msg:
        print("❌ Nie znaleziono wiadomości")
        return

    topics_dict = {
        'olejki': 'Olejki eteryczne',
        'woda': 'Woda wodorowa',
        'joga': 'Joga',
        'zielone': 'Zielona żywność',
        'kregi': 'Kręgi męskie',
        'inne': 'Inne'
    }

    topics_list = contact_msg.topics.split(', ') if contact_msg.topics else []
    topics_formatted = ', '.join([topics_dict.get(t, t) for t in topics_list])

    # Mail do klienta
    client_html = f"""
    <!DOCTYPE html>
    <html lang="pl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #4CAF50;">Potwierdzenie otrzymania wiadomości</h1>
            <p>Witaj <strong>{contact_msg.name}</strong>,</p>
            <p>Dziękujemy za kontakt! Twoja wiadomość została otrzymana.</p>
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Wybrane tematy:</strong> {topics_formatted or 'Nie wybrano'}</p>
                <p><strong>Twoja wiadomość:</strong></p>
                <p style="white-space: pre-wrap;">{contact_msg.message}</p>
            </div>
            <p>Odpowiemy najszybciej jak to możliwe.</p>
            <p style="color: #666; font-size: 12px; margin-top: 30px;">
                Pozdrawiamy,<br>Zespół Kręgi Męskie
            </p>
        </div>
    </body>
    </html>
    """

    client_text = f"""Witaj {contact_msg.name},

Dziękujemy za kontakt!

Tematy: {topics_formatted or 'Nie wybrano'}

Twoja wiadomość:
{contact_msg.message}

Pozdrawiamy,
Zespół Moc Pięciu Żywiołów"""

    send_email_brevo(
        to_email=contact_msg.email,
        to_name=contact_msg.name,
        subject='Potwierdzenie otrzymania wiadomości',
        html_content=client_html,
        text_content=client_text
    )

    # Mail do admina
    admin_text = f"""Nowa wiadomość kontaktowa!

Od: {contact_msg.name}
Email: {contact_msg.email}
Telefon: {contact_msg.phone or 'Nie podano'}
Tematy: {topics_formatted or 'Nie wybrano'}

Wiadomość:
{contact_msg.message}

Data wysłania: {contact_msg.sent_at}"""

    send_email_brevo(
        to_email=app.config['MAIL_ADMIN'],
        to_name="Admin",
        subject=f"Nowa wiadomość od {contact_msg.name}",
        html_content=f"<pre>{admin_text}</pre>",
        text_content=admin_text
    )


# Filtry Jinja2
@app.template_filter('polish_date')
def polish_date_filter(date):
    return format_polish_date(date)


@app.template_filter('truncate')
def truncate_filter(text, length=100):
    return truncate_text(text, length)


@app.template_filter('nl2br')
def nl2br_filter(text):
    from markupsafe import Markup
    return Markup(text.replace('\n', '<br>'))


@app.template_filter('safe_html')
def safe_html_filter(text):
    from markupsafe import Markup
    text = text.replace('\n', '<br>')
    return Markup(text)


# Routes
@app.route('/')
def index():

    db.session.close()

    upcoming_events = Event.query.filter(Event.date > datetime.now()).order_by(Event.date).all()
    next_event = upcoming_events[0] if upcoming_events else None

    if next_event:
        moon_phase = get_moon_phase(next_event.date)
        event_date_str = next_event.date.strftime('%Y-%m-%dT%H:%M:%S')
    else:
        moon_phase = None
        event_date_str = None

    return render_template('index.html',
                           title='Kręgi Męskie',
                           event_date=event_date_str,
                           moon_phase=moon_phase,
                           next_event=next_event)


@app.route('/wydarzenia')
def wydarzenia():
    now = datetime.now()

    db.session.close()


    upcoming = Event.query.filter(Event.date > now).order_by(Event.date).all()
    past = Event.query.filter(Event.date <= now).order_by(Event.date.desc()).all()

    for event in upcoming + past:
        event.moon_phase = get_moon_phase(event.date)
        print(f"🔍 Event: {event.title} | spots_taken: {event.spots_taken} | spots_total: {event.spots_total}")

    return render_template('wydarzenia.html',
                           title='Wydarzenia',
                           upcoming_events=upcoming,
                           past_events=past)


@app.route('/wydarzenie/<int:event_id>', methods=['GET', 'POST'])
def event_detail(event_id):

    db.session.close()

    event = Event.query.get_or_404(event_id)

    event.moon_phase = get_moon_phase(event.date)
    form = RegistrationForm()

    # 👇 DODAJ TO — DIAGNOSTYKA FORMULARZA:
    if request.method == "POST":
        print("🔍 POST odebrany!")
        print("validate_on_submit:", form.validate_on_submit())
        print("errors:", form.errors)  # Bardzo ważne! pokaże co blokuje!!

    if form.validate_on_submit():
        registration = Registration(
            event_id=event.id,
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data,
            message=form.message.data
        )
        db.session.add(registration)
        event.spots_taken += 1
        db.session.commit()

        # Wysyłanie emaila
        try:
            send_registration_email(registration)
            print("✅ Email wysłany pomyślnie")
        except Exception as e:
            print(f"⚠️ Błąd wysyłania emaila: {e}")

        flash("Zapisano pomyślnie! Sprawdź email.", "success")
        return redirect(url_for('event_detail', event_id=event.id))

    return render_template('event_detail.html', event=event, form=form)

@app.route('/wydarzenie/<int:event_id>/zapis', methods=['POST'])
def register_for_event(event_id):
    """Obsługa zapisu na wydarzenie"""
    form = RegistrationForm()

    if form.validate_on_submit():
        max_retries = 5
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                event = Event.query.get_or_404(event_id)

                if event.is_full:
                    flash('Przepraszamy, brak wolnych miejsc na to wydarzenie.', 'error')
                    return redirect(url_for('event_detail', event_id=event_id))

                existing = Registration.query.filter_by(
                    event_id=event_id,
                    email=form.email.data
                ).first()

                if existing:
                    flash('Jesteś już zapisany/a na to wydarzenie!', 'warning')
                    return redirect(url_for('event_detail', event_id=event_id))

                registration = Registration(
                    event_id=event_id,
                    name=form.name.data,
                    email=form.email.data,
                    phone=form.phone.data,
                    message=form.message.data
                )

                event.spots_taken += 1

                db.session.add(registration)
                db.session.flush()
                db.session.commit()

                print(f"✅ Zapis do bazy udany (próba {attempt + 1})")

                try:
                    send_registration_email(registration)
                    print("✅ Email wysłany pomyślnie")
                except Exception as e:
                    print(f"⚠️ Błąd wysyłania emaila: {e}")

                flash(f'Dziękujemy! Zapisałeś/aś się na wydarzenie: {event.title}', 'success')
                return redirect(url_for('registration_success', registration_id=registration.id))

            except Exception as e:
                db.session.rollback()
                print(f"⚠️ Próba {attempt + 1}/{max_retries} nie powiodła się: {e}")

                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    flash('Wystąpił błąd podczas zapisu. Spróbuj ponownie za chwilę.', 'error')
                    return redirect(url_for('event_detail', event_id=event_id))

    for field, errors in form.errors.items():
        for error in errors:
            flash(f'{getattr(form, field).label.text}: {error}', 'error')

    return redirect(url_for('event_detail', event_id=event_id))


@app.route('/zapis-potwierdzony/<int:registration_id>')
def registration_success(registration_id):
    registration = Registration.query.get_or_404(registration_id)
    return render_template('registration_success.html',
                           title='Potwierdzenie zapisu',
                           registration=registration)


@app.route('/olejki')
def olejki():
    return render_template('olejki.html', title='Olejki Eteryczne')


@app.route('/woda')
def woda():
    return render_template('woda.html', title='Woda Wodorowa')


@app.route('/joga')
def joga():
    return render_template('joga.html', title='Joga')


@app.route('/zielone')
def zielone():
    return render_template('zielone.html', title='Zielona Żywność')


from flask import request, flash, redirect, url_for, render_template
from datetime import datetime

@app.route('/kontakt', methods=['GET', 'POST'])
def kontakt():
    form = ContactForm()

    if form.validate_on_submit():
        msg = ContactMessage(
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data,
            topics=", ".join(form.topics.data),
            message=form.message.data
        )
        db.session.add(msg)
        db.session.commit()

        # Wysyłanie emaila synchronicznie
        try:
            send_contact_email(msg.id)
            flash("Wiadomość wysłana! Sprawdź email.", "success")
        except Exception as e:
            print(f"❌ Błąd wysyłania emaila: {e}")
            flash("Wiadomość zapisana, ale wystąpił problem z wysłaniem emaila.", "warning")
        
        return redirect(url_for('kontakt'))

    return render_template('kontakt.html', form=form)


@app.route('/wiadomosc-wyslana/<int:message_id>')
def contact_success(message_id):
    message = ContactMessage.query.get_or_404(message_id)
    return render_template('contact_success.html',
                           title='Wiadomość wysłana',
                           message=message)


# 🔍 DIAGNOSTYKA - sprawdź co jest w bazie
@app.route('/admin/debug-events')
def debug_events():
    db.session.close()  # Zamknij starą sesję
    events = Event.query.all()

    output = "<h1>🔍 Diagnostyka - Stan bazy danych</h1>"
    output += "<style>body{font-family:Arial;padding:20px;}table{border-collapse:collapse;width:100%;margin:20px 0;}th,td{border:1px solid #ddd;padding:12px;text-align:left;}th{background-color:#4CAF50;color:white;}tr:nth-child(even){background-color:#f2f2f2;}</style>"
    output += f"<p><strong>⏰ Czas sprawdzenia:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
    output += f"<p><strong>🔗 Połączenie z:</strong> {app.config['SQLALCHEMY_DATABASE_URI'].split('@')[1] if '@' in app.config['SQLALCHEMY_DATABASE_URI'] else 'SQLite'}</p>"

    output += "<table><tr><th>ID</th><th>Tytuł</th><th>spots_taken (BAZA)</th><th>spots_total</th><th>spots_available</th><th>is_full</th><th>Data</th></tr>"

    for event in events:
        color = "red" if event.is_full else "green"
        output += f"<tr><td>{event.id}</td><td>{event.title}</td><td style='background-color:{color};color:white;font-weight:bold;'>{event.spots_taken}</td><td>{event.spots_total}</td><td>{event.spots_available}</td><td>{'✅ TAK' if event.is_full else '❌ NIE'}</td><td>{event.date.strftime('%Y-%m-%d %H:%M')}</td></tr>"

    output += "</table>"

    # Pokaż też rejestracje
    output += "<h2>📋 Wszystkie rejestracje</h2>"
    registrations = Registration.query.all()
    output += f"<p><strong>Łącznie rejestracji:</strong> {len(registrations)}</p>"
    output += "<table><tr><th>ID</th><th>Wydarzenie</th><th>Imię</th><th>Email</th><th>Data zapisu</th></tr>"

    for reg in registrations:
        output += f"<tr><td>{reg.id}</td><td>{reg.event.title}</td><td>{reg.name}</td><td>{reg.email}</td><td>{reg.registered_at.strftime('%Y-%m-%d %H:%M')}</td></tr>"

    output += "</table>"

    return output


@app.template_filter('nl2br_simple')
def nl2br_simple(text):
    """Prosta zamiana \n na <br>"""
    print(f"🔧 FILTR - Długość tekstu: {len(text)}")
    print(f"🔧 FILTR - Pierwsze 100 znaków: {repr(text[:100])}")
    print(f"🔧 FILTR - Zawiera \\n? {chr(10) in text}")

    if not text:
        return ""

    # Zamień podwójne nowe linie na akapity
    text = text.replace('\n\n', '</p><p>')
    # Zamień pojedyncze nowe linie na <br>
    text = text.replace('\n', '<br>')
    # Owiń w akapit
    result = f'<p>{text}</p>'

    print(f"🔧 FILTR - Po konwersji (pierwsze 200): {repr(result[:200])}")
    return Markup(result)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)