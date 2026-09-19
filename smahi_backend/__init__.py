# mysqlclient needs to compile against MySQL's C client library, which was
# failing to build/import cleanly on PythonAnywhere (ModuleNotFoundError:
# No module named 'MySQLdb') — PyMySQL is a pure-Python drop-in that always
# installs cleanly, at the cost of Django needing this standard shim to make
# its "MySQLdb" import resolve to it instead. No-op (never even imported)
# when DATABASE_URL isn't set to a mysql:// URL, e.g. local dev on SQLite —
# guarded so a fresh clone that hasn't run `pip install` yet still boots.
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass
