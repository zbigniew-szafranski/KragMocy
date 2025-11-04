# Konfiguracja projektu

## Pierwsze uruchomienie

1. Skopiuj plik `config.example.py` jako `config.py`:
   ```bash
   cp config.example.py config.py
   ```

2. Edytuj `config.py` i uzupełnij własnymi danymi:
   - SECRET_KEY - wygeneruj losowy string
   - MAIL_USERNAME - Twój email Gmail
   - MAIL_PASSWORD - hasło aplikacji z Gmail
   - MAIL_DEFAULT_SENDER - email nadawcy
   - MAIL_ADMIN - email do powiadomień

3. Uruchom aplikację:
   ```bash
   python app.py
   ```

**WAŻNE:** Nigdy nie commituj pliku `config.py` do repozytorium!
