FROM python:3.10-alpine

# Устанавливаем клиент PostgreSQL
RUN apk add --no-cache postgresql-client

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

# Скрипт для применения миграций
COPY apply_migrations.sh /app/
RUN chmod +x /app/apply_migrations.sh

CMD ["/bin/sh", "/app/apply_migrations.sh"]