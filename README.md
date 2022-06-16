# Bürgeramt appointment finder

This server looks for Bürgeramt appointment every few seconds, and broadcasts the results via websockets. This is the code behind All About Berlin's [Bürgeramt appointment finder](https://allaboutberlin.com/tools/appointment-finder)

## Setup

### Standalone

1. Set the required environment variables:
    ```
    export BOOKING_TOOL_EMAIL=your@email.com
    export BOOKING_TOOL_ID=johnsmith-dev
    ```

2. Run the appointment booking tool
    ```
    pip install -r requirements.txt
    python3 appointments.py
    ```

The tool outputs the appointments it finds and the errors to the console, and broadcasts them with websockets.

### Docker

A Dockerfile is supplied with the repository.

## Notes

The polling rate is limited to 180 seconds (3 minutes), as required by the Berlin.de IKT-ZMS team (ikt-zms@seninnds.berlin.de).
