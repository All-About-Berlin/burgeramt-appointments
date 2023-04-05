# Bürgeramt appointment finder

This server looks for Bürgeramt appointment every few seconds. You can make it look for any kind of appointment.

This is the code behind All About Berlin's [Bürgeramt appointment finder](https://allaboutberlin.com/tools/appointment-finder).

If this tool helped you, [make a donation](https://allaboutberlin.com/donate). Building things for Berliners is my full time job.

## Setup

### 1. Install the script

Run this command in your terminal:

```bash
# It might be called 'pip3' on your computer
pip install berlin-appointment-finder
```

You need Python 3 on your computer. If you have macOS or Linux, you already have it. If you have Windows, you're on your own.

### 2. Find the appointment type you need

Pick a service from the [list of services on Berlin.de](https://service.berlin.de/dienstleistungen/), and copy the URL. For example, `https://service.berlin.de/dienstleistung/120686/` for the *[Anmeldung](https://allaboutberlin.com/glossary/Anmeldung)*.

### 3. Run the script

Run this command and follow the instructions on your screen:

```bash
appointments
```

The script will check Berlin.de every 3 minutes. When it finds appointments, it lists them. Just keep an eye on the terminal.

## Instructions for nerds

This script can be configured with command line arguments or environment variables.

Type `appointments --help` to see available command line arguments.

These are the available environment variables:

    ```bash
    BOOKING_TOOL_EMAIL=your@email.com
    BOOKING_TOOL_ID=johnsmith-dev
    BOOKING_TOOL_URL=https://service.berlin.de/dienstleistung/120686/
    ```

The script broadcasts broadcasts the appointments it finds with websockets. By default, it broadcasts them on port 80.

A Dockerfile is supplied in this repo. It's the same one I use on All About Berlin.

The polling rate is limited to 180 seconds (3 minutes), as required by the Berlin.de IKT-ZMS team (ikt-zms@seninnds.berlin.de).