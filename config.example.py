# config.example.py - SZABLON KONFIGURACJI
# Skopiuj ten plik jako config.py i wypełnij własnymi danymi

# Klucz sekretny aplikacji (wygeneruj losowy string)
SECRET_KEY = 'twoj-losowy-sekretny-klucz-tutaj'

# Konfiguracja bazy danych
SQLALCHEMY_DATABASE_URI = 'sqlite:///events.db'
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Konfiguracja emaili
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_USERNAME = 'twoj-email@gmail.com'
MAIL_PASSWORD = 'twoje-haslo-aplikacji-gmail'
MAIL_DEFAULT_SENDER = 'twoj-email@gmail.com'
MAIL_ADMIN = 'email-do-powiadomien@gmail.com'