# Bürgeramt appointment finder

This server looks for Bürgeramt appointment every few seconds, and broadcasts the results via websockets. This is the code behind https://allaboutberlin.com/appointments

## Setup

### Standalone

```
pip install -r requirements.txt
python3 appointments.py
```
### Telegram Notification

Now it is possible to get notified via telegram regarding the appointment dates along with the appointment url. Just click on it and book it right away.

- Go to config directory and rename the config.bak.json to config.json

- Add the telegram api key and the chat id in config.json
 
### Docker

A Dockerfile is supplied with the repository.
