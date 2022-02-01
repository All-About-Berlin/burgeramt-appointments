from bs4 import BeautifulSoup, SoupStrainer
from datetime import date, datetime
from datetime import datetime, date, timedelta
from pathlib import Path
import asyncio
import csv
import json
import logging
import pytz
import random
import requests
import time
import websockets
import telegram

logging.basicConfig(
    datefmt='%Y-%m-%d %H:%M:%S',
    format='[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
    level=logging.WARNING,
)
logger = logging.getLogger(__name__)


common_user_agents = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36 Edg/96.0.1054.62',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36',
)

timezone = pytz.timezone('Europe/Berlin')
appointments_url = 'https://service.berlin.de/terminvereinbarung/termin/tag.php?termin=1&anliegen[]=120686&dienstleisterlist=122210,122217,327316,122219,327312,122227,327314,122231,122243,327348,122252,329742,122260,329745,122262,329748,122254,329751,122271,327278,122273,327274,122277,327276,330436,122280,327294,122282,327290,122284,327292,327539,122291,327270,122285,327266,122286,327264,122296,327268,150230,329760,122301,327282,122297,327286,122294,327284,122312,329763,122314,329775,122304,327330,122311,327334,122309,327332,122281,327352,122279,329772,122276,327324,122274,327326,122267,329766,122246,327318,122251,327320,122257,327322,122208,327298,122226,327300&herkunft=http%3A%2F%2Fservice.berlin.de%2Fdienstleistung%2F120686%2F'
delay = 30


def datetime_to_json(datetime_obj):
    return datetime_obj.strftime('%Y-%m-%dT%H:%M:%SZ')


connected_clients = []
last_message = {
    'time': datetime_to_json(datetime.now()),
    'status': 200,
    'appointmentDates': [],
    'connectedClients': len(connected_clients)
}


def get_appointments():
    today = timezone.localize(datetime.now())
    next_month = timezone.localize(datetime(today.year, today.month % 12 + 1, 1))
    next_month_timestamp = int(next_month.timestamp())

    session = requests.Session()
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': random.choice(common_user_agents),
        'Accept-Language': 'en-gb',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }

    response_p1 = session.get(appointments_url, headers=headers)
    response_p1.raise_for_status()
    time.sleep(5)
    response_p2 = session.get(f'https://service.berlin.de/terminvereinbarung/termin/day/{next_month_timestamp}/', headers=headers)
    response_p2.raise_for_status()

    return sorted(parse_appointment_dates(response_p1.text) + parse_appointment_dates(response_p2.text))


def parse_appointment_dates(page_content):
    appointment_strainer = SoupStrainer('a', title='An diesem Tag einen Termin buchen')
    bookable_cells = BeautifulSoup(page_content, 'lxml', parse_only=appointment_strainer).find_all('a')
    appointment_dates = []
    for bookable_cell in bookable_cells:
        timestamp = int(bookable_cell['href'].rstrip('/').split('/')[-1])
        appointment_dates.append(timezone.localize(datetime.fromtimestamp(timestamp)))

    return appointment_dates


def look_for_appointments():
    global delay
    try:
        appointments = get_appointments()
        delay = 30
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 200,
            'message': None,
            'appointmentDates': [datetime_to_json(d) for d in appointments],
            'connectedClients': len(connected_clients),
        }
    except requests.HTTPError as err:
        logger.warning(f"Got {err.response.status_code} error. Checking in 300 seconds")
        delay = 300
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 502,
            'message': f'Could not fetch results from Berlin.de - Got HTTP {err.response.status_code}.',
            'appointmentDates': [],
            'connectedClients': len(connected_clients),
        }
    except Exception as err:
        logger.exception("Could not fetch results due to an unexpected error.")
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 500,
            'message': f'An unknown error occured: {str(err)}',
            'appointmentDates': [],
            'connectedClients': len(connected_clients),
        }


async def on_connect(websocket, path):
    global last_message
    connected_clients.append(websocket)
    last_message['connectedClients'] = len(connected_clients)
    try:
        websockets.broadcast(connected_clients, json.dumps(last_message))
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)

#  Telegram Notifcation Added by Siva Rajendran

def telegram_notify(message):
    with open('./config/config.json', 'r') as config_file:
        t = json.load(config_file)
        token = t['telegram_token']
        chat_id = t['telegram_chat_id']
        notify = telegram.Bot(token=token)
    # Loads the Json results
    available_dates = []
    available_datestring = []
    if not last_message['appointmentDates']: # To check if its an empty array
        print("No Appointment dates available")
        notify.sendMessage(chat_id=chat_id, text="No Appointment dates are found so far")
    else:   
        for dates in message['appointmentDates']:     
            if dates not in available_datestring:  # To check for duplicates inside dates                
                datestime = datetime.strptime(dates,'%Y-%m-%dT%H:%M:%SZ')
                date_str = datestime.strftime("%d-%b-%Y")
                available_dates.append(date_str)
                available_dates_str = ','.join(available_dates)
                available_datestring.append(dates)            
        notify_str= "The next appointment for flat registration is available on the following dates "+available_dates_str+". Please use this URL to book the appointment faster: "+appointments_url
        notify.sendMessage(chat_id=chat_id, text=notify_str)

async def main():
    global last_message
    async with websockets.serve(on_connect, port=80):
        while True:
            last_message = look_for_appointments()
            telegram_notify(last_message) # Telegram Notification
            websockets.broadcast(connected_clients, json.dumps(last_message))
            await asyncio.sleep(delay)


if __name__ == "__main__":
    asyncio.run(main())
