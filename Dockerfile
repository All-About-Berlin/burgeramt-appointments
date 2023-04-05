FROM python:3.10-slim
COPY requirements.txt requirements.txt
COPY src /var/appointments
RUN pip install -e /var/appointments
CMD appointments -q
