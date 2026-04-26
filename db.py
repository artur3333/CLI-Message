import sqlite3
import os
import json

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
                   "pronouns TEXT DEFAULT '', " \
                   "status TEXT DEFAULT '', " \
                   "name_color TEXT DEFAULT '', " \
                   "accent_color TEXT DEFAULT 'dark_blue', " \
                   "connections TEXT DEFAULT '[]', " \
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
                   "attachment_data BLOB DEFAULT NULL, " \
                   "attachment_name TEXT DEFAULT NULL, " \
                   "created INTEGER NOT NULL, " \
                   "deleted INTEGER DEFAULT 0)")
    
    # friends
    cursor.execute("CREATE TABLE IF NOT EXISTS friends (" \
                   "id INTEGER PRIMARY KEY AUTOINCREMENT, " \
                   "sender_id INTEGER NOT NULL, " \
                   "receiver_id INTEGER NOT NULL, " \
                   "status TEXT DEFAULT 'pending', " \
                   "created INTEGER NOT NULL," \
                   "UNIQUE(sender_id, receiver_id))")
    
    # dm messages
    cursor.execute("CREATE TABLE IF NOT EXISTS dm_messages (" \
                   "id INTEGER PRIMARY KEY AUTOINCREMENT, " \
                   "sender_id INTEGER NOT NULL, " \
                   "receiver_id INTEGER NOT NULL, " \
                   "content TEXT NOT NULL, " \
                   "attachment_data BLOB DEFAULT NULL, " \
                   "attachment_name TEXT DEFAULT NULL, " \
                   "created INTEGER NOT NULL, " \
                   "deleted INTEGER DEFAULT 0)")
    
    # channel_reads
    cursor.execute("CREATE TABLE IF NOT EXISTS channel_reads (" \
                   "user_id INTEGER NOT NULL, " \
                   "channel_id INTEGER NOT NULL, " \
                   "last_read_message_id INTEGER DEFAULT 0, " \
                   "PRIMARY KEY (user_id, channel_id))")
    
    # dm_reads
    cursor.execute("CREATE TABLE IF NOT EXISTS dm_reads (" \
                   "user_1 INTEGER NOT NULL, " \
                   "user_2 INTEGER NOT NULL, " \
                   "user_id INTEGER NOT NULL, " \
                   "last_read_message_id INTEGER DEFAULT 0, " \
                   "PRIMARY KEY (user_1, user_2, user_id))")
    
    # user notes
    cursor.execute("CREATE TABLE IF NOT EXISTS user_notes (" \
                   "by_id INTEGER NOT NULL, " \
                   "target_id INTEGER NOT NULL, " \
                   "content TEXT NOT NULL, " \
                   "created INTEGER NOT NULL, " \
                   "PRIMARY KEY (by_id, target_id))")
    
    # settings
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (" \
                   "user_id INTEGER PRIMARY KEY, " \
                   "dm_notifications INTEGER DEFAULT 1, " \
                   "mention_notifications INTEGER DEFAULT 1, " \
                   "compact_mode INTEGER DEFAULT 0)")
    
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
    

def change_user_password(user_id, new_password):
    password_hash, password_salt = hash_password(new_password)

    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?",
                       (password_hash, password_salt, user_id))
        connection.commit()
        connection.close()

        return True
    
    except Exception as e:
        connection.close()
        return False
    

def delete_user(user_id):
    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("DELETE FROM users WHERE id = ?",
                       (user_id,))
        connection.commit()
        connection.close()

        return True

    except Exception as e:
        connection.close()
        return False
    
def delete_user_sessions(user_id):
    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("DELETE FROM sessions WHERE user_id = ?",
                       (user_id,))
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
    

def update_profile(user_id, display_name="", bio="", pronouns="", status="", name_color="", accent_color="dark_blue", connections=None):
    if len(display_name) > 32:
        return False, "Display name cannot be longer than 32 characters."
    if len(bio) > 256:
        return False, "Bio cannot be longer than 256 characters."
    if len(pronouns) > 32:
        return False, "Pronouns cannot be longer than 32 characters."
    if len(status) > 128:
        return False, "Status cannot be longer than 128 characters."
    
    if name_color and name_color not in ["white", "cyan", "green", "yellow", "magenta", "red", "blue", "bright_cyan", "bright_green", "bright_yellow", "bright_magenta", "bright_red"]:
        return False, "Invalid name color."
    
    if accent_color and accent_color not in ["dark_blue", "dark_green", "dark_red", "dark_magenta", "dark_cyan"]:
        return False, "Invalid accent color."
    
    if connections is None:
        connections = []

    connections = connections[:10]
    connections_json = json.dumps(connections)

    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("UPDATE users SET display_name = ?, bio = ?, pronouns = ?, status = ?, name_color = ?, accent_color = ?, connections = ? WHERE id = ?",
                       (display_name, bio, pronouns, status, name_color, accent_color, connections_json, user_id))
        connection.commit()
        connection.close()

        return True, "Profile updated successfully."

    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"


