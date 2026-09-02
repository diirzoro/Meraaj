#!/usr/bin/env bash
# Restore drill — TEST/PREVIEW ONLY. Never run against Live.
# 1) decrypt the encrypted archive  2) restore into a throwaway DB  3) verify counts
set -euo pipefail
FILE="${1:?usage: manual_restore_test.sh <backup-file-name>}"
source /app/backend/.env
[ "${ENVIRONMENT:-}" = "preview" ] || { echo "REFUSING: ENVIRONMENT is not preview"; exit 1; }
SRC="/app/backups/$FILE"
TMP="/tmp/restore-drill.archive.gz"
if [[ "$FILE" == *.enc ]]; then
  openssl enc -d -aes-256-cbc -pbkdf2 -in "$SRC" -out "$TMP" -pass "pass:$BACKUP_PASSPHRASE"
else
  cp "$SRC" "$TMP"
fi
DRILL_DB="${DB_NAME}_restore_drill"
mongorestore --uri="$MONGO_URL" --archive="$TMP" --gzip --drop \
  --nsFrom="${DB_NAME}.*" --nsTo="${DRILL_DB}.*"
python3 - <<EOF
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
async def m():
    c = AsyncIOMotorClient("$MONGO_URL")
    src, dst = c["$DB_NAME"], c["$DRILL_DB"]
    for coll in ("users", "bookings", "packages", "transactions"):
        print(coll, "source:", await src[coll].count_documents({}),
              "restored:", await dst[coll].count_documents({}))
    await c.drop_database("$DRILL_DB")
    print("drill database dropped — live data untouched")
asyncio.run(m())
EOF
rm -f "$TMP"
