from datetime import datetime
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError
from typing import Any
import asyncio
import chime
import json
import logging
import os  # Moved from inside
import pytz
import websockets
import argparse  # Moved from inside


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


def ask_question(question: str, instructions: str) -> str:
    print(f"\033[1m{question}\033[0m")
    if instructions:
        print(instructions)
    return input("> \033[0m")


def main(argv: list[str] | None = None) -> None:
    # Explicitly configure logging as requested in code review
    logging.basicConfig(
        datefmt='%Y-%m-%d %H:%M:%S',
        format='[%(asctime)s] %(levelname)s: %(message)s',
        level=logging.INFO
    )

    port_env = os.environ.get('BOOKING_TOOL_PORT')
    try:
        default_port = int(port_env) if port_env is not None else 80
    except ValueError:
        logger.warning("Invalid BOOKING_TOOL_PORT value %r; falling back to 80", port_env)
        default_port = 80

    parser = argparse.ArgumentParser(
        prog='appointments',
        description=(
            'Finds Bürgeramt and other office appointments in Berlin. '
            'Also broadcasts results via websockets.'
        ),
        epilog='Made with ❤️ in Berlin'
    )
    parser.add_argument(
        '-i', '--id',
        help="A unique ID for your script. Used by the Berlin.de team to identify requests from you.",
        default=os.environ.get('BOOKING_TOOL_ID', '')
    )
    parser.add_argument(
        '-e', '--email',
        help="Your email address. Required by the Berlin.de team.",
        default=os.environ.get('BOOKING_TOOL_EMAIL', None)
    )
    parser.add_argument(
        '-u', '--url',
        help="URL to the service page on Berlin.de. For example, \"https://service.berlin.de/dienstleistung/120686/\"",
        default=os.environ.get('BOOKING_TOOL_URL', None)
    )
    parser.add_argument(
        '-q', '--quiet', action='store_true',
        help="Limit output to essential logging.",
        default=False
    )
    parser.add_argument(
        '-p', '--port', type=int,
        help="Expose a websockets server on that port. Allows other software to listen for new appointments.",
        default=default_port
    )
    args = parser.parse_args(argv)

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    service_page_url = args.url or ask_question(
        "What is the URL of the service you want to watch?",
        ("This is the service.berlin.de page for the service you want an appointment for. "
         "For example, \"https://service.berlin.de/dienstleistung/120686/\"")
    )

    email = args.email or ask_question(
        "What is your email address?",
        "It will be included in the requests this script makes. It's required by the Berlin.de appointments team."
    )

    asyncio.run(watch_for_appointments(service_page_url, email, args.id, args.port, args.quiet))


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


def _handle_appointment_error(
    error_type: str,
    err: Exception,
    quiet: bool,
    status_code: int,
    log_level: int = logging.WARNING
) -> dict[str, Any]:
    """Helper to handle common error reporting for look_for_appointments."""
    message = f'Could not fetch results from Berlin.de. - {str(err)}'
    if error_type == "unexpected":
        logger.exception("Unexpected error.")
    elif error_type == "playwright_timeout":
        logger.exception(f"Element selection timeout. Checking in {refresh_delay} seconds")
    else:
        logger.log(log_level, f"{str(err)}. Checking in {refresh_delay} seconds")

    if not quiet:
        chime.error()
    return {
        'time': datetime_to_json(datetime.now()),
        'status': status_code,
        'message': message if error_type != "unexpected" else f'Could not find appointments. - {str(err)}',
        'appointmentDates': [],
    }


async def look_for_appointments(
    browser: Browser,
    appointments_url: str,
    email: str,
    script_id: str,
    quiet: bool
) -> dict[str, Any]:
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
        return _handle_appointment_error("http", err, quiet, 502)
    except TimeoutError as err:
        return _handle_appointment_error("timeout", err, quiet, 504)
    except PlaywrightTimeoutError as err:
        return _handle_appointment_error("playwright_timeout", err, quiet, 504)
    except Exception as err:
        return _handle_appointment_error("unexpected", err, quiet, 500)


async def on_connect(client) -> None:
    """
    When a client connects via websockets, send them the latest results
    """
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


if __name__ == '__main__':
    main()
