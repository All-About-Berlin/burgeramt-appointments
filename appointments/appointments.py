from datetime import datetime
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError
from typing import Any
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


class HTTPError(Exception):
    def __init__(self, status: int, url: str):
        self.status = status
        self.url = url
        super().__init__(f"Got {status} error for URL '{url}'")


def datetime_to_json(datetime_obj: datetime) -> str:
    return datetime_obj.strftime('%Y-%m-%dT%H:%M:%SZ')


connected_clients = []
last_message = {
    'time': datetime_to_json(datetime.now()),
    'status': 200,
    'appointmentDates': [],
    'lastAppointmentsFoundOn': None,
}

timezone = pytz.timezone('Europe/Berlin')


async def goto_or_fail(page: Page, url: str, timeout=10000) -> None:
    try:
        response = await page.goto(url, timeout=timeout)
    except PlaywrightTimeoutError as err:
        raise TimeoutError(f"Request to '{url}' timed out") from err

    if not response:
        raise ConnectionError(f"Could not connect to {url}")
    elif not response.ok:
        raise HTTPError(response.status, url)


async def get_appointments(browser: Browser, appointments_url: str, email: str, script_id: str) -> list[datetime]:
    """
    Fetch the appointments calendar on Berlin.de, parse it, and return appointment dates.
    """
    today = timezone.localize(datetime.now())
    next_month = timezone.localize(datetime(today.year, today.month % 12 + 1, 1))
    next_month_timestamp = int(next_month.timestamp())

    context = await browser.new_context()
    page = await context.new_page()

    try:
        # Load the first calendar page
        await goto_or_fail(page, appointments_url)
        page1_dates = await parse_appointment_dates(page)

        # Load the next month page
        await goto_or_fail(page, f'https://service.berlin.de/terminvereinbarung/termin/day/{next_month_timestamp}/')
        page2_dates = await parse_appointment_dates(page)
    finally:
        await page.close()
        await context.close()

    return sorted(list(set(page1_dates + page2_dates)))


async def parse_appointment_dates(page: Page) -> list[datetime]:
    links = await page.query_selector_all("td.buchbar a")
    appointment_dates = []
    for link in links:
        href = await link.get_attribute("href")
        if href:
            timestamp = int(href.rstrip("/").split("/")[-1])
            appointment_dates.append(timezone.localize(datetime.fromtimestamp(timestamp)))
    return appointment_dates


async def look_for_appointments(browser: Browser, appointments_url: str, email: str, script_id: str, quiet: bool) -> dict[str, Any]:
    """
    Look for appointments, return a response dict
    """
    try:
        appointments = await get_appointments(browser, appointments_url, email, script_id)
        logger.info(f"Found {len(appointments)} appointments: {[datetime_to_json(d) for d in appointments]}")
        if len(appointments) and not quiet:
            chime.info()
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 200,
            'message': None,
            'appointmentDates': [datetime_to_json(d) for d in appointments],
        }
    except HTTPError as err:
        logger.warning(f"{str(err)}. Checking in {refresh_delay} seconds")
        if not quiet:
            chime.error()
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 502,
            'message': f'Could not fetch results from Berlin.de - {str(err)}',
            'appointmentDates': [],
        }
    except TimeoutError as err:
        logger.warning(f"{str(err)}. Checking in {refresh_delay} seconds")
        if not quiet:
            chime.error()
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 504,
            'message': f'Could not fetch results from Berlin.de. - {str(err)}',
            'appointmentDates': [],
        }
    except PlaywrightTimeoutError as err:
        logger.exception(f"Element selection timeout. Checking in {refresh_delay} seconds")
        if not quiet:
            chime.error()
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 504,
            'message': f'Could not fetch results from Berlin.de. - {str(err)}',
            'appointmentDates': [],
        }
    except Exception as err:
        logger.exception("Unexpected error.")
        if not quiet:
            chime.error()
        return {
            'time': datetime_to_json(datetime.now()),
            'status': 500,
            'message': f'Could not find appointments. - {str(err)}',
            'appointmentDates': [],
        }


async def on_connect(client) -> None:
    """
    When a client connects via websockets, send them the latest results
    """
    global last_message
    connected_clients.append(client)
    try:
        await client.send(json.dumps(last_message))
        await client.wait_closed()
    finally:
        connected_clients.remove(client)


async def watch_for_appointments(service_page_url: str, email: str, script_id: str, server_port: int, quiet: bool) -> None:
    """
    Constantly look for new appointments on Berlin.de until stopped. Broadcast the appointments via websockets.
    """
    global last_message
    logger.info(f"Getting appointment URL for {service_page_url}")

    service_id = service_page_url.rstrip('/').split('/')[-1]
    appointments_url = f"https://service.berlin.de/terminvereinbarung/termin/all/{service_id}/"

    logger.info(f"URL found: {appointments_url}")
    async with websockets.serve(on_connect, port=server_port), async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        logger.info(f"Server is running on port {server_port}. Looking for appointments every {refresh_delay} seconds.")
        while True:
            last_appts_found_on = last_message['lastAppointmentsFoundOn']
            last_message = await look_for_appointments(browser, appointments_url, email, script_id, quiet)
            if last_message['appointmentDates']:
                last_message['lastAppointmentsFoundOn'] = datetime_to_json(datetime.now())
            else:
                last_message['lastAppointmentsFoundOn'] = last_appts_found_on

            websockets.broadcast(connected_clients, json.dumps(last_message))

            await asyncio.sleep(refresh_delay)

        await browser.close()
