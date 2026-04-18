"""US Pollen Radar API — scrapes kleenex.com for US cities."""

from typing import Any
import logging
from datetime import datetime, date

import aiohttp
import async_timeout
from bs4 import BeautifulSoup, Tag
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, POLLEN_URL

TIMEOUT = 10
_LOGGER: logging.Logger = logging.getLogger(__package__)


class PollenApi:
    """US Pollen Radar API client."""

    _headers: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.3"
        ),
    }

    _pollen_na_types: dict[str, tuple[str, str]] = {
        "trees": ("TreesRiskData", "tree-ppm"),
        "weeds": ("WeedsRiskData", "weed-ppm"),
        "grass": ("GrassRiskData", "grass-ppm"),
    }

    _pollen_species_class: dict[str, str] = {
        "trees": "tree-type",
        "weeds": "weed-type",
        "grass": "grass-type",
    }

    def __init__(self, session: aiohttp.ClientSession, city: str) -> None:
        self._session = session
        self.city = city
        self._raw_data: str = ""
        self._pollen: list[dict[str, Any]] = []
        self._found_city: str = ""
        self._found_latitude: float = 0.0
        self._found_longitude: float = 0.0

    async def async_get_data(self) -> dict[str, Any]:
        """Fetch and return parsed pollen data."""
        await self._refresh_data()
        return {
            "pollen": self._pollen,
            "location": {
                "city": self._found_city,
                "latitude": self._found_latitude,
                "longitude": self._found_longitude,
            },
        }

    async def _refresh_data(self) -> None:
        data = await self._perform_request()
        if data:
            self._raw_data = data
            self._decode_raw_data_na()

    async def _perform_request(self) -> str | None:
        try:
            async with async_timeout.timeout(TIMEOUT):
                response = await self._session.get(
                    url=POLLEN_URL,
                    params={"city": self.city},
                    headers=self._headers,
                    ssl=False,
                )
                if response.status == 403:
                    _LOGGER.error("Access forbidden (403) from Kleenex server")
                    return None
                if response.ok:
                    return await response.text()
                return None
        except aiohttp.ClientConnectorDNSError as e:
            raise DNSError(
                "dns_error",
                translation_domain=DOMAIN,
                translation_key="dns_error",
            ) from e
        except Exception as e:
            raise DNSError(
                "unknown_error",
                translation_domain=DOMAIN,
                translation_key="unknown_error",
            ) from e

    def _decode_raw_data_na(self) -> None:
        """Parse the US Kleenex pollen HTML response.

        HTML structure per day:
          <p class="date-heading">City | Monday April 21 </p>
          <div class="data-container">
            <li class="... tree-learn-more ...">
              <input data-id="TreesRiskData" value="high" />
              <p class="ppm-level tree-ppm">391 PPM</p>
              <p class="allergen-type tree-type">Oak</p>
            </li>
            <li class="... grass-learn-more ...">
              <input data-id="GrassRiskData" value="low" />
              <p class="ppm-level grass-ppm">0 PPM</p>
              <p class="allergen-type grass-type">Grass/Poaceae</p>
            </li>
            <li class="... weed-learn-more ...">
              <input data-id="WeedsRiskData" value="low" />
              <p class="ppm-level weed-ppm">0 PPM</p>
              <p class="allergen-type weed-type">Ragweed</p>
            </li>
          </div>
        """
        soup = BeautifulSoup(self._raw_data, "html.parser")
        self._extract_location_data(soup)

        pollen_tracker = soup.find("div", class_="pollen-tracker")
        if not pollen_tracker or not isinstance(pollen_tracker, Tag):
            _LOGGER.warning("Could not find pollen-tracker div in response")
            return

        day_divs = [el for el in pollen_tracker.children if isinstance(el, Tag)]
        self._pollen = []

        for day_div in day_divs:
            date_heading = day_div.find("p", class_="date-heading")
            if not date_heading or not isinstance(date_heading, Tag):
                continue
            try:
                day_no = int(date_heading.text.strip().split()[-1])
            except (ValueError, IndexError):
                continue

            pollen_date = self._determine_pollen_date(day_no)
            pollen: dict[str, Any] = {"day": day_no, "date": pollen_date}

            for pollen_type, (risk_id, ppm_class) in self._pollen_na_types.items():
                # Level
                risk_input = day_div.find("input", attrs={"data-id": risk_id})
                if risk_input and isinstance(risk_input, Tag):
                    pollen_level = risk_input.get("value", "") or self.determine_level_by_count(pollen_type, 0)
                else:
                    pollen_level = self.determine_level_by_count(pollen_type, 0)

                # PPM count
                ppm_el = day_div.find("p", class_=ppm_class)
                count_unit = ppm_el.text.strip() if ppm_el else "0 PPM"
                try:
                    pollen_count, unit_of_measure = count_unit.split(" ")
                    pollen[pollen_type] = int(pollen_count)
                except (ValueError, AttributeError):
                    pollen[pollen_type] = 0
                    unit_of_measure = "ppm"

                pollen[f"{pollen_type}_level"] = pollen_level
                pollen[f"{pollen_type}_unit_of_measure"] = unit_of_measure.lower()

                # Species name — e.g. "Oak", "Ragweed", "Grass/Poaceae"
                species_class = self._pollen_species_class.get(pollen_type, "")
                species_el = day_div.find("p", class_=species_class) if species_class else None
                species_name = species_el.text.strip() if species_el else "Unknown"

                # Build details list (single species for US, unlike EU multi-species pipe list)
                pollen[f"{pollen_type}_details"] = [
                    {
                        "name": species_name,
                        "value": pollen[pollen_type],
                        "level": pollen_level,
                    }
                ] if species_name != "Unknown" else []

            self._pollen.append(pollen)

    def _extract_location_data(self, soup: BeautifulSoup) -> None:
        self._found_city = self._get_location_str("cityName", soup)
        self._found_latitude = self._get_location_float("pollenlat", soup)
        self._found_longitude = self._get_location_float("pollenlng", soup)

    def _get_location_str(self, key: str, soup: BeautifulSoup) -> str:
        result = soup.find("input", id=key)
        return result.get("value", "") if result else ""  # type: ignore

    def _get_location_float(self, key: str, soup: BeautifulSoup) -> float:
        result = soup.find("input", id=key)
        value = result.get("value", None) if result else None  # type: ignore
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _determine_pollen_date(self, day_no: int) -> date:
        year = datetime.today().year
        month = datetime.today().month
        try:
            dt = datetime(year=year, month=month, day=day_no)
            invalid_date = False
        except ValueError:
            dt = datetime.today()
            invalid_date = True
        if dt.date() < datetime.today().date() or invalid_date:
            month += 1
            if month > 12:
                year += 1
                month = 1
            dt = datetime(year=year, month=month, day=day_no)
        return dt.date()

    def determine_level_by_count(self, pollen_type: str, pollen_count: int) -> str:
        thresholds = {
            "trees": [95, 207, 703],
            "weeds": [20, 77, 266],
            "grass": [29, 60, 341],
        }
        categories = ["low", "moderate", "high", "very-high"]
        for i, threshold in enumerate(thresholds.get(pollen_type, [])):
            if pollen_count <= threshold:
                return categories[i]
        return "very-high"


class DNSError(HomeAssistantError):
    """DNS or connection error for Pollen API."""
