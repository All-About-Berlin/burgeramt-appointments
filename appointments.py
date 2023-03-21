from bs4 import BeautifulSoup, SoupStrainer
from datetime import datetime
import asyncio
import json
import logging
import os
import pytz
import requests
import time
import websockets


logging.basicConfig(
    datefmt='%Y-%m-%d %H:%M:%S',
    format='[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Disable websocket connection log spam
logging.getLogger('websockets.server').setLevel(logging.ERROR)

server_port = 80

try:
    # Berlin.de requires the user agent to include your email.
    email = os.environ['BOOKING_TOOL_EMAIL']

    # This allows Berlin.de to distinguish different between people running the same tool.
    script_id = os.environ['BOOKING_TOOL_ID']
except KeyError:
    exception_message = "You must set the BOOKING_TOOL_EMAIL and BOOKING_TOOL_ID environment variables."
    logger.exception(exception_message)
    raise Exception(exception_message)


timezone = pytz.timezone('Europe/Berlin')
appointments_url = 'https://service.berlin.de/terminvereinbarung/termin/tag.php?termin=1&anliegen[]=120686&dienstleisterlist=122210,122217,327316,122219,327312,122227,327314,122231,327346,122243,327348,122254,122252,329742,122260,329745,122262,329748,122271,327278,122273,327274,122277,327276,330436,122280,327294,122282,327290,122284,327292,122291,327270,122285,327266,122286,327264,122296,327268,150230,329760,122297,327286,122294,327284,122312,329763,122314,329775,122304,327330,122311,327334,122309,327332,317869,122281,327352,122279,329772,122283,122276,327324,122274,327326,122267,329766,122246,327318,122251,327320,122257,327322,122208,327298,122226,327300&herkunft=http%3A%2F%2Fservice.berlin.de%2Fdienstleistung%2F120686%2F'
delay = 180  # Minimum allowed by Berlin.de's IKT-ZMS team.


def datetime_to_json(datetime_obj):
    return datetime_obj.strftime('%Y-%m-%dT%H:%M:%SZ')


connected_clients = []
last_message = {
    'time': datetime_to_json(datetime.now()),
    'status': 200,
    'appointmentDates': [],
}


def get_appointments():
    today = timezone.localize(datetime.now())
    next_month = timezone.localize(datetime(today.year, today.month % 12 + 1, 1))
    next_month_timestamp = int(next_month.timestamp())

    session = requests.Session()
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': f"Mozilla/5.0 AppointmentBookingTool/1.1 (https://github.com/nicbou/burgeramt-appointments-websockets; {email}; {script_id})",
        'Accept-Language': 'en-gb',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }

    # Load the first two months
    response_p1 = session.get(appointments_url, headers=headers)
    response_p1.raise_for_status()
    time.sleep(1)

    # Load the next two months
    response_p2 = session.get(
        f'https://service.berlin.de/terminvereinbarung/termin/day/{next_month_timestamp}/',
        headers=headers
    )
    response_p2.raise_for_status()

    return sorted(list(set(parse_appointment_dates(response_p1.text) + parse_appointment_dates(response_p2.text))))


def parse_appointment_dates(page_content):
    appointment_strainer = SoupStrainer('td', class_='buchbar')
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
        delay = 180
        logger.info(f"Found {len(appointments)} appointments: {[datetime_to_json(d) for d in appointments]}")
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 200,
            'message': None,
            'appointmentDates': [datetime_to_json(d) for d in appointments],
        }
    except requests.HTTPError as err:
        delay = 360
        logger.warning(f"Got {err.response.status_code} error. Checking in {delay} seconds")
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 502,
            'message': f'Could not fetch results from Berlin.de - Got HTTP {err.response.status_code}.',
            'appointmentDates': [],
        }
    except requests.exceptions.ConnectionError:
        logger.warning("Could not connect to Berlin.de.")
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 502,
            'message': 'Could not fetch results from Berlin.de - Got connection error.',
            'appointmentDates': [],
        }
    except Exception as err:
        logger.exception("Could not fetch results due to an unexpected error.")
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 500,
            'message': f'An unknown error occured: {str(err)}',
            'appointmentDates': [],
        }


async def on_connect(client, path):
    global last_message
    connected_clients.append(client)
    try:
        await client.send(json.dumps(last_message))
        await client.wait_closed()
    finally:
        connected_clients.remove(client)


async def main():
    global last_message
    async with websockets.serve(on_connect, port=server_port):
        logger.info(f"Server is running on port {server_port}...")
        while True:
            last_message = look_for_appointments()
            websockets.broadcast(connected_clients, json.dumps(last_message))
            await asyncio.sleep(delay)


if __name__ == "__main__":
    asyncio.run(main())
