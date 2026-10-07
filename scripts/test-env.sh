#!/bin/sh
# usage: source scripts/test-env.sh
# Exports MONGO_TEST_URL for the MongoDB integration tests, built from the shared
# local infra credentials in ~/infra/mongodb/.env. The .env file is parsed as
# KEY=VALUE data, never run as shell code, and only MONGO_TEST_URL is exported.

_mongo_env_file="$HOME/infra/mongodb/.env"
if [ ! -r "$_mongo_env_file" ]; then
    echo "test-env.sh: $_mongo_env_file not found; bring up the MongoDB stack in ~/infra first" >&2
    unset _mongo_env_file
    return 1 2>/dev/null || exit 1
fi

if _mongo_test_url="$(python3 -I - "$_mongo_env_file" <<'PY'
import sys
from pathlib import Path
from urllib.parse import quote

values = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    key, sep, value = line.partition("=")
    if not sep:
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    values[key.strip()] = value

names = ("BIND_IP", "MONGO_ROOT_USER", "MONGO_ROOT_PASSWORD")
missing = [name for name in names if not values.get(name)]
if missing:
    sys.exit("test-env.sh: missing in the infra .env: " + ", ".join(missing))
user = quote(values["MONGO_ROOT_USER"], safe="")
password = quote(values["MONGO_ROOT_PASSWORD"], safe="")
host = values["BIND_IP"]
print(f"mongodb://{user}:{password}@{host}:27017/?authSource=admin&directConnection=true")
PY
)"; then
    export MONGO_TEST_URL="$_mongo_test_url"
    unset _mongo_env_file _mongo_test_url
else
    unset _mongo_env_file _mongo_test_url
    return 1 2>/dev/null || exit 1
fi
