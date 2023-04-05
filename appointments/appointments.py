from bs4 import BeautifulSoup, SoupStrainer
from datetime import datetime
import aiohttp
import asyncio
import chime
import json
import logging
import pytz
import websockets


logger = logging.getLogger()

chime.theme('material')

# Disable websocket connection log spam
logging.getLogger('websockets.server').setLevel(logging.ERROR)

refresh_delay = 180  # Minimum allowed by Berlin.de's IKT-ZMS team.


def datetime_to_json(datetime_obj):
    return datetime_obj.strftime('%Y-%m-%dT%H:%M:%SZ')


connected_clients = []
last_message = {
    'time': datetime_to_json(datetime.now()),
    'status': 200,
    'appointmentDates': [],
}


timezone = pytz.timezone('Europe/Berlin')


async def get_appointments_url(service_page_url: str, email: str, script_id: str):
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': f"Mozilla/5.0 AppointmentBookingTool/1.1 (https://github.com/nicbou/burgeramt-appointments-websockets; {email}; {script_id})",
        'Accept-Language': 'en-gb',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(service_page_url, headers=headers) as response:
            service_page_content = await response.text()
            termin_suchen_button = SoupStrainer('div', class_='zmstermin-multi inner')
            termin_suchen_link = BeautifulSoup(service_page_content, 'lxml', parse_only=termin_suchen_button).find('a')
            return termin_suchen_link['href']


async def get_appointments(appointments_url: str, email: str, script_id: str) -> list:
    """
    Fetches the appointments calendar on Berlin.de, parses it, and returns available appointment dates.
    """
    today = timezone.localize(datetime.now())
    next_month = timezone.localize(datetime(today.year, today.month % 12 + 1, 1))
    next_month_timestamp = int(next_month.timestamp())

    async with aiohttp.ClientSession(raise_for_status=True) as session:
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': f"Mozilla/5.0 AppointmentBookingTool/1.1 (https://github.com/nicbou/burgeramt-appointments-websockets; {email}; {script_id})",
            'Accept-Language': 'en-gb',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

        # Load the first two months
        response_p1 = await session.get(appointments_url, headers=headers, timeout=20)
        response_p1.raise_for_status()
        await asyncio.sleep(1)

        # Load the next two months
        response_p2 = await session.get(
            f'https://service.berlin.de/terminvereinbarung/termin/day/{next_month_timestamp}/',
            headers=headers, timeout=20
        )
        response_p2.raise_for_status()

    return sorted(
        list(
            set(
                parse_appointment_dates(await response_p1.text())
                + parse_appointment_dates(await response_p2.text())
            )
        )
    )


def parse_appointment_dates(page_content: str) -> list:
    """
    Parse the content of the calendar page on Berlin.de, and returns available appointment dates.
    """
    appointment_strainer = SoupStrainer('td', class_='buchbar')
    bookable_cells = BeautifulSoup(page_content, 'lxml', parse_only=appointment_strainer).find_all('a')
    appointment_dates = []
    for bookable_cell in bookable_cells:
        timestamp = int(bookable_cell['href'].rstrip('/').split('/')[-1])
        appointment_dates.append(timezone.localize(datetime.fromtimestamp(timestamp)))

    return appointment_dates


async def look_for_appointments(appointments_url: str, email: str, script_id: str, quiet: bool) -> dict:
    try:
        appointments = await get_appointments(appointments_url, email, script_id)
        logger.info(f"Found {len(appointments)} appointments: {[datetime_to_json(d) for d in appointments]}")
        if len(appointments) and not quiet:
            chime.info()
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 200,
            'message': None,
            'appointmentDates': [datetime_to_json(d) for d in appointments],
        }
    except aiohttp.ClientResponseError as err:
        logger.warning(f"Got {err.status} error. Checking in {refresh_delay} seconds")
        if not quiet:
            chime.error()
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 502,
            'message': f'Could not fetch results from Berlin.de - Got HTTP {err.status}.',
            'appointmentDates': [],
        }
    except aiohttp.ClientConnectorError:
        logger.warning("Could not connect to Berlin.de.")
        if not quiet:
            chime.error()
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 502,
            'message': 'Could not fetch results from Berlin.de - Got connection error.',
            'appointmentDates': [],
        }
    except Exception as err:
        logger.exception("Could not fetch results due to an unexpected error.")
        if not quiet:
            chime.error()
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 500,
            'message': f'An unknown error occured: {str(err)}',
            'appointmentDates': [],
        }


async def on_connect(client, path):
    """
    When a client connects, send them the latest results
    """
    global last_message
    connected_clients.append(client)
    try:
        await client.send(json.dumps(last_message))
        await client.wait_closed()
    finally:
        connected_clients.remove(client)


async def watch_for_appointments(service_page_url: str, email: str, script_id: str, server_port: int, quiet: bool):
    """
    Constantly look for new appointments on Berlin.de until stopped.
    """
    global last_message
    logger.info(f"Getting appointment URL for {service_page_url}")
    appointments_url = await get_appointments_url(service_page_url, email, script_id)
    logger.info(f"URL found: {appointments_url}")
    async with websockets.serve(on_connect, port=server_port):
        logger.info(f"Server is running on port {server_port}. Looking for appointments every {refresh_delay} seconds.")
        while True:
            last_message = await look_for_appointments(appointments_url, email, script_id, quiet)
            websockets.broadcast(connected_clients, json.dumps(last_message))
            await asyncio.sleep(refresh_delay)
