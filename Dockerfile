FROM python:3.10-slim
COPY . /var/appointments
RUN pip install -e /var/appointments
CMD /usr/local/bin/appointments -q