def set_user_note(by_id, target_id, content):
    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("INSERT INTO user_notes (by_id, target_id, content, created) VALUES (?, ?, ?, ?) ON CONFLICT(by_id, target_id) DO UPDATE SET content = excluded.content, created = excluded.created",
                       (by_id, target_id, content, timestamp()))
        connection.commit()
        connection.close()

        return True, "Note saved successfully."
    
    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"
    

def get_user_note(by_id, target_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT content FROM user_notes WHERE by_id = ? AND target_id = ?",
                   (by_id, target_id))
    row = cursor.fetchone()
    connection.close()

    if row is None:
        return ""
    return row["content"]
    

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
    

def send_message(channel_id, sender_id, content, attachment_data=None, attachment_name=None):
    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("INSERT INTO messages (channel_id, sender_id, content, attachment_data, attachment_name, created) VALUES (?, ?, ?, ?, ?, ?)",
                       (channel_id, sender_id, content, attachment_data, attachment_name, timestamp()))
        message_id = cursor.lastrowid
        connection.commit()
        connection.close()

        return True, message_id
    
    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"
    

def get_channel_messages(channel_id, limit=100):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT messages.*, users.username, users.display_name, users.name_color FROM messages JOIN users ON messages.sender_id = users.id WHERE messages.channel_id = ? AND messages.deleted = 0 ORDER BY messages.created DESC LIMIT ?",
                   (channel_id, limit))
    
    results = []
    for row in cursor.fetchall():
        results.append(dict(row))
    connection.close()

    results.reverse()

    return results


def get_messages_after(channel_id, last_id):
    connection = connect_db()
    cursor = connection.cursor()
    
    cursor.execute("SELECT messages.*, users.username, users.display_name, users.name_color FROM messages JOIN users ON messages.sender_id = users.id WHERE messages.channel_id = ? AND messages.id > ? AND messages.deleted = 0 ORDER BY messages.created ASC",
                    (channel_id, last_id))
    
    results = []
    for row in cursor.fetchall():
        results.append(dict(row))
    connection.close()

    return results


def search_messages(channel_id, query, limit=20, offset=0):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT messages.*, users.username, users.display_name, users.name_color FROM messages JOIN users ON messages.sender_id = users.id WHERE messages.channel_id = ? AND messages.content LIKE ? AND messages.deleted = 0 ORDER BY messages.created DESC LIMIT ? OFFSET ?",
                   (channel_id, f"%{query}%", limit, offset))
    
    results = []
    for row in cursor.fetchall():
        results.append(dict(row))
    connection.close()

    results.reverse()
    return results


def search_dm_messages(user_id1, user_id2, query, limit=20, offset=0):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT dm_messages.*, users.username, users.display_name, users.name_color FROM dm_messages JOIN users ON dm_messages.sender_id = users.id WHERE ((dm_messages.sender_id = ? AND dm_messages.receiver_id = ?) OR (dm_messages.sender_id = ? AND dm_messages.receiver_id = ?)) AND dm_messages.content LIKE ? AND dm_messages.deleted = 0 ORDER BY dm_messages.created DESC LIMIT ? OFFSET ?",
                   (user_id1, user_id2, user_id2, user_id1, f"%{query}%", limit, offset))
    
    results = []
    for row in cursor.fetchall():
        results.append(dict(row))
    connection.close()

    results.reverse()
    return results


def send_friend_request(sender_id, receiver_id):
    connection = connect_db()
    cursor = connection.cursor()

    if sender_id == receiver_id:
        connection.close()
        return False, "You cannot send a friend request to yourself."
    
    cursor.execute("SELECT * FROM friends WHERE status = 'accepted' AND ((sender_id =? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))",
                   (sender_id, receiver_id, receiver_id, sender_id))
    
    if cursor.fetchone() is not None:
        connection.close()
        return False, "You are already friends with this user."
    
    cursor.execute("SELECT * FROM friends WHERE status = 'pending' AND ((sender_id =? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))",
                   (sender_id, receiver_id, receiver_id, sender_id))
    
    if cursor.fetchone() is not None:
        connection.close()
        return False, "A friend request is already pending with this user."
    
    try:
        cursor.execute("INSERT INTO friends (sender_id, receiver_id, status, created) VALUES (?, ?, ?, ?)",
                       (sender_id, receiver_id, "pending", timestamp()))
        connection.commit()
        connection.close()

        return True, "Friend request sent."
    
    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"
    

