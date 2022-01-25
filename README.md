# Bürgeramt appointment finder

This server looks for Bürgeramt appointment every few seconds, and broadcasts the results via websockets. This is the code behind https://allaboutberlin.com/appointments

## Setup

### Standalone

```
pip install -r requirements.txt
python3 appointments.py
```

### Docker

A Dockerfile is supplied with the repository.