PostgreSQL backup and restore

Files:
- scripts/backup_postgres.sh
- scripts/restore_postgres.sh

One-time setup on EC2:
1. Ensure PostgreSQL client tools are installed:
   sudo apt update && sudo apt install -y postgresql-client
2. Make scripts executable:
   chmod +x /home/ubuntu/ecommerce/scripts/backup_postgres.sh
   chmod +x /home/ubuntu/ecommerce/scripts/restore_postgres.sh

Manual backup:
- /home/ubuntu/ecommerce/scripts/backup_postgres.sh

Manual restore:
- /home/ubuntu/ecommerce/scripts/restore_postgres.sh /home/ubuntu/backups/postgres/your_backup.sql.gz

Suggested cron job (daily at 02:00):
- crontab -e
- Add this line:
  0 2 * * * /home/ubuntu/ecommerce/scripts/backup_postgres.sh >> /home/ubuntu/backups/postgres/backup.log 2>&1

Defaults:
- Backup directory: /home/ubuntu/backups/postgres
- Retention: 14 days

Optional overrides (environment variables):
- PROJECT_DIR
- ENV_FILE
- BACKUP_DIR
- RETENTION_DAYS

Restore drill recommendation:
- Run one restore test every month on a non-production database.
