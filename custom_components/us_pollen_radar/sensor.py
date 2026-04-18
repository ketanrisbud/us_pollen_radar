"""Sensor platform for US Pollen Radar."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorEntityDescription,
)

from .coordinator import PollenDataUpdateCoordinator
from .const import DOMAIN, NAME, MODEL, MANUFACTURER, CONF_NAME

_LOGGER = logging.getLogger(__package__)


@dataclass(kw_only=True, frozen=True)
class PollenDetailSensorEntityDescription(SensorEntityDescription):
    """Describes a per-species detail sensor."""
    group: str | None = None
    pollen_type: str | None = None


def get_sensor_descriptions() -> list[SensorEntityDescription]:
    level_options = ["low", "moderate", "high", "very-high"]
    return [
        # PPM count sensors
        *[
            SensorEntityDescription(
                key=key,
                translation_key=key,
                icon=icon,
                state_class="measurement",
                native_unit_of_measurement="ppm",
            )
            for key, icon in [
                ("trees", "mdi:tree-outline"),
                ("grass", "mdi:grass"),
                ("weeds", "mdi:flower-pollen"),
            ]
        ],
        # Level enum sensors
        *[
            SensorEntityDescription(
                key=key,
                translation_key=key,
                device_class=SensorDeviceClass.ENUM,
                options=level_options,
            )
            for key in ["trees_level", "grass_level", "weeds_level"]
        ],
        # Diagnostics
        SensorEntityDescription(
            key="date",
            translation_key="date",
            icon="mdi:calendar",
            device_class=SensorDeviceClass.DATE,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        SensorEntityDescription(
            key="last_updated",
            translation_key="last_updated",
            icon="mdi:clock-outline",
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        SensorEntityDescription(
            key="city",
            translation_key="city",
            icon="mdi:city",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        SensorEntityDescription(
            key="latitude",
            translation_key="latitude",
            icon="mdi:latitude",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        SensorEntityDescription(
            key="longitude",
            translation_key="longitude",
            icon="mdi:longitude",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        SensorEntityDescription(
            key="error",
            translation_key="error",
            icon="mdi:alert-circle-outline",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
    ]


def get_detail_sensor_descriptions(
    pollen: list[dict[str, Any]],
) -> list[PollenDetailSensorEntityDescription]:
    """Create per-species detail sensor descriptions from today's pollen data."""
    descriptions: list[PollenDetailSensorEntityDescription] = []
    if not pollen:
        return descriptions

    current = pollen[0]
    level_options = ["low", "moderate", "high", "very-high"]

    for group, icon in [
        ("trees_details", "mdi:tree-outline"),
        ("grass_details", "mdi:grass"),
        ("weeds_details", "mdi:flower-pollen"),
    ]:
        for detail in current.get(group, []):
            species_name = detail.get("name", "Unknown")
            # PPM value sensor
            descriptions.append(
                PollenDetailSensorEntityDescription(
                    key="value",
                    pollen_type=species_name,
                    translation_key="detail_value",
                    translation_placeholders={"name": species_name},
                    group=group,
                    icon=icon,
                    state_class="measurement",
                    native_unit_of_measurement="ppm",
                    entity_registry_enabled_default=True,  # enabled by default for US
                )
            )
            # Level enum sensor
            descriptions.append(
                PollenDetailSensorEntityDescription(
                    key="level",
                    pollen_type=species_name,
                    translation_key="detail_level",
                    translation_placeholders={"name": species_name},
                    group=group,
                    device_class=SensorDeviceClass.ENUM,
                    options=level_options,
                    entity_registry_enabled_default=True,
                )
            )

    return descriptions


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PollenDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    pollen = coordinator.data.get("pollen", {})
    name = config_entry.data.get(CONF_NAME)

    device_info = DeviceInfo(
        entry_type=DeviceEntryType.SERVICE,
        identifiers={(DOMAIN, f"{name}")},
        name=f"{NAME} ({name})",
        model=MODEL,
        manufacturer=MANUFACTURER,
    )

    entities: list[SensorEntity] = [
        PollenSensor(
            coordinator=coordinator,
            entry_id=config_entry.entry_id,
            description=desc,
            config_entry=config_entry,
            device_info=device_info,
        )
        for desc in get_sensor_descriptions()
    ]

    if pollen:
        entities += [
            PollenDetailSensor(
                coordinator=coordinator,
                entry_id=config_entry.entry_id,
                description=desc,
                config_entry=config_entry,
                device_info=device_info,
            )
            for desc in get_detail_sensor_descriptions(pollen)
        ]

    async_add_entities(entities)


class PollenSensor(CoordinatorEntity[PollenDataUpdateCoordinator], SensorEntity):
    """Main pollen sensor (trees/grass/weeds PPM + level)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id, description, config_entry, device_info):
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_unique_id = f"{entry_id}-{NAME}-{description.key}"
        self._attr_device_info = device_info
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        key = self.entity_description.key
        pollen = self.coordinator.data.get("pollen", {})
        current = pollen[0] if pollen else {}
        value = current.get(key)
        if value is not None:
            return value
        value = self.coordinator.data.get(key)
        if value is not None:
            return value
        return self._config_entry.data.get(key)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        key = self.entity_description.key
        if key not in {"trees", "grass", "weeds"}:
            return None

        pollen = self.coordinator.data.get("pollen", {})
        if not pollen:
            return None

        current = pollen[0]
        data: dict[str, Any] = {
            "level": current.get(f"{key}_level"),
            "species": (current.get(f"{key}_details") or [{}])[0].get("name"),
            "details": current.get(f"{key}_details"),
        }

        mapping = {
            key: "value",
            f"{key}_level": "level",
            f"{key}_details": "details",
        }

        data["forecast"] = [
            {
                mapping.get(dk, dk): day.get(dk)
                for dk in ["date", key, f"{key}_level", f"{key}_details"]
            }
            for day in pollen[1:]
        ]
        return data


class PollenDetailSensor(CoordinatorEntity[PollenDataUpdateCoordinator], SensorEntity):
    """Per-species detail sensor (e.g. Oak PPM, Oak Level)."""

    _attr_has_entity_name = True
    entity_description: PollenDetailSensorEntityDescription

    def __init__(self, coordinator, entry_id, description, config_entry, device_info):
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_unique_id = (
            f"{entry_id}-{NAME}-{description.group}"
            f"-{description.pollen_type}-{description.key}"
        )
        self._attr_device_info = device_info
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        pollen = self.coordinator.data.get("pollen", {})
        if not pollen:
            return None
        return self._get_detail_value(pollen, 0)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        pollen = self.coordinator.data.get("pollen", {})
        if not pollen:
            return None
        key = self.entity_description.key
        return {
            "forecast": [
                {"date": pollen[i]["date"], key: self._get_detail_value(pollen, i)}
                for i in range(1, len(pollen))
            ]
        }

    def _get_detail_value(self, pollen: list, day_offset: int) -> Any:
        group = self.entity_description.group
        pollen_type = self.entity_description.pollen_type
        key = self.entity_description.key
        details = pollen[day_offset].get(group, []) if group else []
        detail = next((d for d in details if d["name"] == pollen_type), None)
        return detail.get(key) if detail else None
