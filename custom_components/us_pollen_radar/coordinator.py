"""Data update coordinator for US Pollen Radar.

Rate limiting design:
  - DataUpdateCoordinator enforces update_interval = 1 hour
  - _last_successful_fetch tracks the real wall-clock time of the last
    API call so that HA restarts / reloads never trigger a flood
  - Retries use exponential-ish back-off (5s, 10s, 15s) and give up
    after RETRY_ATTEMPTS — they do NOT reset the 1-hour timer
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging
import asyncio

from homeassistant import config_entries
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant

from .api import PollenApi
from .const import (
    DEFAULT_SYNC_INTERVAL,
    MIN_SYNC_INTERVAL,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF_BASE,
    DOMAIN,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)


class PollenDataUpdateCoordinator(DataUpdateCoordinator):
    """Manages fetching pollen data with strict 1-hour rate limiting."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: PollenApi,
        config_entry: config_entries.ConfigEntry | None,
    ) -> None:
        self.api = api
        self._hass = hass
        # Wall-clock timestamp of the last real API request (not HA state update)
        self._last_fetch_time: datetime | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # Primary guard: HA will not call _async_update_data more often than this
            update_interval=timedelta(seconds=DEFAULT_SYNC_INTERVAL),
            config_entry=config_entry,
        )

    def _seconds_since_last_fetch(self) -> float:
        """Return elapsed seconds since the last real API hit, or infinity if never fetched."""
        if self._last_fetch_time is None:
            return float("inf")
        return (datetime.now() - self._last_fetch_time).total_seconds()

    async def _async_update_data(self) -> dict:
        """Fetch data, honouring the hard rate-limit floor.

        Even if HA somehow calls this more often than update_interval
        (e.g. manual refresh, reload), we refuse to hit the API again
        until MIN_SYNC_INTERVAL seconds have elapsed.
        """
        elapsed = self._seconds_since_last_fetch()

        if elapsed < MIN_SYNC_INTERVAL:
            wait_remaining = MIN_SYNC_INTERVAL - elapsed
            _LOGGER.debug(
                "Rate-limit guard: %.0f s until next API fetch is allowed. "
                "Returning cached data.",
                wait_remaining,
            )
            # Return the existing cached data untouched
            if self.data:
                return self.data
            # First-run edge case: no cache yet but called too soon — wait it out
            await asyncio.sleep(wait_remaining)

        # --- Attempt the actual fetch with retries ---
        last_error: str = ""
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                _LOGGER.debug("Fetching pollen data (attempt %d/%d)", attempt, RETRY_ATTEMPTS)
                data = await self.api.async_get_data()
                pollen   = data.get("pollen", [])
                location = data.get("location", {})

                if not pollen:
                    raise UpdateFailed("Kleenex returned empty pollen data — city may be invalid")

                self._last_fetch_time = datetime.now()
                last_updated = datetime.now().replace(
                    tzinfo=ZoneInfo(self._hass.config.time_zone)
                )

                _LOGGER.info(
                    "Pollen data fetched for %s: Trees=%s PPM, Grass=%s PPM, Weeds=%s PPM",
                    location.get("city", "unknown"),
                    pollen[0].get("trees", "?"),
                    pollen[0].get("grass", "?"),
                    pollen[0].get("weeds", "?"),
                )

                return {
                    "pollen":       pollen,
                    "city":         location.get("city"),
                    "latitude":     location.get("latitude"),
                    "longitude":    location.get("longitude"),
                    "last_updated": last_updated,
                    "error":        "",
                }

            except UpdateFailed:
                raise  # Don't retry on data errors (city not found etc.)

            except Exception as exc:
                last_error = str(exc)
                backoff = attempt * RETRY_BACKOFF_BASE
                _LOGGER.warning(
                    "Attempt %d/%d failed (%s). Retrying in %ds.",
                    attempt, RETRY_ATTEMPTS, last_error, backoff,
                )
                if attempt < RETRY_ATTEMPTS:
                    await asyncio.sleep(backoff)

        # All retries exhausted — return stale cache if available
        _LOGGER.error(
            "All %d fetch attempts failed. Last error: %s. "
            "Serving stale cache if available.",
            RETRY_ATTEMPTS, last_error,
        )
        if self.data:
            return self.data | {"error": last_error}

        raise UpdateFailed(f"Could not fetch pollen data after {RETRY_ATTEMPTS} attempts: {last_error}")
