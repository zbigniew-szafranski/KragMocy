from app import app, db, Event, Registration, ContactMessage
from datetime import datetime

def init_database():
    """Inicjalizuje bazę danych i dodaje przykładowe wydarzenia"""
    with app.app_context():
        # Usuń wszystkie tabele i stwórz na nowo
        db.drop_all()
        db.create_all()

        # Dodaj wydarzenia z poprzedniej listy
        events = [
            Event(
                title='Męski Krąg Mocy',
                date=datetime(2025, 11, 21, 18, 0, 0),
                location='Motylarnia, Długołęka, Wiejska 9',
                description='Pierwsze spotkanie tego Kręgu. Serdecznie zapraszam',
                duration='3 godziny',
                spots_total=10,
                spots_taken=3,
                image='kragmocy1.png'
            ),
            Event(
                title='Aromaterapia jako wsparcie dla ciała i ducha',
                date=datetime(2025, 12, 3, 18, 0, 0),
                location='Motylarnia, Długołęka, Wiejska 9',
                description='Odkryj moc czystych ekstaktów ziołowych zamkniętych w olejku eterycznym. Poznaj ich działanie dla ciała i ducha. Stwórz swoją własną kompozycję.',
                duration='2 godziny',
                spots_total=20,
                spots_taken=0,
                image='air_doterra.jpg'
            ),
        ]

        # Dodaj wszystkie wydarzenia do bazy
        for event in events:
            db.session.add(event)

        # Zapisz zmiany
        db.session.commit()

        print("✅ Baza danych została zainicjalizowana!")
        print(f"✅ Dodano {len(events)} wydarzeń")


if __name__ == '__main__':
    init_database()