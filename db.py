import sqlite3
import os

from utils import timestamp, hash_password, generate_invite_code

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
    
    # messages
    cursor.execute("CREATE TABLE IF NOT EXISTS messages (" \
                   "id INTEGER PRIMARY KEY AUTOINCREMENT, " \
                   "channel_id INTEGER NOT NULL, " \
                   "sender_id INTEGER NOT NULL, " \
                   "content TEXT NOT NULL, " \
                   "created INTEGER NOT NULL, " \
                   "deleted INTEGER DEFAULT 0)")
    
    connection.commit()
    connection.close()


def create_user(username, password):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (username.lower(),))
    if cursor.fetchone() is not None:
        connection.close()
        return False, "Username is already taken."
        
    password_hash, password_salt = hash_password(password)

    try:
        cursor.execute("INSERT INTO users (username, password_hash, password_salt, created) VALUES (?, ?, ?, ?)",
                       (username.lower(), password_hash, password_salt, timestamp()))
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
    connection.close()
    if row is None:
        return None
    
    return dict(row)


def get_user_by_id(user_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    connection.close()
    if row is None:
        return None
    
    return dict(row)


def create_session(user_id, token, expires):
    connection = connect_db()
    cursor = connection.cursor()
    
    try:
        cursor.execute("INSERT INTO sessions (user_id, token, created, expires) VALUES (?, ?, ?, ?)",
                       (user_id, token, timestamp(), expires))
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
    connection.close()
    if row is None:
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
    

def create_server(owner_id, name, icon, description=""):
    connection = connect_db()
    cursor = connection.cursor()

    invite_code = generate_invite_code()
    for i in range(5):
        cursor.execute("SELECT id FROM servers WHERE invite_code = ?", (invite_code,))
        if cursor.fetchone() is None:
            break

        invite_code = generate_invite_code()

    try:
        cursor.execute("INSERT INTO servers (name, description, owner_id, invite_code, icon, created) VALUES (?, ?, ?, ?, ?, ?)",
                       (name, description, owner_id, invite_code, icon, timestamp()))
        server_id = cursor.lastrowid

        cursor.execute("INSERT INTO server_members (server_id, user_id, joined) VALUES (?, ?, ?)",
                       (server_id, owner_id, timestamp()))
        
        cursor.execute("INSERT INTO channels (server_id, name, description, created) VALUES (?, ?, ?, ?)",
                       (server_id, "general", "General channel", timestamp()))
        
        connection.commit()
        connection.close()
        
        return True, server_id
    
    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"
    

def get_server_by_id(server_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM servers WHERE id = ?",
                   (server_id,))
    row = cursor.fetchone()
    connection.close()
    if row is None:
        return None
    
    return dict(row)


def get_server_by_invite_code(invite_code):
    print(f"Looking for server with invite code: '{invite_code}'")
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM servers WHERE invite_code = ? COLLATE NOCASE",
                   (invite_code,))
    row = cursor.fetchone()
    connection.close()
    if row is None:
        return None
    
    return dict(row)


def get_user_servers(user_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT servers.* FROM servers JOIN server_members ON server_members.server_id = servers.id WHERE server_members.user_id = ? ORDER BY server_members.joined ASC", (user_id,))
    results = []
    for row in cursor.fetchall():
        results.append(dict(row))
    connection.close()
    
    return results


def get_server_channels(server_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM channels WHERE server_id = ? ORDER BY created ASC",
                   (server_id,))

    results = []
    for row in cursor.fetchall():
        results.append(dict(row))
    connection.close()

    return results


def get_server_members(server_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT users.*, users.username, users.display_name FROM users JOIN server_members ON server_members.user_id = users.id WHERE server_members.server_id = ? ORDER BY server_members.joined ASC",
                   (server_id,))
    
    results = []
    for row in cursor.fetchall():
        results.append(dict(row))
    connection.close()

    return results


def create_channel(server_id, name, description=""):
    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("INSERT INTO channels (server_id, name, description, created) VALUES (?, ?, ?, ?)",
                       (server_id, name, description, timestamp()))
        channel_id = cursor.lastrowid
        connection.commit()
        connection.close()

        return True, channel_id
    
    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"


def get_channel_by_id(channel_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM channels WHERE id = ? ORDER BY created ASC",
                   (channel_id,))
    row = cursor.fetchone()
    connection.close()
    if row is None:
        return None

    return dict(row)


def join_server(user_id, server_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM server_members WHERE server_id = ? AND user_id = ?",
                   (server_id, user_id))
    
    if cursor.fetchone() is not None:
        connection.close()
        return False, "You are already a member of this server."
    
    try:
        cursor.execute("INSERT INTO server_members (server_id, user_id, joined) VALUES (?, ?, ?)",
                        (server_id, user_id, timestamp()))
        connection.commit()
        connection.close()

        return True, "Joined server"
    
    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"