def remove_friend(user_id1, user_id2):
    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("DELETE FROM friends WHERE status = 'accepted' AND ((sender_id =? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))",
                       (user_id1, user_id2, user_id2, user_id1))
        connection.commit()
        connection.close()

        return True, "Friend removed."
    
    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"
    

def accept_friend_request(request_id): #or sender_id / receiver_id
    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("UPDATE friends SET status = 'accepted' WHERE id = ?",
                       (request_id,))
        connection.commit()
        connection.close()

        return True, "Friend request accepted."
    
    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"
    

def decline_friend_request(request_id):
    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("DELETE FROM friends WHERE id = ?",
                       (request_id,))
        connection.commit()
        connection.close()

        return True, "Friend request declined."
    
    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"
    

def get_pending_friend_requests(user_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT friends.*, users.username, users.display_name, users.name_color FROM friends JOIN users ON friends.sender_id = users.id WHERE friends.receiver_id = ? AND friends.status = 'pending' ORDER BY friends.created ASC",
                   (user_id,))
    
    results = []
    for row in cursor.fetchall():
        results.append(dict(row))
    connection.close()

    return results


def are_friends(user_id1, user_id2):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM friends WHERE status = 'accepted' AND ((sender_id =? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))",
                   (user_id1, user_id2, user_id2, user_id1))
    
    result = cursor.fetchone() is not None
    connection.close()

    return result


def is_friend_request_pending(user_id1, user_id2):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM friends WHERE status = 'pending' AND ((sender_id =? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))",
                   (user_id1, user_id2, user_id2, user_id1))
    
    result = cursor.fetchone() is not None
    connection.close()

    return result


def get_friends(user_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT users.* FROM users JOIN friends ON ((friends.sender_id = users.id AND friends.receiver_id = ?) OR (friends.receiver_id = users.id AND friends.sender_id = ?)) WHERE friends.status = 'accepted' AND users.id != ? ORDER BY users.username ASC",
                   (user_id, user_id, user_id))
    
    results = []
    for row in cursor.fetchall():
        results.append(dict(row))
    connection.close()

    return results


def send_dm(sender_id, receiver_id, content, attachment_data=None, attachment_name=None):
    connection = connect_db()
    cursor = connection.cursor()

    try:
        cursor.execute("INSERT INTO dm_messages (sender_id, receiver_id, content, attachment_data, attachment_name, created) VALUES (?, ?, ?, ?, ?, ?)",
                       (sender_id, receiver_id, content, attachment_data, attachment_name, timestamp()))
        
        message_id = cursor.lastrowid
        connection.commit()
        connection.close()

        return True, message_id
    
    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"
    

def get_dm_messages(user_id1, user_id2, limit=100):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT dm_messages.*, users.username, users.display_name, users.name_color FROM dm_messages JOIN users ON dm_messages.sender_id = users.id WHERE ((dm_messages.sender_id = ? AND dm_messages.receiver_id = ?) OR (dm_messages.sender_id = ? AND dm_messages.receiver_id = ?)) AND dm_messages.deleted = 0 ORDER BY dm_messages.created DESC LIMIT ?",
                   (user_id1, user_id2, user_id2, user_id1, limit))
    
    results = []
    for row in cursor.fetchall():
        results.append(dict(row))
    connection.close()

    results.reverse()

    return results

def get_dm_messages_after(user_id1, user_id2, last_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT dm_messages.*, users.username, users.display_name, users.name_color FROM dm_messages JOIN users ON dm_messages.sender_id = users.id WHERE ((dm_messages.sender_id = ? AND dm_messages.receiver_id = ?) OR (dm_messages.sender_id = ? AND dm_messages.receiver_id = ?)) AND dm_messages.id > ? AND dm_messages.deleted = 0 ORDER BY dm_messages.created ASC",
                   (user_id1, user_id2, user_id2, user_id1, last_id))
    
    results = []
    for row in cursor.fetchall():
        results.append(dict(row))
    connection.close()

    return results


def mark_channel_read(user_id, channel_id, last_id):
    connection = connect_db()
    cursor = connection.cursor()

    if last_id == 0:
        connection.close()
        return True, ""

    cursor.execute("SELECT * FROM channel_reads WHERE user_id = ? AND channel_id = ?",
                     (user_id, channel_id))
    if cursor.fetchone() is None:
        try:
            cursor.execute("INSERT INTO channel_reads (user_id, channel_id, last_read_message_id) VALUES (?, ?, ?)",
                           (user_id, channel_id, last_id))
            connection.commit()
            connection.close()

            return True, ""
    
        except Exception as e:
            connection.close()
            return False, f"Error: {str(e)}"

    else:
        try:
            cursor.execute("UPDATE channel_reads SET last_read_message_id = ? WHERE user_id = ? AND channel_id = ?",
                           (last_id, user_id, channel_id))
            connection.commit()
            connection.close()

            return True, ""
        
        except Exception as e:
            connection.close()
            return False, f"Error: {str(e)}"
    

