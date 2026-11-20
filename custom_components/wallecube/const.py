"""Constants for the WalleCube integration."""

from datetime import timedelta

DOMAIN = "wallecube"

CONF_USERNAME = "username"
CONF_TOKEN = "token"
CONF_CODE = "code"
CONF_LOGIN_TYPE = "login_type"
CONF_USER_ID = "user_id"

SCAN_INTERVAL = timedelta(seconds=60)

# A unit is treated as unavailable when its latest report is older than this.
STALE_AFTER = timedelta(minutes=10)

# Device "status" value the cloud uses for an online unit.
STATUS_ONLINE = 2
