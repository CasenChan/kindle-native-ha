"""Per-Kindle backlight as an HA number entity, so automations can dim or brighten the panel."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .protocol import DOMAIN

SIGNAL_NEW_DEVICE = f"{DOMAIN}_new_device"


def signal_device_updated(device_id: str) -> str:
    return f"{DOMAIN}_device_updated_{device_id}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    manager = hass.data[DOMAIN]
    async_add_entities(KindleBacklight(manager, device_id) for device_id in manager.devices)

    @callback
    def add_device(device_id: str) -> None:
        async_add_entities([KindleBacklight(manager, device_id)])

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE, add_device))


class KindleBacklight(NumberEntity):
    """Shows the level the Kindle last reported; setting it queues a command the Kindle applies on its next refresh."""

    _attr_has_entity_name = True
    _attr_name = "背光"
    _attr_icon = "mdi:brightness-6"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_should_poll = False

    def __init__(self, manager, device_id: str):
        self.manager, self.device_id = manager, device_id
        self._attr_unique_id = f"{device_id}_backlight"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device_id)})

    @property
    def device(self) -> dict | None:
        return self.manager.devices.get(self.device_id)

    @property
    def available(self) -> bool:
        return self.device is not None

    @property
    def native_value(self) -> float | None:
        device = self.device or {}
        target = device.get("backlight_target")
        # Until the Kindle confirms, show the requested level so the slider does not jump back.
        return target["level"] if target else device.get("backlight")

    @property
    def extra_state_attributes(self) -> dict:
        device = self.device or {}
        return {"pending": device.get("backlight_target") is not None, "reported": device.get("backlight")}

    async def async_set_native_value(self, value: float) -> None:
        await self.manager.set_backlight(self.device_id, round(value))

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(
            self.hass, signal_device_updated(self.device_id), self.async_write_ha_state))
