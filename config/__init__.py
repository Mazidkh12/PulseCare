import pymysql
from django.db.backends.mysql.features import DatabaseFeatures
from django.db.utils import OperationalError

# Enable PyMySQL to act as the MySQLdb driver for Django's MySQL backend
pymysql.install_as_MySQLdb()

# Support MySQL 8.0+ servers (Django 6 defaults minimum_database_version to 8.4,
# while local development environments widely use MySQL 8.0.x Community Server)
def _safe_min_db_version(self):
    if self.connection.mysql_is_mariadb:
        return (10, 11)
    return (8, 0)


DatabaseFeatures.minimum_database_version = property(_safe_min_db_version)

# Fallback for DatabaseFeatures.has_native_uuid_field during offline checks
_orig_has_native_uuid = DatabaseFeatures.has_native_uuid_field.func


def _safe_has_native_uuid_field(self):
    try:
        return _orig_has_native_uuid(self)
    except (OperationalError, Exception):
        return False


DatabaseFeatures.has_native_uuid_field = property(_safe_has_native_uuid_field)
