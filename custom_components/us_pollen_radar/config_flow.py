"""Config flow for US Pollen Radar integration."""

from __future__ import annotations
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_NAME, CONF_CITY
from .api import PollenApi, DNSError

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for US Pollen Radar."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}

        if user_input is not None:
            city = user_input[CONF_CITY]
            name = user_input[CONF_NAME]

            await self.async_set_unique_id(name)
            self._abort_if_unique_id_configured()

            try:
                session = async_get_clientsession(self.hass)
                api = PollenApi(session=session, city=city)
                data = await api.async_get_data()
                if not data or not data.get("pollen"):
                    raise InvalidCity
            except InvalidCity:
                errors["base"] = "invalid_city"
            except DNSError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during config flow")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=name, data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_CITY): str,
                vol.Required(
                    CONF_NAME,
                    default=self.hass.config.location_name,
                ): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )


class InvalidCity(HomeAssistantError):
    """Raised when no pollen data is returned for the given city."""
