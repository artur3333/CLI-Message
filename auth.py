import os

import db
from utils import validate_username, validate_password, timestamp, verify_password, generate_token


# SESSION_FILE = os.path.join(os.path.expanduser("~"), ".cli_message_session")

current_user = None
current_token = None

# def save_session_token(token):
#     try:
#         with open(SESSION_FILE, "w", encoding="utf-8") as file:
#             file.write(token)

#     except OSError as e:
#         pass


# def load_session_token():
#     try:
#         with open(SESSION_FILE, "r", encoding="utf-8") as file:
#             token = file.read().strip()
#             return token
        
#     except OSError:
#         return None
    

# def clear_session_token():
#     try:
#         if os.path.exists(SESSION_FILE):
#             os.remove(SESSION_FILE)

#     except OSError:
#         pass

def clear_session_state():
    global current_user, current_token
    current_user = None
    current_token = None


def get_current_user():
    global current_user
    return current_user

def is_logged():
    return current_user is not None


def register(username, password):
    valid, error = validate_username(username)
    if not valid:
        return False, error
    
    valid, error = validate_password(password)
    if not valid:
        return False, error
    
    success, result = db.create_user(username, password)

    if success:
        return True, result
    else:
        return False, result
    

def login(username, password):
    global current_user, current_token
    user = db.get_user_by_username(username)
    if user is None:
        return False, "User not found."
    
    if user.get("is_banned") == 1:
        reason = user.get("ban_reason")
        return False, f"Your account has been banned. Reason: {reason}"
    
    time = timestamp()
    if user["locked_until"] > time:
        remain = (user["locked_until"] - time) // 60
        return False, f"Your account is locked. Please try again in {remain} minutes."
    
    if verify_password(password, user['password_hash'], user['password_salt']):
        if current_token:
            db.delete_session(current_token)

        db.delete_expired_sessions()

        token = generate_token()
        expires = time + 86400

        db.create_session(user['id'], token, expires)
        db.update_user(user['id'], login_attempts=0)

        current_user = db.get_user_by_id(user["id"])
        current_token = token
        # save_session_token(token)

        return True, f"Welcome back, @{username}!"
    
    else:
        attempts = user["login_attempts"] + 1

        if attempts >= 5:
            lock_duration = time + 15 * 60 # 15 minutes
            db.update_user(user["id"], login_attempts=0, locked_until=lock_duration)

            return False, "Too many failed login attempts. Your account has been locked for 15 minutes."
        
        else:
            db.update_user(user["id"], login_attempts=attempts)
            remaining_attempts = 5 - attempts

            return False, f"Incorrect password. You have {remaining_attempts} more attempt(s)."
        

def logout():
    global current_user, current_token
    
    if current_token:
        db.delete_session(current_token)

    # clear_session_token()
    current_user = None
    current_token = None

    return True, "You have been logged out."


def delete_account(password):
    global current_user

    if not is_logged():
        return False, "No user is currently logged in."
    
    if not verify_password(password, current_user["password_hash"], current_user["password_salt"]):
        return False, "Incorrect password. Account deletion aborted."

    db.delete_user_sessions(current_user["id"])
    db.delete_user(current_user["id"])

    # clear_session_token()
    clear_session_state()

    return True, "Your account has been deleted."


def change_password(old_password, new_password):
    global current_user

    if not is_logged():
        return False, "No user is currently logged in."
    
    if not verify_password(old_password, current_user["password_hash"], current_user["password_salt"]):
        return False, "Current password is incorrect."
    
    valid, error = validate_password(new_password)
    if not valid:
        return False, error
    
    username = current_user["username"]
    user_id = current_user["id"]
    
    db.change_user_password(user_id, new_password)

    db.delete_user_sessions(user_id)

    # clear_session_token()
    clear_session_state()

    login(username, new_password)

    return True, "Password changed successfully."


def change_username(new_username):
    global current_user

    if not is_logged():
        return False, "No user is currently logged in."
    
    new_username = new_username.strip().lower()
    
    valid, error = validate_username(new_username)
    if not valid:
        return False, error
    
    if new_username == current_user["username"]:
        return False, "It's already your username. Baka~"
    
    exist = db.get_user_by_username(new_username)
    if exist:
        return False, "Username is already taken."
    
    db.update_user(current_user["id"], username=new_username)
    current_user = db.get_user_by_id(current_user["id"])

    return True, "Username changed successfully."


def validate_session():
    global current_user, current_token

    if not current_token:
        # current_token = load_session_token()
        return False
    
    session = db.get_session(current_token)

    if session is None:
        # clear_session_token()
        current_user = None
        current_token = None
        return False
    
    current_user = db.get_user_by_id(session["user_id"])

    if current_user is None:
        db.delete_session(current_token)
        # clear_session_token()
        current_token = None
        return False

    if current_user and current_user.get("is_banned") == 1:
        logout()
        return False

    return True
