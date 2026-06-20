FROM python:3.12-alpine

WORKDIR /usr/app

COPY pyproject.toml README.md ./
COPY tiktok_scraper ./tiktok_scraper

RUN python -m pip install --no-cache-dir .

ENV SCRAPING_FROM_DOCKER=1
RUN mkdir -p files

ENTRYPOINT ["tiktok-scraper"]
