# MySQL 9.7 with the schemas and accounts needed by a fresh Compose volume.
FROM mysql:9.7
COPY 10-business-schema.sql 20-knowledge-base.sh /docker-entrypoint-initdb.d/
