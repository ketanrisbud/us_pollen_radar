"""Constants for the US Pollen Radar integration."""

from enum import Enum

NAME = "US Pollen Radar"
DOMAIN = "us_pollen_radar"
MANUFACTURER = "Kleenex"
MODEL = "Pollen Radar"

SENSOR = "sensor"
PLATFORMS = [SENSOR]

# Rate limiting — poll ONCE per hour maximum.
# Kleenex only updates their data every 3 hours anyway.
DEFAULT_SYNC_INTERVAL = 3600       # seconds — 1 hour between polls
MIN_SYNC_INTERVAL     = 3600       # hard floor — never allow faster than 1hr
RETRY_ATTEMPTS        = 3          # max retries on failure before giving up
RETRY_BACKOFF_BASE    = 5          # seconds — sleep = attempt * RETRY_BACKOFF_BASE

CONF_NAME = "name"
CONF_CITY = "city"

POLLEN_URL = "https://www.kleenex.com/api/sitecore/Pollen/GetPollenContentNACity"
