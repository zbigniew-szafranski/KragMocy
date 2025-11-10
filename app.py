import logging

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_mail import Mail, Message
from wtforms import StringField, TextAreaField, SubmitField, SelectMultipleField
from wtforms.validators import DataRequired, Email, Length
from wtforms.widgets import CheckboxInput, ListWidget
import ephem
from datetime import datetime
import sqlite3
import os

app = Flask(__name__)

# Załaduj konfigurację z zmiennych środowiskowych LUB z pliku config.py (lokalnie)
if os.environ.get('RAILWAY_ENVIRONMENT'):
    # Produkcja na Railway - użyj zmiennych środowiskowych
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = os.environ.get('SQLALCHEMY_TRACK_MODIFICATIONS', 'False') == 'True'
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
    app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False') == 'True'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')
    app.config['MAIL_ADMIN'] = os.environ.get('MAIL_ADMIN')
    app.config['REVOLUT_ME_LINK'] = os.environ.get('REVOLUT_ME_LINK')
    app.config['REVOLUT_ACCOUNT_NAME'] = os.environ.get('REVOLUT_ACCOUNT_NAME')

    # Dla Railway - bez WAL mode i pool size
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {
            'check_same_thread': False,
            'timeout': 30
        }
    }
else:
    # Lokalnie - użyj config.py
    try:
        import config

        db_uri = config.SQLALCHEMY_DATABASE_URI
        if 'sqlite' in db_uri and '?' not in db_uri:
            db_uri += '?timeout=30'

        app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = config.SQLALCHEMY_TRACK_MODIFICATIONS
        app.config['SECRET_KEY'] = config.SECRET_KEY
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
        app.config['MAIL_SERVER'] = config.MAIL_SERVER
        app.config['MAIL_PORT'] = config.MAIL_PORT
        app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
        app.config['MAIL_USE_SSL'] = config.MAIL_USE_SSL
        app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
        app.config['MAIL_PASSWORD'] = config.MAIL_PASSWORD
        app.config['MAIL_DEFAULT_SENDER'] = config.MAIL_DEFAULT_SENDER
        app.config['MAIL_ADMIN'] = config.MAIL_ADMIN
        app.config['REVOLUT_ME_LINK'] = config.REVOLUT_ME_LINK
        app.config['REVOLUT_ACCOUNT_NAME'] = config.REVOLUT_ACCOUNT_NAME
    except ImportError:
        print("⚠️  UWAGA: Brak pliku config.py i brak zmiennych środowiskowych!")
        raise

db = SQLAlchemy(app)
mail = Mail(app)

# Automatyczne zamykanie sesji
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

# Inicjalizacja bazy przy starcie (tylko jeśli nie istnieje)
with app.app_context():
    try:
        db.create_all()
        print("✅ Baza danych zainicjalizowana")
    except Exception as e:
        print(f"⚠️ Błąd inicjalizacji bazy: {e}")

# Włącz WAL mode dla SQLite (lepsza współbieżność)
def init_sqlite_wal():
    """Włącza Write-Ahead Logging dla lepszej wydajności"""
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA busy_timeout=30000')
        conn.close()
        print("✅ SQLite WAL mode enabled")


# Inicjalizuj WAL mode od razu po utworzeniu db
with app.app_context():
    init_sqlite_wal()


# Model bazy danych dla wydarzeń
class Event(db.Model):
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


# Nowy model dla zapisów uczestników
class Registration(db.Model):
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
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    topics = db.Column(db.String(200), nullable=False)  # Przechowuje tematy jako string
    message = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.now)

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
    """
    Oblicza fazę Księżyca dla danej daty
    Zwraca: (emoji, nazwa_fazy, procent_oświetlenia)
    """
    moon = ephem.Moon(date)

    # Procent oświetlenia
    illumination = moon.moon_phase * 100

    # Określenie fazy na podstawie procentu oświetlenia
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

    # Sprawdzenie czy księżyc maleje
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


def send_contact_email(contact_message):
    """Wysyła email z potwierdzeniem do klienta i powiadomienie do admina"""

    topics_dict = {
        'olejki': 'Olejki eteryczne',
        'woda': 'Woda wodorowa',
        'joga': 'Joga',
        'zielone': 'Zielona żywność',
        'kregi': 'Kręgi męskie',
        'inne': 'Inne'
    }

    topics_list = contact_message.topics.split(', ') if contact_message.topics else []
    topics_formatted = ', '.join([topics_dict.get(t, t) for t in topics_list])

    # Email do klienta (potwierdzenie)
    try:
        msg_client = Message(
            subject='Potwierdzenie otrzymania wiadomości - Kręgi Męskie',
            recipients=[contact_message.email],
            body=f"""Witaj {contact_message.name},

Dziękujemy za kontakt!

Otrzymaliśmy Twoją wiadomość i odpowiemy najszybciej jak to możliwe.

Podsumowanie:
Tematy: {topics_formatted or 'Nie wybrano'}
Wiadomość: {contact_message.message}

Pozdrawiamy,
Zespół Krąg Mocy
"""
        )
        mail.send(msg_client)
        print(f"✅ Email potwierdzający wysłany do: {contact_message.email}")
    except Exception as e:
        print(f"❌ Błąd wysyłania emaila do klienta: {e}")
        import traceback
        traceback.print_exc()  # Pokaż pełny błąd

    # Email do admina (powiadomienie)
    try:
        msg_admin = Message(
            subject=f'Nowa wiadomość kontaktowa od {contact_message.name}',
            recipients=[app.config['MAIL_ADMIN']],
            body=f"""Otrzymałeś nową wiadomość kontaktową:

Od: {contact_message.name}
Email: {contact_message.email}
Telefon: {contact_message.phone or 'Nie podano'}
Tematy: {topics_formatted or 'Nie wybrano'}

Wiadomość:
{contact_message.message}

---
Data wysłania: {contact_message.sent_at.strftime('%d.%m.%Y %H:%M')}
"""
        )
        mail.send(msg_admin)
        print(f"✅ Powiadomienie wysłane do admina: {app.config['MAIL_ADMIN']}")
    except Exception as e:
        print(f"❌ Błąd wysyłania emaila do admina: {e}")
        import traceback
        traceback.print_exc()  # Pokaż pełny błąd


def send_registration_email(registration):
    """Wysyła email z potwierdzeniem zapisu na wydarzenie"""

    event = registration.event
    moon_phase = get_moon_phase(event.date)

    # Email do uczestnika (potwierdzenie)
    try:
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
                    <h2 style="color: #333; margin-top: 0;">📅 {event.title}</h2>
                    <p><strong>Data:</strong> {format_polish_date(event.date)}</p>
                    <p><strong>Miejsce:</strong> {event.location}</p>
                    <p><strong>Czas trwania:</strong> {event.duration}</p>
                    <p><strong>Faza Księżyca:</strong> {moon_phase['emoji']} {moon_phase['name']}</p>
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
                    Zespół Kręgi Męskie<br>
                    <em>Email wysłany automatycznie - nie odpowiadaj na tę wiadomość</em>
                </p>
            </div>
        </body>
        </html>
        """

        msg_participant = Message(
            subject=f'Potwierdzenie zapisu: {event.title}',
            recipients=[registration.email],
            html=html_body
        )
        mail.send(msg_participant)
        print(f"✅ Email potwierdzający wysłany do uczestnika: {registration.email}")
    except Exception as e:
        print(f"❌ Błąd wysyłania emaila do uczestnika: {e}")
        import traceback
        traceback.print_exc()

    # Email do admina pozostaje bez zmian (plain text)
    try:
        msg_admin = Message(
            subject=f'Nowy zapis na wydarzenie: {event.title}',
            recipients=[app.config['MAIL_ADMIN']],
            body=f"""Nowy uczestnik zapisał się na wydarzenie!

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
        )
        mail.send(msg_admin)
        print(f"✅ Powiadomienie o zapisie wysłane do admina")
    except Exception as e:
        print(f"❌ Błąd wysyłania emaila do admina: {e}")
        import traceback
        traceback.print_exc()

# Zarejestruj filtry Jinja2
@app.template_filter('polish_date')
def polish_date_filter(date):
    return format_polish_date(date)


@app.template_filter('truncate')
def truncate_filter(text, length=100):
    """Filtr do obcinania tekstu"""
    return truncate_text(text, length)


@app.template_filter('nl2br')
def nl2br_filter(text):
    """Zamienia znaki nowej linii na <br> (dla formatowania w HTML)"""
    from markupsafe import Markup
    return Markup(text.replace('\n', '<br>'))


@app.template_filter('safe_html')
def safe_html_filter(text):
    """Bezpiecznie renderuje HTML z podstawowym formatowaniem"""
    from markupsafe import Markup
    # Zamień nowe linie na <br>
    text = text.replace('\n', '<br>')
    # Możesz dodać więcej formatowania tutaj
    return Markup(text)

# Zarejestruj funkcję jako filtr Jinja2
@app.template_filter('polish_date')
def polish_date_filter(date):
    return format_polish_date(date)

@app.route('/')
def index():
    # Najbliższe wydarzenie z bazy danych
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
    # Pobierz wydarzenia z bazy danych
    now = datetime.now()
    upcoming = Event.query.filter(Event.date > now).order_by(Event.date).all()
    past = Event.query.filter(Event.date <= now).order_by(Event.date.desc()).all()

    # Dodaj fazę księżyca
    for event in upcoming + past:
        event.moon_phase = get_moon_phase(event.date)

    return render_template('wydarzenia.html',
                           title='Wydarzenia',
                           upcoming_events=upcoming,
                           past_events=past)


@app.route('/wydarzenie/<int:event_id>')
def event_detail(event_id):
    """Strona szczegółów wydarzenia z formularzem zapisu"""
    event = Event.query.get_or_404(event_id)
    event.moon_phase = get_moon_phase(event.date)
    form = RegistrationForm()

    return render_template('event_detail.html',
                           title=event.title,
                           event=event,
                           form=form)


@app.route('/wydarzenie/<int:event_id>/zapis', methods=['POST'])
def register_for_event(event_id):
    """Obsługa zapisu na wydarzenie"""
    event = Event.query.get_or_404(event_id)
    form = RegistrationForm()

    if form.validate_on_submit():
        # Sprawdź czy są jeszcze wolne miejsca
        if event.is_full:
            flash('Przepraszamy, brak wolnych miejsc na to wydarzenie.', 'error')
            return redirect(url_for('event_detail', event_id=event_id))

        # Sprawdź czy ta osoba już się nie zapisała
        existing = Registration.query.filter_by(
            event_id=event_id,
            email=form.email.data
        ).first()

        if existing:
            flash('Jesteś już zapisany/a na to wydarzenie!', 'warning')
            return redirect(url_for('event_detail', event_id=event_id))

        # Utwórz nowy zapis
        registration = Registration(
            event_id=event_id,
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data,
            message=form.message.data
        )

        # Zwiększ liczbę zajętych miejsc
        event.spots_taken += 1

        # Zapisz do bazy z retry logic
        max_retries = 5
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                db.session.add(registration)
                db.session.commit()
                print(f"✅ Zapis do bazy udany (próba {attempt + 1})")
                break
            except Exception as e:
                db.session.rollback()
                print(f"⚠️ Próba {attempt + 1}/{max_retries} nie powiodła się: {e}")

                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    # Ostatnia próba nie powiodła się
                    flash('Wystąpił błąd podczas zapisu. Spróbuj ponownie za chwilę.', 'error')
                    print(f"❌ Wszystkie próby zapisu nie powiodły się: {e}")
                    import traceback
                    traceback.print_exc()
                    return redirect(url_for('event_detail', event_id=event_id))

        # Wyślij emaile z potwierdzeniem (w osobnym try/except)
        try:
            send_registration_email(registration)
        except Exception as e:
            print(f"⚠️ Błąd wysyłania emaila (dane zapisane): {e}")
            # Nie przerywaj procesu - zapis już się odbył

        flash(f'Dziękujemy! Zapisałeś/aś się na wydarzenie: {event.title}', 'success')
        return redirect(url_for('registration_success', registration_id=registration.id))

    # Jeśli formularz nie jest poprawny, pokaż błędy
    for field, errors in form.errors.items():
        for error in errors:
            flash(f'{getattr(form, field).label.text}: {error}', 'error')

    return redirect(url_for('event_detail', event_id=event_id))


@app.route('/zapis-potwierdzony/<int:registration_id>')
def registration_success(registration_id):
    """Strona potwierdzenia zapisu"""
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


@app.route('/kontakt', methods=['GET', 'POST'])
def kontakt():
    form = ContactForm()

    if form.validate_on_submit():
        # Zapisz wiadomość do bazy
        topics_str = ', '.join(form.topics.data) if form.topics.data else ''

        contact_message = ContactMessage(
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data,
            topics=topics_str,
            message=form.message.data
        )

        # Zapisz z retry logic
        max_retries = 5
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                db.session.add(contact_message)
                db.session.commit()
                print(f"✅ Wiadomość zapisana (próba {attempt + 1})")
                break
            except Exception as e:
                db.session.rollback()
                print(f"⚠️ Próba {attempt + 1}/{max_retries}: {e}")

                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    flash('Wystąpił błąd podczas zapisywania wiadomości. Spróbuj ponownie.', 'error')
                    return render_template('kontakt.html', title='Kontakt', form=form)

        # Wyślij emaile
        try:
            send_contact_email(contact_message)
        except Exception as e:
            print(f"⚠️ Błąd wysyłania emaila (wiadomość zapisana): {e}")

        flash('Dziękujemy za wiadomość! Odpowiemy wkrótce.', 'success')
        return redirect(url_for('contact_success', message_id=contact_message.id))

    return render_template('kontakt.html', title='Kontakt', form=form)


@app.route('/wiadomosc-wyslana/<int:message_id>')
def contact_success(message_id):
    """Strona potwierdzenia wysłania wiadomości"""
    message = ContactMessage.query.get_or_404(message_id)
    return render_template('contact_success.html',
                           title='Wiadomość wysłana',
                           message=message)

if __name__ == '__main__':
    # app.run(host='192.168.0.112', port=5000, debug=True)
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)