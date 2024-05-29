FROM python:3.12
RUN pip install docker flask
WORKDIR /app
COPY app.py /app/app.py