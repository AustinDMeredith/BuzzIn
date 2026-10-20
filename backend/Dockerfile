FROM python:3.14-slim
WORKDIR /buzzInBackend

COPY ./requirements.txt /buzzInBackend/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /buzzInBackend/requirements.txt
COPY ./app /buzzInBackend/app

RUN useradd --no-create-home --shell /usr/sbin/nologin appuser
USER appuser

CMD ["fastapi", "run", "app/main.py", "--port", "8000"]
