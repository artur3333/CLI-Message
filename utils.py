import time
import secrets
import hashlib
import re
from datetime import datetime


def timestamp():
    timestamp = int(time.time())
    return timestamp


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(32)

    pass_salt = password + salt
    pass_hash = hashlib.sha256(pass_salt.encode()).hexdigest()

    return pass_hash, salt


def validate_username(username):
    if not username:
        return False, "Username cannot be empty."

    if len(username) < 3:
        return False, "Username must be at least 3 characters long."

    if len(username) > 20:
        return False, "Username cannot be longer than 20 characters."

    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return False, "Username can only contain letters, numbers, and underscores."

    return True, ""


def validate_password(password):
    if not password:
        return False, "Password cannot be empty."

    if len(password) < 6:
        return False, "Password must be at least 6 characters long."
    
    return True, ""


def verify_password(password, hashed_password, salt):
    new_hash, _ = hash_password(password, salt)
    if new_hash == hashed_password:
        return True
    
    return False


def generate_token():
    return secrets.token_hex(32)


def generate_invite_code():
    return secrets.token_urlsafe(8)


def format_timestamp(timestamp):
    return time.strftime("%H:%M", time.localtime(timestamp))


def get_display_name(user):
    if user.get("display_name"):
        return user["display_name"]
    else:
        return user["username"]
    
def get_display_name_markup(user):
    name = get_display_name(user)
    color = user.get("name_color", "")
    if color and color in ["white", "cyan", "green", "yellow", "magenta", "red", "blue", "bright_cyan", "bright_green", "bright_yellow", "bright_magenta", "bright_red"]:
        bugged_colors = {
            "white": "bright_white",
            "cyan":   "#00bcd4",
            "green":  "#4caf50",
            "yellow": "#ffeb3b",
            "magenta": "#e91e63",
            "red":    "#f44336",
            "blue":   "#2196f3",
            "bright_cyan":   "#00e5ff",
            "bright_green":  "#69ff47",
            "bright_yellow": "#ffe066",
            "bright_magenta":"#ff6ef7",
            "bright_red":    "#ff6b6b",
        }
        rich_color = bugged_colors.get(color, color)
        return f"[bold {rich_color}]{name}[/bold {rich_color}]"
    
    return f"[bold]{name}[/bold]"


def get_accent_color(user):
    color = user.get("accent_color", "dark_blue")
    if color not in ["dark_blue", "dark_green", "dark_red", "dark_magenta", "dark_cyan"]:
        color = "dark_blue"
    
    return color
        


def day_label(timestamp):
    datee = datetime.fromtimestamp(timestamp).date()
    today = datetime.now().date()
    delta = (today - datee).days

    if delta == 0:
        return "Today"
    elif delta == 1:
        return "Yesterday"
    else:
        return datetime.fromtimestamp(timestamp).strftime("%B %d, %Y")
    

def should_compact(previous_message, current_message):
    if previous_message is None:
        return False

    if previous_message["sender_id"] != current_message["sender_id"]:
        return False
    
    if not datetime.fromtimestamp(previous_message["created"]).date() == datetime.fromtimestamp(current_message["created"]).date():
        return False

    time_diff = current_message["created"] - previous_message["created"]
    if time_diff > 300:  # 5 minutes
        return False

    return True


def highlight_mention(content, username):
    def replace(match):
        mention = match.group(1)
        if mention.lower() == username.lower():
            return f"[bold white on #5865F2] @{mention} [/bold white on #5865F2]"

        return f"[bold cyan]@{mention}[/bold cyan]"
    
    return re.sub(r"@(\w+)", replace, content.replace("[", "\\["))
