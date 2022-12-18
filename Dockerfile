FROM python:3.9-slim

ADD . /app
WORKDIR /app
RUN mkdir -p logs

RUN pip install -U pip
RUN pip install -r requirements.txt
CMD ["python", "booster_bot.py"]