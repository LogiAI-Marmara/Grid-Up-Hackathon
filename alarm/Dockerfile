FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir requests==2.32.3

COPY alarm_service.py durum.py kanallar.py ./

# Alarm durumu (imleç + bekleyen bildirimler + tekrar önleme kayıtları) burada
# tutulur ve konteyner yeniden oluşturulduğunda korunmalıdır (A-04). Dizinin
# kalıcı bir volume'a bağlanması compose'un işidir; bağlanmazsa servis çalışır
# ama yeniden oluşturmada geçmişini kaybeder.
ENV ALARM_STATE_FILE=/durum/alarm_state.json
RUN mkdir -p /durum
VOLUME ["/durum"]

CMD ["python", "alarm_service.py"]
