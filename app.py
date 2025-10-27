from flask import Flask, render_template
import ephem
from datetime import datetime

from openpyxl.styles.builtins import title

app = Flask(__name__)


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


# Lista wydarzeń - TUTAJ DODAJESZ NOWE WYDARZENIA
EVENTS = [
    {
        'id': 1,
        'title': 'Męski Krąg Mocy',
        'date': datetime(2025, 11, 21, 18, 0, 0),
        'location': 'Motylarnia, Długołęka, Wiejska 9',
        'description': 'Pierwsze spotkanie tego Kręgu. Serdecznie zapraszam',
        'duration': '3 godziny',
        'spots_total': 10,      # Liczba miejsc ogółem
        'spots_taken': 3,       # Liczba zajętych miejsc
        'image': 'kragmocy1.png'
    },
    {
        'id': 2,
        'title': 'Aromaterapia jako wsparcie dla ciała i ducha',
        'date': datetime(2025, 12, 3, 18, 0, 0),
        'location': 'Motylarnia, Długołęka, Wiejska 9',
        'description': 'Odkryj moc czystych ekstaktów ziołowych zamkniętych w olejku eterycznym. Poznaj ich działanie dla ciała i ducha. Stwórz swoją własną kompozycję.',
        'duration': '2 godziny',
        'spots_total': 20,
        'spots_taken': 0,
        'image': 'air_doterra.jpg'
    },
    {
        'id': 3,
        'title': 'Zimowy Krąg w Górach',
        'date': datetime(2026, 1, 20, 9, 0, 0),
        'location': 'Bieszczady',
        'description': 'Weekendowy wyjazd do gór. Wędrówki, rozmowy przy ognisku, sauna i lodowata kąpiel.',
        'duration': '2 dni',
        'spots_total': 10,
        'spots_taken': 2,
        'image': None
    }
]


@app.route('/')
def index():
    # Najbliższe wydarzenie
    upcoming_events = sorted([e for e in EVENTS if e['date'] > datetime.now()], key=lambda x: x['date'])
    next_event = upcoming_events[0] if upcoming_events else None

    if next_event:
        moon_phase = get_moon_phase(next_event['date'])
        event_date_str = next_event['date'].strftime('%Y-%m-%dT%H:%M:%S')
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
    # Sortuj wydarzenia: najpierw nadchodzące, potem przeszłe
    now = datetime.now()
    upcoming = sorted([e for e in EVENTS if e['date'] > now], key=lambda x: x['date'])
    past = sorted([e for e in EVENTS if e['date'] <= now], key=lambda x: x['date'], reverse=True)

    # Dodaj fazę księżyca i oblicz wolne miejsca
    for event in upcoming + past:
        event['moon_phase'] = get_moon_phase(event['date'])
        event['is_past'] = event['date'] <= now
        event['spots_available'] = event['spots_total'] - event['spots_taken']
        event['is_full'] = event['spots_taken'] >= event['spots_total']

    return render_template('wydarzenia.html',
                           title='Wydarzenia',
                           upcoming_events=upcoming,
                           past_events=past)


@app.route('/olejki')
def olejki():
    return render_template('olejki.html', title='Oleje Eteryczne')


@app.route('/woda')
def woda():
    return render_template('woda.html', title='Woda Wodorowa')

@app.route('/joga')
def joga():
    return render_template('joga.html', title='Joga')


@app.route('/zielone')
def zielone():
    return render_template('zielone.html', title='Zielona Żywność')


if __name__ == '__main__':
    app.run(host='192.168.0.112', port=5000, debug=True)