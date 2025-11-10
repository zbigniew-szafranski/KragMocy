from app import app, db, ContactMessage

def add_contact_table():
    """Dodaje tylko tabelę contact_message bez usuwania istniejących danych"""
    with app.app_context():
        # Utwórz tylko nową tabelę
        db.create_all()
        print("✅ Tabela contact_message została dodana!")

if __name__ == '__main__':
    add_contact_table()