def get_channel_unread_count(user_id, channel_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT last_read_message_id FROM channel_reads WHERE user_id = ? AND channel_id=?",
                   (user_id, channel_id))
    
    row = cursor.fetchone()
    if row:
        last_read_id = row["last_read_message_id"]
    else:
        last_read_id = 0

    cursor.execute("SELECT COUNT(*) FROM messages WHERE channel_id = ? AND id > ? AND deleted = 0 AND sender_id != ?",
                   (channel_id, last_read_id, user_id))
    count = cursor.fetchone()[0]
    connection.close()

    return count


def get_server_unread_count(user_id, server_id):
    connection = connect_db()
    cursor = connection.cursor()

    if not cursor.execute("SELECT * FROM server_members WHERE server_id = ? AND user_id = ?",
                          (server_id, user_id)).fetchone():
        connection.close()
        return 0

    cursor.execute("SELECT id FROM channels WHERE server_id = ?",
                   (server_id,))
    
    channel_ids = []
    for row in cursor.fetchall():
        channel_ids.append(row["id"])
    
    connection.close()

    total_count = 0
    for channel_id in channel_ids:
        total_count = total_count + get_channel_unread_count(user_id, channel_id)
    
    return total_count


def get_all_server_unreads(user_id):
    servers = get_user_servers(user_id)

    result = {}
    for server in servers:
        result[server["id"]] = get_server_unread_count(user_id, server["id"])

    return result


def mark_dm_read(user_id1, user_id2, last_id):
    connection = connect_db()
    cursor = connection.cursor()

    if last_id == 0:
        connection.close()
        return True, ""
    
    user_1 = min(user_id1, user_id2)
    user_2 = max(user_id1, user_id2)

    cursor.execute("SELECT * FROM dm_reads WHERE user_1 =? AND user_2 = ? AND user_id = ?",
                   (user_1, user_2, user_id1))
    if cursor.fetchone() is None:
        try:
            cursor.execute("INSERT INTO dm_reads (user_1, user_2, user_id, last_read_message_id) VALUES (?, ?, ?, ?)",
                           (user_1, user_2, user_id1, last_id))
            connection.commit()
            connection.close()

            return True, ""
    
        except Exception as e:
            connection.close()
            return False, f"Error: {str(e)}"
    
    else:
        try:
            cursor.execute("UPDATE dm_reads SET last_read_message_id = ? WHERE user_1 = ? AND user_2 = ? AND user_id = ?",
                           (last_id, user_1, user_2, user_id1))
            connection.commit()
            connection.close()

            return True, ""
        
        except Exception as e:
            connection.close()
            return False, f"Error: {str(e)}"
        

def get_dm_unread_count(user_id1, user_id2):
    connection = connect_db()
    cursor = connection.cursor()

    user_1 = min(user_id1, user_id2)
    user_2 = max(user_id1, user_id2)

    cursor.execute("SELECT last_read_message_id FROM dm_reads WHERE user_1 =? AND user_2 = ? AND user_id = ?",
                   (user_1, user_2, user_id1))
    
    row = cursor.fetchone()
    if row:
        last_read_id = row["last_read_message_id"]
    else:
        last_read_id = 0

    cursor.execute("SELECT COUNT(*) FROM dm_messages WHERE ((sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)) AND id > ? AND deleted = 0 AND sender_id != ?",
                   (user_id1, user_id2, user_id2, user_id1, last_read_id, user_id1))
    
    count = cursor.fetchone()[0]
    connection.close()

    return count


def get_all_dm_unreads(user_id):
    friends = get_friends(user_id)

    result = {}
    for friend in friends:
        result[friend["id"]] = get_dm_unread_count(user_id, friend["id"])

    return result


def get_user_settings(user_id):
    connection = connect_db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM settings WHERE user_id = ?",
                   (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute("INSERT INTO settings (user_id) VALUES (?)",
                       (user_id,))
        connection.commit()

        cursor.execute("SELECT * FROM settings WHERE user_id = ?",
                       (user_id,))
        row = cursor.fetchone()

    connection.close()

    return dict(row)


def update_settings(user_id, setting, value):
    connection = connect_db()
    cursor = connection.cursor()

    allowed_settings = ["dm_notifications", "mention_notifications", "compact_mode"]
    if setting not in allowed_settings:
        connection.close()
        return False, "Invalid setting."
    
    get_user_settings(user_id)

    try:
        cursor.execute(f"UPDATE settings SET {setting} = ? WHERE user_id = ?",
                       (value, user_id))
        connection.commit()
        connection.close()

        return True, f"{setting} updated successfully."
    
    except Exception as e:
        connection.close()
        return False, f"Error: {str(e)}"
