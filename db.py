import sqlite3

from utils import timestamp, hash_password

PATH = "cli_message.db"


def connect_db():
    db_connection = sqlite3.connect(PATH)
    db_connection.row_factory = sqlite3.Row

    return db_connection


def close_db(db_connection):
    db_connection.close()


def init_db():
    connection = connect_db()
    cursor = connection.cursor()

    # users
    cursor.execute("CREATE TABLE IF NOT EXISTS users (" \
                   "id INTEGER PRIMARY KEY AUTOINCREMENT, " \
                   "username TEXT UNIQUE NOT NULL, " \
                   "password_hash TEXT NOT NULL, " \
                   "password_salt TEXT NOT NULL, " \
                   "display_name TEXT DEFAULT '', " \
                   "bio TEXT DEFAULT '', " \
                   "is_banned INTEGER DEFAULT 0, " \
                   "ban_reason TEXT DEFAULT '', " \
                   "login_attempts INTEGER DEFAULT 0, " \
                   "locked_until INTEGER DEFAULT 0, " \
                   "created INTEGER NOT NULL)")
    
    # sessions
    cursor.execute("CREATE TABLE IF NOT EXISTS sessions (" \
                    "id INTEGER PRIMARY KEY AUTOINCREMENT," \
                    "user_id INTEGER NOT NULL," \
                    "token TEXT UNIQUE NOT NULL," \
                    "created INTEGER NOT NULL," \
                    "expires INTEGER NOT NULL," \
                    "FOREIGN KEY (user_id) REFERENCES users(id))" )
    
    # servers
    cursor.execute("CREATE TABLE IF NOT EXISTS servers (" \
                   "id INTEGER PRIMARY KEY AUTOINCREMENT, " \
                   "name TEXT NOT NULL, " \
                   "description TEXT DEFAULT '', " \
                   "owner_id INTEGER NOT NULL, " \
                   "invite_code TEXT UNIQUE NOT NULL, " \
                   "icon TEXT DEFAULT '', " \
                   "created INTEGER NOT NULL)")
    
    # channels
    cursor.execute("CREATE TABLE IF NOT EXISTS channels (" \
                   "id INTEGER PRIMARY KEY AUTOINCREMENT, " \
                   "server_id INTEGER NOT NULL, " \
                   "name TEXT NOT NULL, " \
                   "description TEXT DEFAULT '', " \
                   "created INTEGER NOT NULL)")
    
    # server_members
    cursor.execute("CREATE TABLE IF NOT EXISTS server_members (" \
                   "server_id INTEGER NOT NULL, " \
                   "user_id INTEGER NOT NULL, " \
                   "joined INTEGER NOT NULL, " \
                   "PRIMARY KEY (server_id, user_id))")
    
    connection.commit()
    connection.close()


def create_user(username, password):
    connection = connect_db()
    cursor = connection.cursor()

    now_timestamp = timestamp()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username.lower(),))
    if cursor.fetchone() is not None:
        connection.close()
        return False, "Username is already taken."
        
    password_hash, password_salt = hash_password(password)

    try:
        cursor.execute("INSERT INTO users (username, password_hash, password_salt, created) VALUES (?, ?, ?, ?)",
                       (username.lower(), password_hash, password_salt, now_timestamp))
        connection.commit()
        connection.close()

        return True, "User created successfully."
    
    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"
    

def get_user_by_username(username):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM users WHERE username = ?", (username.lower(),))
    row = cursor.fetchone()
    if row is None:
        connection.close()
        return None
    
    return dict(row)


def create_session(user_id, token, expires):
    connection = connect_db()
    cursor = connection.cursor()

    now_timestamp = timestamp()
    
    try:
        cursor.execute("INSERT INTO sessions (user_id, token, created, expires) VALUES (?, ?, ?, ?)",
                       (user_id, token, now_timestamp, expires))
        connection.commit()
        connection.close()

        return True
    
    except Exception as e:
        connection.close()
        return False
    

def get_session(token):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM sessions WHERE token = ?", (token,))
    row = cursor.fetchone()
    if row is None:
        connection.close()
        return None
    
    return dict(row)


def delete_session(token):
    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
        connection.commit()
        connection.close()

        return True
    
    except Exception as e:
        connection.close()
        return False
    

def update_user(user_id, **kwargs):
    connection = connect_db()
    cursor = connection.cursor()

    updates = []
    values = []

    for field, value in kwargs.items():
        updates.append(f"{field} = ?")
        values.append(value)

    if not updates:
        connection.close()
        return False
    
    values.append(user_id)
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"

    try:
        cursor.execute(query, values)
        connection.commit()
        connection.close()
        return True
    
    except Exception as e:
        connection.close()
        return False
