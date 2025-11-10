import logging

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

from flask import Flask, render_template, request, redirect, url_for, flash
import os

app = Flask(__name__)

# Załaduj konfigurację
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # PRODUKCJA - Railway
    print("🚀 Tryb produkcji - Railway")

    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-secret-key')
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
    app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False') == 'True'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')
    app.config['MAIL_ADMIN'] = os.environ.get('MAIL_ADMIN')

    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }

    print(f"✅ PostgreSQL skonfigurowany")
else:
    # LOKALNIE
    print("💻 Tryb lokalny - config.py")

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

        print(f"✅ SQLite skonfigurowany")

    except ImportError as e:
        print("⚠️  BŁĄD: Brak pliku config.py i brak DATABASE_URL!")
        raise RuntimeError("Brak konfiguracji bazy danych!") from e

print("📦 Importuję SQLAlchemy...")
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy(app)
print("✅ SQLAlchemy zainicjalizowany")

print("📧 Importuję Flask-Mail...")
from flask_mail import Mail, Message

mail = Mail(app)
print("✅ Flask-Mail zainicjalizowany")

print("📝 Importuję formularze...")
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, SelectMultipleField
from wtforms.validators import DataRequired, Email, Length
from wtforms.widgets import CheckboxInput, ListWidget

print("✅ Formularze zaimportowane")

print("🌙 Importuję ephem...")
import ephem
from datetime import datetime

print("✅ Ephem zaimportowany")

print("🏗️  Definiuję modele...")


# Automatyczne zamykanie sesji
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()


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


class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    topics = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f'<ContactMessage {self.name} - {self.topics}>'


print("✅ Modele zdefiniowane")


# Formularze
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


print("✅ Formularze zdefiniowane")
print("🎯 Definiuję funkcje pomocnicze...")


# Funkcje pomocnicze
def get_moon_phase(date):
    """Oblicza fazę Księżyca"""
    moon = ephem.Moon(date)
    illumination = moon.moon_phase * 100

    if illumination < 1:
        phase_name, emoji = "Nów", "🌑"
    elif illumination < 25:
        phase_name, emoji = "Przybywający sierp", "🌒"
    elif illumination < 45:
        phase_name, emoji = "Pierwsza kwadra", "🌓"
    elif illumination < 55:
        phase_name, emoji = "Przybywający garb", "🌔"
    elif illumination < 99:
        phase_name, emoji = "Pełnia", "🌕"
    else:
        phase_name, emoji = "Pełnia", "🌕"

    next_day = ephem.Moon(ephem.Date(date) + 1)
    if next_day.moon_phase < moon.moon_phase:
        if 55 < illumination < 99:
            phase_name, emoji = "Malejący garb", "🌖"
        elif 45 < illumination <= 55:
            phase_name, emoji = "Ostatnia kwadra", "🌗"
        elif 25 < illumination <= 45:
            phase_name, emoji = "Ostatnia kwadra", "🌗"
        elif 1 <= illumination <= 25:
            phase_name, emoji = "Malejący sierp", "🌘"

    return {'emoji': emoji, 'name': phase_name, 'illumination': round(illumination, 1)}


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
    """Obcina tekst"""
    if len(text) <= length:
        return text
    return text[:length].rsplit(' ', 1)[0] + '...'


def send_contact_email(contact_message):
    """Wysyła email kontaktowy"""
    # Implementacja bez zmian - skopiuj z poprzedniej wersji
    pass


def send_registration_email(registration):
    """Wysyła email z potwierdzeniem zapisu"""
    # Implementacja bez zmian - skopiuj z poprzedniej wersji
    pass


print("✅ Funkcje pomocnicze zdefiniowane")
print("🌐 Rejestruję routes...")


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
    return Markup(text.replace('\n', '<br>'))


# ENDPOINT DO INICJALIZACJI BAZY
@app.route('/init-db-secret-endpoint-12345')
def init_database():
    """Inicjalizacja bazy - wywołaj raz"""
    try:
        db.create_all()
        return "✅ Baza danych zainicjalizowana!", 200
    except Exception as e:
        return f"❌ Błąd: {str(e)}", 500


# Routes - TYLKO PODSTAWOWE NA START
@app.route('/')
def index():
    return "✅ Aplikacja działa! Inicjalizuj bazę: /init-db-secret-endpoint-12345"


@app.route('/test')
def test():
    return "✅ Test endpoint działa!"


print("✅ Routes zarejestrowane")
print("🚀 Aplikacja gotowa do uruchomienia!")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)