# Schulverwaltung – Anwendungscontainer (Django + Gunicorn)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Eigener, unprivilegierter Benutzer statt root
RUN useradd --create-home --uid 1000 schule

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ /app/
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && mkdir -p /app/staticfiles /daten/dokumente \
    && SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && chown -R schule:schule /app /daten

USER schule
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/gesundheit/', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-"]
