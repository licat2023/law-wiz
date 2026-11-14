#!/bin/sh
(
set -eu

: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}"
: "${KB_MYSQL_DATABASE:?KB_MYSQL_DATABASE is required}"
: "${KB_MYSQL_USER:?KB_MYSQL_USER is required}"
: "${KB_MYSQL_PASSWORD:?KB_MYSQL_PASSWORD is required}"

case "$KB_MYSQL_DATABASE$KB_MYSQL_USER" in
    *[!A-Za-z0-9_]*) echo 'KB database and user must contain only ASCII letters, digits and underscores' >&2; exit 1 ;;
esac
if [ "$KB_MYSQL_DATABASE" = "${MYSQL_DATABASE:-}" ] || [ "$KB_MYSQL_USER" = "${MYSQL_USER:-}" ] || [ "$KB_MYSQL_USER" = root ]; then
    echo 'Knowledge base requires a separate database and non-root user' >&2
    exit 1
fi
password_hex=$(printf '%s' "$KB_MYSQL_PASSWORD" | od -An -v -tx1 | tr -d ' \n')
# MySQL treats underscores as wildcards in database-level grants.
kb_grant_database=$(printf '%s' "$KB_MYSQL_DATABASE" | sed 's/_/\\_/g')
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --protocol=socket -uroot <<SQL
CREATE DATABASE IF NOT EXISTS \`$KB_MYSQL_DATABASE\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
SET @kb_password = CONVERT(0x$password_hex USING utf8mb4);
SET @kb_statement = CONCAT('CREATE USER IF NOT EXISTS ''$KB_MYSQL_USER''@''%'' IDENTIFIED BY ', QUOTE(@kb_password));
PREPARE kb_account FROM @kb_statement;
EXECUTE kb_account;
DEALLOCATE PREPARE kb_account;
SET @kb_statement = CONCAT('ALTER USER ''$KB_MYSQL_USER''@''%'' IDENTIFIED BY ', QUOTE(@kb_password));
PREPARE kb_account FROM @kb_statement;
EXECUTE kb_account;
DEALLOCATE PREPARE kb_account;
GRANT ALL PRIVILEGES ON \`$kb_grant_database\`.* TO '$KB_MYSQL_USER'@'%';
SQL
)
