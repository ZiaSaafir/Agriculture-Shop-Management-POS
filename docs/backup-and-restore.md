# Backup and restore

Backup and restore are not implemented in Stage 2. Before the system is used
with real shop data, the project must provide a tested PostgreSQL backup and
restore procedure, a retention policy, and an off-device backup option.

Do not treat the existence of a backup file as proof that recovery will work.
