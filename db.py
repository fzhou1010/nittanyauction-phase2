# Database helper functions
# Provides a shared SQLite connection per request and a convenience query function

import sqlite3 as sql
import os

DATABASE = os.path.join(os.path.dirname(__file__), 'nittanyauction.db')

HELPDESK_TEAM_EMAIL = 'helpdeskteam@lsu.edu'

def get_db():
    """Return a database connection for the current request.
    Reuses the same connection within a single request (stored on Flask's g object)."""
    from flask import g
    if 'db' not in g:
        g.db = sql.connect(DATABASE)
        g.db.row_factory = sql.Row           # Lets us access columns by name (row['email'])
        g.db.execute('PRAGMA foreign_keys = ON') # Enforce foreign key constraints
    return g.db

def close_db(e=None):
    """Close the database connection at the end of a request."""
    from flask import g
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Create all tables from schema.sql (used for initial setup)."""
    db = sql.connect(DATABASE)
    db.row_factory = sql.Row
    db.execute('PRAGMA foreign_keys = ON')
    with open(os.path.join(os.path.dirname(__file__), 'schema.sql')) as f:
        db.executescript(f.read())
    db.close()

def query_db(query, args=(), one=False):
    """Run a SELECT query and return results.
    If one=True, returns a single row (or None). Otherwise returns a list of rows."""
    db = get_db()
    cur = db.execute(query, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv
