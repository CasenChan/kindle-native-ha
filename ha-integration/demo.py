"""Fictional entities and a multi-room layout for the offline preview. Never touches a live HA."""

MODES = ["off", "cool", "heat", "dry", "fan_only", "auto"]


def entity(entity_id, state, name, **attributes):
    return entity_id, {"entity_id": entity_id, "state": state, "attributes": {"friendly_name": name, **attributes}}


STATES = dict([
    entity("light.living_main", "on", "客厅主灯", brightness=153, supported_color_modes=["brightness"]),
    entity("light.living_strip", "on", "客厅灯带"),
    entity("switch.floor_lamp", "off", "落地灯"),
    entity("sensor.living_temperature", "25.84", "客厅温度", unit_of_measurement="°C", device_class="temperature"),
    entity("sensor.living_humidity", "58", "客厅湿度", unit_of_measurement="%", device_class="humidity"),
    entity("climate.bedroom", "cool", "卧室空调", temperature=24, current_temperature=26.3, min_temp=16, max_temp=30,
           target_temp_step=1, hvac_modes=MODES),
    entity("light.bedside", "on", "床头灯"),
    entity("fan.bedroom", "off", "卧室风扇"),
    entity("binary_sensor.front_door", "off", "入户门", device_class="door"),
    entity("lock.front_door", "locked", "门锁"),
    entity("scene.go_home", "2026-11-03T08:00:00", "回家模式"),
    entity("scene.good_night", "unknown", "晚安"),
    entity("climate.study", "off", "书房空调", temperature=22, current_temperature=19.6, min_temp=16, max_temp=30,
           target_temp_step=0.5, hvac_modes=["off", "heat", "cool", "auto"]),
    entity("light.study_desk", "off", "台灯"),
    entity("switch.monitor", "on", "显示器"),
    entity("cover.study_curtain", "unavailable", "书房窗帘"),
    entity("sensor.study_power", "86.4", "插座功率", unit_of_measurement="W", device_class="power"),
    entity("binary_sensor.study_motion", "off", "书房有人", device_class="motion"),
    entity("button.robot_dock", "unknown", "扫地机回充"),
    entity("sensor.robot_battery", "100", "扫地机电量", unit_of_measurement="%", device_class="battery"),
    entity("media_player.living_speaker", "playing", "客厅音箱", media_title="夜曲 · 周杰伦"),
    entity("cover.bedroom_curtain", "open", "卧室窗帘", current_position=60),
])

LAYOUT = {
    "refresh_seconds": 30, "power_mode": "external-refresh", "temperature_unit": "auto", "home_timeout": 3,
    "night_light": {"enabled": True, "start": "22:30", "end": "07:00", "level": 10},
    "pages": [
        {"id": "home", "title": "全屋", "columns": 4, "sections": [
            {"id": "living", "title": "客厅", "rows": 2, "tiles": [
                {"id": "t1", "entity_id": "light.living_main", "title": "客厅主灯", "icon": "bulb", "w": 2},
                {"id": "t2", "entity_id": "sensor.living_temperature", "title": "室温", "icon": "temperature", "h": 2},
                {"id": "t3", "entity_id": "sensor.living_humidity", "title": "湿度", "icon": "humidity", "h": 2},
                {"id": "t4", "entity_id": "light.living_strip", "title": "灯带", "icon": "bulb"},
                {"id": "t5", "entity_id": "switch.floor_lamp", "title": "落地灯", "icon": "plug"},
            ]},
            {"id": "bedroom", "title": "卧室", "rows": 2, "tiles": [
                {"id": "t6", "entity_id": "climate.bedroom", "title": "卧室空调", "icon": "thermostat", "w": 3, "h": 2},
                {"id": "t7", "entity_id": "light.bedside", "title": "床头灯", "icon": "bulb"},
                {"id": "t8", "entity_id": "fan.bedroom", "title": "风扇", "icon": "fan"},
            ]},
            {"id": "entry", "title": "门口", "rows": 1, "tiles": [
                {"id": "t9", "entity_id": "binary_sensor.front_door", "title": "入户门", "icon": "door", "w": 2},
                {"id": "t10", "entity_id": "lock.front_door", "title": "门锁", "icon": "lock", "w": 2,
                 "allow_unlock": True},
            ]},
        ]},
        {"id": "study", "title": "书房", "columns": 3, "sections": [
            {"id": "study-main", "title": "书房", "rows": 3, "tiles": [
                {"id": "t11", "entity_id": "climate.study", "title": "书房空调", "icon": "thermostat", "w": 3, "h": 2},
                {"id": "t12", "entity_id": "light.study_desk", "title": "台灯", "icon": "bulb"},
                {"id": "t13", "entity_id": "switch.monitor", "title": "显示器", "icon": "tv"},
                {"id": "t14", "entity_id": "cover.study_curtain", "title": "窗帘", "icon": "curtain"},
            ]},
            {"id": "study-status", "title": "状态", "rows": 2, "summary": False, "tiles": [
                {"id": "t15", "entity_id": "sensor.study_power", "title": "插座功率", "icon": "bolt"},
                {"id": "t16", "entity_id": "binary_sensor.study_motion", "title": "有人", "icon": "motion"},
                {"id": "t17", "entity_id": "sensor.robot_battery", "title": "扫地机", "icon": "battery"},
                {"id": "t18", "entity_id": "button.robot_dock", "title": "回充", "icon": "power", "w": 2},
                {"id": "t19", "entity_id": "scene.good_night", "title": "晚安", "icon": "scene"},
            ]},
        ]},
        {"id": "scenes", "title": "影音", "columns": 2, "sections": [
            {"id": "scene-list", "title": "", "rows": 3, "tiles": [
                {"id": "t20", "entity_id": "scene.go_home", "title": "回家模式", "icon": "scene"},
                {"id": "t21", "entity_id": "scene.good_night", "title": "晚安模式", "icon": "scene"},
                {"id": "t22", "entity_id": "media_player.living_speaker", "title": "客厅音箱", "icon": "music", "w": 2},
                {"id": "t23", "entity_id": "cover.bedroom_curtain", "title": "卧室窗帘", "icon": "curtain", "w": 2},
            ]},
        ]},
    ],
}
