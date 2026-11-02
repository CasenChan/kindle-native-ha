"""Set up the native Kindle control-panel integration."""
from homeassistant.config_entries import ConfigFlow

from .protocol import DOMAIN


class KindlePanelConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Kindle 控制面板", data={})
        return self.async_show_form(step_id="user")
