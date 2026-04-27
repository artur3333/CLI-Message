import os
import re
import io
import json
import atexit
from datetime import datetime
from PIL import Image as PImage

from rich.text import Text
from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.widgets import Input, Button, Static, Label
from textual.widget import Widget
from textual.containers import Horizontal, Container, ScrollableContainer
from textual_image.widget import Image as TImage

import auth
import db
from utils import format_timestamp, day_label, should_compact, highlight_mention, get_display_name, get_display_name_markup, get_accent_color, get_presence_indicator


class LoginScreen(Screen):
    def compose(self) -> ComposeResult:
        with Container(id="login-container"):
            yield Label("Welcome to CLI-Message!", id="login-title")
            yield Label("", id="login-error")
            yield Label("Username",  classes="field-label")
            yield Input(placeholder="Enter your username", id="username-input")
            yield Label("Password",  classes="field-label")
            yield Input(placeholder="••••••••", password=True, id="password-input")
            with Horizontal(id="login-buttons"):
                yield Button("Login", id="login-button", variant="primary")
                yield Button("Register", id="register-button")

    def on_button_pressed(self, event: Button.Pressed):
        username = self.query_one("#username-input", Input).value.strip()
        password = self.query_one("#password-input", Input).value.strip()
        error = self.query_one("#login-error", Label)

        if not username or not password:
            error.update("Please fill in all fields.")
            return
        
        if event.button.id == "login-button":
            success, message = auth.login(username, password)
            if success:
                error.update("")
                self.app.push_screen(MainScreen())

            else:
                error.update(message)

        elif event.button.id == "register-button":
            success, message = auth.register(username, password)
            if success:
                auth.login(username, password)
                error.update("")
                self.app.push_screen(MainScreen())

            else:
                error.update(message)


class MainScreen(Screen):
    BINDINGS = [("ctrl+q", "quit_app", "Quit")]
    def __init__(self):
        super().__init__()
        self.active_server = None
        self.active_channel = None
        self.last_message_id = 0
        self.pending_attachment = None
        self.active_mode = "dm"
        self.dm_view = "friends"
        self.active_dm_user = None

        self.last_message_day = None
        self.last_message_previous = None

        self.global_channel_last_ids = {}
        self.global_dm_last_ids = {}
        
        self.search_active = False

        self.loading_members = False

        self.last_pending_count = None

        user = auth.get_current_user()
        settings = db.get_user_settings(user["id"])
        self.dm_notifications = bool(settings.get("dm_notifications", 1))
        self.mention_notifications = bool(settings.get("mention_notifications", 1))
        self.compact_mode = bool(settings.get("compact_mode", 0))
        self.theme = settings.get("theme", "dark")

    def compose(self) -> ComposeResult:

        with Container(id="servers-container"):
            pass

        with Container(id="channels-container"):
            with Horizontal(id="server-title"):
                yield Label("CLI-Message", id="server-name")

            with ScrollableContainer(id="channels-list"):
                # yield Label("", id="channels-title")
                pass

            with Container(id="user-info"):
                yield Avatar(id ="user-info-avatar")
                
                with Container(id="user-info-text"):
                    yield Label("", id="user-info-name")
                    yield Label("", id="user-info-status")

                with Horizontal(id = "user-info-buttons"):
                    yield Button("S", id="settings-button", classes="user-info-button")
                    yield Button("L", id="logout-button", classes="user-info-button")

        with Container(id="chat-container"):
            yield Label("", id="chat-title")
            with Horizontal(id="dm-navbar"):
                yield Button("Online", id="dm-tab-online", classes="dm-tab")
                yield Button("Friends", id="dm-tab-friends", classes="dm-tab active-dm-tab")
                yield Button("Pending", id="dm-tab-pending", classes="dm-tab")
                yield Static("", id="dm-navbar-separator")
                yield Button("+ Add Friend", id="dm-add-friend", variant="primary")

            with ScrollableContainer(id="messages-container"):
                yield Static("Select a channel to start chatting", id="chat-placeholder", classes="chat-placeholder")
            
            with Horizontal(id="input-row"):
                yield Button("+", id="attach-button", disabled=True)
                yield Input(placeholder="Type a message...", id="message-input", disabled=True)

        with Container(id="members-container"):
            yield Input(placeholder="Search...", id="search-input")
            with ScrollableContainer(id="members-list"):
                pass

        
    async def on_mount(self):
        user = auth.get_current_user()

        def set_offline():
            db.update_presence(user["id"], "offline")

        atexit.register(set_offline)

        await self.refresh_user_info(user)
        accent = get_accent_color(user)


        if self.active_mode == "dm":
            await self.switch_dm_mode()
        else:
            self.query_one("#dm-navbar").display = False
            await self.load_servers()

        self.set_interval(1, self.refresh_messages)
        self.set_interval(1, self.refresh_notifications)
        self.set_interval(1, self.refresh_badges)
        self.set_interval(5, self.refresh_members)
        self.set_interval(5, self.refresh_dm)

        settings = db.get_user_settings(user["id"])
        self.apply_theme(settings.get("theme", "dark"))

        db.update_presence(user["id"], "online")
        self.change_presence("online")


    def apply_theme(self, theme):
        if theme == "light":
            self.app.add_class("light-mode")
        else:
            self.app.remove_class("light-mode")

    
    async def action_quit_app(self):
        user = auth.get_current_user()
        db.update_presence(user["id"], "offline")
        self.app.exit()


    def change_presence(self, presence):
        avatar = self.query_one("#user-info-avatar", Avatar)
        for classname in ["status-online", "status-dnd", "status-invisible", "status-offline"]:
            avatar.remove_class(classname)

        avatar.add_class(f"status-{presence}")
        avatar.presence = presence


    async def refresh_user_info(self, user):
        name = get_display_name(user)
        markup_name = get_display_name_markup(user)
        accent = get_accent_color(user)
        avatar = self.query_one("#user-info-avatar", Avatar)

        avatar.update_label(name[0].upper())
        self.query_one("#user-info-name", Label).update(Text.from_markup(markup_name))
        self.query_one("#user-info-status", Label).update(user.get("status") or f"[dim]@{user['username']}[/dim]")

        settings = db.get_user_settings(user["id"])
        presence = settings.get("presence", "online")
        self.change_presence(presence)


    async def refresh_messages(self):
        if self.active_mode == "dm":
            if not self.active_dm_user:
                return
            user = auth.get_current_user()
            messages = db.get_dm_messages_after(user["id"], self.active_dm_user["id"], self.last_message_id)
        
        elif self.active_mode == "server":
            if not self.active_channel:
                return
            messages = db.get_messages_after(self.active_channel["id"], self.last_message_id)

        else:
            return
        
        if not messages:
            return
        
        prev = self.last_message_previous
        prev_day = self.last_message_day

        for message in messages:
            message_day = datetime.fromtimestamp(message["created"]).date()
            if prev_day is None or message_day != prev_day:
                await self.query_one("#messages-container").mount(DaySeparator(day_label(message["created"])))
                prev_day = message_day
                prev = None

            compact = should_compact(prev, message)
            await self.query_one("#messages-container").mount(Message(message, compact=compact, compact_mode=self.compact_mode))
            prev = message
            
        self.last_message_previous = prev
        self.last_message_day = prev_day

        self.last_message_id = messages[-1]["id"]

        self.query_one("#messages-container").scroll_end(animate=False)

        user = auth.get_current_user()
        if self.active_mode == "server" and self.active_channel:
            db.mark_channel_read(user["id"], self.active_channel["id"], self.last_message_id)
        elif self.active_mode == "dm" and self.active_dm_user:
            db.mark_dm_read(user["id"], self.active_dm_user["id"], self.last_message_id)


    async def refresh_notifications(self):
        user = db.get_user_by_id(auth.get_current_user()["id"])
        dnd = user.get("presence") == "dnd"
        
        for server in db.get_user_servers(user["id"]):
            for channel in db.get_server_channels(server["id"]):
                c = channel["id"]

                if self.active_mode == "server" and self.active_channel and self.active_channel["id"] == c:
                    self.global_channel_last_ids[c] = self.last_message_id
                    continue
                
                if c not in self.global_channel_last_ids:
                    if db.get_messages_after(c, 0):
                        self.global_channel_last_ids[c] = db.get_messages_after(c, 0)[-1]["id"]
                    else:
                        self.global_channel_last_ids[c] = 0
                    continue

                messages = db.get_messages_after(c, self.global_channel_last_ids[c])
                if not messages:
                    continue

                for message in messages:
                    if message["sender_id"] == user["id"]:
                        continue
                        
                    lower_mentions = []
                    for mention in re.findall(r"@(\w+)", message["content"]):
                        lower_mentions.append(mention.lower())
                        
                    if user["username"] in lower_mentions:
                        if self.mention_notifications == True and not dnd:
                            self.notify(f"{message["username"]} mentioned you in #{channel["name"]} in {server['name']}", title="Mention", severity="warning")

                self.global_channel_last_ids[channel["id"]] = messages[-1]["id"]

        
        for friend in db.get_friends(user["id"]):
            f = friend["id"]

            if self.active_mode == "dm" and self.active_dm_user and self.active_dm_user["id"] == f:
                self.global_dm_last_ids[f] = self.last_message_id
                continue

            if f not in self.global_dm_last_ids:
                if db.get_dm_messages_after(user["id"], f, 0):
                    self.global_dm_last_ids[f] = db.get_dm_messages_after(user["id"], f, 0)[-1]["id"]
                else:
                    self.global_dm_last_ids[f] = 0
                continue

            messages = db.get_dm_messages_after(user["id"], f, self.global_dm_last_ids[f])
            if not messages:
                continue

            for message in messages:
                if message["sender_id"] == user["id"]:
                    continue
                
                if self.dm_notifications == True and not dnd:
                    self.notify(f"New message from @{message['username']}", title="DM")

            self.global_dm_last_ids[f] = messages[-1]["id"]


        pending = db.get_pending_friend_requests(user["id"])
        current_count = len(pending)

        if self.last_pending_count is not None and current_count > self.last_pending_count:
            if not dnd:
                self.notify(f"You have {current_count} pending friend requests", title="Friend Requests", severity="warning")
        
        self.last_pending_count = current_count

    
    async def refresh_badges(self):
        user = auth.get_current_user()
        
        server_unreads = db.get_all_server_unreads(user["id"])
        for server_id, count in server_unreads.items():
            try:
                button = self.query_one(f"#server-{server_id}", Button)
                if count > 0:
                    button.add_class("server-unread")
                else:
                    button.remove_class("server-unread")
            
            except Exception as e:
                pass

        dm_unreads = db.get_all_dm_unreads(user["id"])
        total_dm_unreads = sum(dm_unreads.values())
        try:
            dm_button = self.query_one("#dm-button", Button)
            if total_dm_unreads > 0:
                dm_button.add_class("dm-server-unread")
            else:
                dm_button.remove_class("dm-server-unread")

        except Exception as e:
            pass

        if self.active_server:
            for channel in db.get_server_channels(self.active_server["id"]):
                try:
                    button = self.query_one(f"#channel-{channel['id']}", Button)
                    
                    if self.active_channel and self.active_channel["id"] == channel["id"]:
                        button.remove_class("channel-unread")
                        continue

                    unread = db.get_channel_unread_count(user["id"], channel["id"])
                    if unread > 0:
                        button.add_class("channel-unread")
                    else:
                        button.remove_class("channel-unread")

                except Exception as e:
                    pass

        if self.active_mode == "dm" and not self.active_dm_user:
            for friend in db.get_friends(user["id"]):
                try:
                    button = self.query_one(f"#dm-{friend['id']}", Button)
                    unread = db.get_dm_unread_count(user["id"], friend["id"])
                    if unread > 0:
                        button.add_class("dm-unread")
                    else:
                        button.remove_class("dm-unread")

                except Exception as e:
                    pass


    async def refresh_members(self):
        if self.active_server and not self.search_active:
            await self.load_members(self.active_server["id"])


    async def refresh_dm(self):
        if self.active_mode != "dm":
            return
        
        await self.load_dm_sidebar()

        if self.active_dm_user:
            self.active_dm_user = db.get_user_by_id(self.active_dm_user["id"])
            await self.query_one(f"#members-list").remove_children()
            await self.query_one(f"#members-list").mount(DMUserPanel(self.active_dm_user))

        else:
            if self.dm_view == "online":
                await self.load_dm_online_view()
            
            elif self.dm_view == "friends":
                await self.load_dm_friends_view()
            
            elif self.dm_view == "pending":
                await self.load_dm_pending_view()

            for tab in ["dm-tab-online", "dm-tab-friends", "dm-tab-pending"]:
                self.query_one(f"#{tab}", Button).remove_class("active-dm-tab")

            self.query_one(f"#dm-tab-{self.dm_view}", Button).add_class("active-dm-tab")



    async def load_servers(self):
        user = auth.get_current_user()
        servers = db.get_user_servers(user["id"])
        servers_container = self.query_one("#servers-container")
        await servers_container.remove_children()

        if self.active_mode == "dm":
            dm_classes = "server-button active-server"
        else:
            dm_classes = "server-button"

        await servers_container.mount(Button(">", id="dm-button", classes=dm_classes))
        await servers_container.mount(Static("---", classes="divider"))

        for server in servers:
            if server["icon"]:
                icon = server["icon"]
            else:
                icon = server["name"][0].upper()

            if self.active_server and self.active_server["id"] == server["id"]:
                classes = "server-button active-server"
            else:
                classes = "server-button"

            await servers_container.mount(Button(icon, id=f"server-{server['id']}", classes=classes))

        await servers_container.mount(Button("+", id=f"add-server-button", classes="server-add-button"))


    async def load_channels(self, server_id):
        channels = db.get_server_channels(server_id)
        channels_list = self.query_one("#channels-list")
        await channels_list.remove_children()
        user = auth.get_current_user()
        
        for channel in channels:
            if self.active_channel and self.active_channel["id"] == channel["id"]:
                classes = "channel-button active-channel"
            else:
                classes = "channel-button"
            
            unread = db.get_channel_unread_count(user["id"], channel["id"])
            if unread > 0 and not (self.active_channel and self.active_channel["id"] == channel["id"]):
                classes += " channel-unread"

            await channels_list.mount(Button(f"#\u00a0{channel['name']}", id=f"channel-{channel['id']}", classes=classes))

        await channels_list.mount(Button("+ Add Channel", id=f"add-channel-button", classes="add-channel-button"))

    
    async def load_members(self, server_id):
        if self.search_active:
            return
        
        if self.loading_members:
            return
        self.loading_members = True
        try:
            members = db.get_server_members(server_id)
            members_list = self.query_one("#members-list")
            await members_list.remove_children()

            for member in members:
                name = f"{get_presence_indicator(member)} {get_display_name_markup(member)}"

                await members_list.mount(Button(Text.from_markup(name), id=f"member-{member['id']}", classes="member-button"))
        
        finally:
            self.loading_members = False


    async def load_messages(self, channel_id):
        messages = db.get_channel_messages(channel_id)
        messages_container = self.query_one("#messages-container")
        await messages_container.remove_children()

        channel = self.active_channel
        await messages_container.mount(Static(f"This is the beginning of # {channel["name"]}", classes="channel-start-placeholder"))

        prev = self.last_message_previous
        prev_day = self.last_message_day

        for message in messages:
            message_day = datetime.fromtimestamp(message["created"]).date()
            if prev_day is None or message_day != prev_day:
                await self.query_one("#messages-container").mount(DaySeparator(day_label(message["created"])))
                prev_day = message_day
                prev = None

            compact = should_compact(prev, message)
            await self.query_one("#messages-container").mount(Message(message, compact=compact, compact_mode=self.compact_mode))
            prev = message

        if messages:
            self.last_message_id = messages[-1]["id"]
            self.last_message_previous = messages[-1]
            self.last_message_day = datetime.fromtimestamp(messages[-1]["created"]).date()
        
        else:
            self.last_message_id = 0
            self.last_message_previous = None
            self.last_message_day = None

        messages_container.scroll_end(animate=False)

        
    async def load_dm_messages(self, user_id):
        current_user = auth.get_current_user()
        messages = db.get_dm_messages(current_user["id"], user_id)
        messages_container = self.query_one("#messages-container")
        await messages_container.remove_children()

        name = get_display_name(self.active_dm_user)

        await messages_container.mount(Static(f"This is the beginning of your direct messages with @{name}", classes="channel-start-placeholder"))

        prev = self.last_message_previous
        prev_day = self.last_message_day

        for message in messages:
            message_day = datetime.fromtimestamp(message["created"]).date()
            if prev_day is None or message_day != prev_day:
                await self.query_one("#messages-container").mount(DaySeparator(day_label(message["created"])))
                prev_day = message_day
                prev = None

            compact = should_compact(prev, message)
            await self.query_one("#messages-container").mount(Message(message, compact=compact, compact_mode=self.compact_mode))
            prev = message

        if messages:
            self.last_message_id = messages[-1]["id"]
            self.last_message_previous = messages[-1]
            self.last_message_day = datetime.fromtimestamp(messages[-1]["created"]).date()
        
        else:
            self.last_message_id = 0
            self.last_message_previous = None
            self.last_message_day = None

        messages_container.scroll_end(animate=False)


    async def switch_dm_mode(self): #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        self.active_server = None
        self.active_channel = None
        self.last_message_id = 0
        self.pending_attachment = None
        self.active_mode = "dm"
        self.dm_view = "friends"
        self.active_dm_user = None
        self.last_message_day = None
        self.last_message_previous = None

        self.search_active = False
        self.query_one("#members-container").remove_class("search-active")

        await self.load_servers()

        self.query_one("#server-name", Label).update("Direct Messages")
        for button in self.query_one("#server-title").query(".invite-button"):
            await button.remove()
        
        await self.load_dm_sidebar()

        self.query_one("#chat-title", Label).display = False
        self.query_one("#dm-navbar").display = True
        self.query_one("#input-row").display = False
        self.query_one("#members-container").display = False


        self.query_one("#dm-tab-friends", Button).add_class("active-dm-tab")
        self.query_one("#dm-tab-pending", Button).remove_class("active-dm-tab")
        self.query_one("#dm-tab-online", Button).remove_class("active-dm-tab")

        await self.query_one("#members-list").remove_children()
        await self.load_dm_friends_view()

        self.query_one("#search-input", Input).placeholder = "Search friends..."


    async def load_dm_sidebar(self):
        user = auth.get_current_user()
        friends = db.get_friends(user["id"])
        pending = db.get_pending_friend_requests(user["id"])
        
        channels_list = self.query_one("#channels-list")
        await channels_list.remove_children()

        if pending:
            await channels_list.mount(Button(f"Pending ({len(pending)})", id="sidebar-pending-button", classes="sidebar-pending-button"))
        
        if friends:
            for friend in friends:
                markup_name = get_display_name_markup(friend)

                if self.active_dm_user and self.active_dm_user["id"] == friend["id"]:
                    button_classes = "channel-button active-channel"
                else:
                    button_classes = "channel-button"
                
                dm_text = Text.from_markup(f"{get_presence_indicator(friend)} {markup_name}")
                unread = db.get_dm_unread_count(user["id"], friend["id"])
                if unread > 0 and not (self.active_dm_user and self.active_dm_user["id"] == friend["id"]):
                    button_classes += " dm-unread"
                    dm_text.append(f" ({unread})")

                await channels_list.mount(Button(dm_text, id=f"dm-{friend['id']}", classes=button_classes))
        
        else:
            await channels_list.mount(Static("No friends yet...", classes="channel-placeholder"))

    async def load_dm_online_view(self):
        self.dm_view = "online"
        self.query_one("#input-row").display = False
        self.query_one("#members-container").display = False

        user = auth.get_current_user()
        friends = db.get_friends(user["id"])

        online = []
        for friend in friends:
            if friend.get("presence", "online") == "online" or friend.get("presence", "online") == "dnd":
                online.append(friend)

        container = self.query_one("#messages-container")
        await container.remove_children()

        if not online:
            await container.mount(Static("No friends online...", classes="chat-placeholder"))
            return

        await container.mount(Static(f"[bold]Online Friends ({len(online)})[/bold]", markup=True, classes="dm-section-header"))

        for friend in online:
            await container.mount(FriendCard(friend))

    async def load_dm_friends_view(self):
        self.dm_view = "friends"
        self.query_one("#input-row").display = False
        self.query_one("#members-container").display = False

        user = auth.get_current_user()
        friends = db.get_friends(user["id"])

        container = self.query_one("#messages-container")
        await container.remove_children()

        if not friends:
            await container.mount(Static("No friends yet...", classes="chat-placeholder"))
            return
        
        await container.mount(Static(f"[bold]All Friends ({len(friends)})[/bold]", markup=True, classes="dm-section-header"))
        
        for friend in friends:
            await container.mount(FriendCard(friend))

    async def load_dm_pending_view(self):
        self.dm_view = "pending"
        self.query_one("#input-row").display = False
        self.query_one("#members-container").display = False

        user = auth.get_current_user()
        pending = db.get_pending_friend_requests(user["id"])
        
        container = self.query_one("#messages-container")
        await container.remove_children()

        if not pending:
            await container.mount(Static("No pending requests...", classes="chat-placeholder"))
            return
        
        await container.mount(Static(f"[bold]Pending Friend Requests ({len(pending)})[/bold]", markup=True, classes="dm-section-header"))
        
        for request in pending:
            await container.mount(FriendRequestCard(request))

    async def open_dm(self, user_id):
        user = auth.get_current_user()
        friend = db.get_user_by_id(user_id)
        if not friend:
            return
        
        name = get_display_name(friend)
        
        self.active_dm_user = friend
        self.last_message_id = 0
        self.last_message_day = None
        self.last_message_previous = None

        self.search_active = False
        self.query_one("#members-container").remove_class("search-active")

        for button in self.query(".channel-button"):
            button.remove_class("active-channel")
        
        self.query_one(f"#dm-{user_id}", Button).add_class("active-channel")

        self.query_one("#dm-navbar").display = False
        self.query_one("#chat-title").display = True
        self.query_one("#input-row").display = True
        self.query_one("#members-container").display = True

        self.query_one("#chat-title", Label).update(f" @{name}")
        self.query_one("#message-input", Input).disabled = False
        self.query_one("#attach-button", Button).disabled = False
        self.query_one("#message-input", Input).placeholder = f"Message @{name}..."
        self.query_one("#search-input", Input).placeholder = "Search messages..."
        
        await self.query_one("#members-list").remove_children()
        
        await self.query_one("#members-list").mount(DMUserPanel(friend))

        await self.load_dm_messages(friend["id"])

        if self.last_message_id:
            db.mark_dm_read(user["id"], friend["id"], self.last_message_id)
        await self.load_dm_sidebar()

    
    async def switch_server(self, server_id): #! Check thisssssssssssss!!!!
        server = db.get_server_by_id(server_id)
        self.active_server = server
        self.active_channel = None
        self.last_message_id = 0
        self.active_mode = "server"
        self.dm_view = "friends"
        self.pending_attachment = None
        self.active_dm_user = None
        self.last_message_day = None
        self.last_message_previous = None
        self.search_active = False
        self.query_one("#members-container").remove_class("search-active")

        
        self.query_one("#chat-title").display = True
        self.query_one("#dm-navbar").display = False
        self.query_one("#input-row").display = True
        self.query_one("#members-container").display = True
        self.query_one("#search-input", Input).placeholder = "Search members..."

        self.query_one("#server-name", Label).update(server["name"])

        header = self.query_one("#server-title")
        for button in header.query(".invite-button"):
            await button.remove()

        await header.mount(Button("Invite", id=f"invite-button", classes="invite-button"))

        for button in self.query(".server-button"):
            button.remove_class("active-server")

        self.query_one(f"#server-{server_id}", Button).add_class("active-server")

        await self.load_channels(server_id)
        await self.load_members(server_id)

        self.query_one("#chat-title", Label).update("")
        messages = self.query_one("#messages-container")
        await messages.remove_children()
        await messages.mount(Static("Select a channel to chat", classes="chat-placeholder"))
        
        self.query_one("#message-input", Input).disabled = True
        self.query_one("#attach-button", Button).disabled = True
        self.pending_attachment = None
    

    async def switch_channel(self, channel_id):
        channel = db.get_channel_by_id(channel_id)
        user = auth.get_current_user()
        
        self.active_channel = channel
        self.search_active = False
        self.query_one("#members-container").remove_class("search-active")

        header = f" # {channel['name']}"
        if channel.get("description"):
            header = header + f" - {channel['description']}"
        self.query_one("#chat-title", Label).update(header)

        for button in self.query(".channel-button"):
            button.remove_class("active-channel")

        self.query_one(f"#channel-{channel_id}", Button).add_class("active-channel")
        
        self.query_one("#message-input", Input).disabled = False
        self.query_one("#attach-button", Button).disabled = False
        self.query_one("#message-input", Input).placeholder = f"Message # {channel['name']}..."
        self.query_one("#search-input", Input).placeholder = "Search messages..."
        self.pending_attachment = None

        await self.load_messages(channel_id)
        
        if self.last_message_id:
            db.mark_channel_read(user["id"], channel_id, self.last_message_id)


    async def send_message(self, content, attachment_path=None):
        if self.active_mode == "server" and not self.active_channel:
            return
        
        if self.active_mode == "dm" and not self.active_dm_user:
            return
        
        user = auth.get_current_user()
        
        attachment_data = None
        attachment_name = None
        if attachment_path:
            try:
                if os.path.getsize(attachment_path) > 50 * 1024 * 1024: # 50 MB
                    self.notify("Attachment is too large. Max size is 50 MB.", title="Error")
                    return
                
                with open(attachment_path, "rb") as file:
                    attachment_data = file.read()

                attachment_name = os.path.basename(attachment_path)
            
            except Exception as e:
                self.notify(f"Failed to read attachment: {str(e)}", title="Error")
                pass

        if self.active_mode == "dm":
            if not self.active_dm_user:
                return
            
            success, result = db.send_dm(user["id"], self.active_dm_user["id"], content, attachment_data=attachment_data, attachment_name=attachment_name)
            if not success:
                return
            messages = db.get_dm_messages_after(user["id"], self.active_dm_user["id"], self.last_message_id)
        
        elif self.active_mode == "server":
            if not self.active_channel:
                return
            
            success, result = db.send_message(self.active_channel["id"], user["id"], content, attachment_data=attachment_data, attachment_name=attachment_name)
            if not success:
                return
            messages = db.get_messages_after(self.active_channel["id"], self.last_message_id)

        if not success:
            return
        
        prev = self.last_message_previous
        prev_day = self.last_message_day

        for message in messages:
            message_day = datetime.fromtimestamp(message["created"]).date()
            if prev_day is None or message_day != prev_day:
                await self.query_one("#messages-container").mount(DaySeparator(day_label(message["created"])))
                prev_day = message_day
                prev = None

            compact = should_compact(prev, message)
            await self.query_one("#messages-container").mount(Message(message, compact=compact, compact_mode=self.compact_mode))
            prev = message
            
        self.last_message_previous = prev
        self.last_message_day = prev_day

        self.last_message_id = messages[-1]["id"]
        self.query_one("#messages-container").scroll_end(animate=False)

        if self.active_mode == "server" and self.active_channel and self.last_message_id:
            db.mark_channel_read(user["id"], self.active_channel["id"], self.last_message_id)

        elif self.active_mode == "dm" and self.active_dm_user and self.last_message_id:
            db.mark_dm_read(user["id"], self.active_dm_user["id"], self.last_message_id)


        self.pending_attachment = None
        self.query_one("#attach-button", Button).label = "+"

        if self.active_mode == "dm" and self.active_dm_user:
            self.query_one("#message-input", Input).placeholder = f"Message @{self.active_dm_user['username']}..."

        else:
            self.query_one("#message-input", Input).placeholder = "Type a message..."


    async def search(self, query):
        while self.loading_members:
            await self.sleep(0)

        members_list = self.query_one("#members-list")
        user = auth.get_current_user()
        query = query.strip()

        if not query:
            self.search_active = False
            self.query_one("#members-container").remove_class("search-active")
            await members_list.remove_children()

            if self.active_mode == "server" and self.active_server:
                await self.load_members(self.active_server["id"])
            
            elif self.active_mode == "dm" and self.active_dm_user:
                await members_list.mount(DMUserPanel(self.active_dm_user))

            return
        
        self.search_active = True
        self.query_one("#members-container").add_class("search-active")
        await members_list.remove_children()

        if self.active_mode == "server":
            if self.active_channel:
                results = db.search_messages(self.active_channel["id"], query)
                if results:
                    await members_list.mount(Static(f"Search Results for \"{query}\"", classes="search-results-title"))
                    for message in results:
                        await members_list.mount(SearchResult(message))
                    
                else:
                    await members_list.mount(Static(f"No results found for \"{query}\"", classes="search-results-title"))

            
            if self.active_server:
                members = db.get_server_members(self.active_server["id"])
            else:
                members = []

            matched = []
            for member in members:
                name = get_display_name(member)
                if query.lower() in name.lower():
                    matched.append(member)

            if matched:
                await members_list.mount(Static(f"Members matching \"{query}\"", classes="search-results-title"))
                for member in matched:
                    await members_list.mount(Button(get_display_name(member), id=f"member-{member['id']}", classes="member-button"))
            
        
        elif self.active_mode == "dm":
            if self.active_dm_user:
                results = db.search_dm_messages(user["id"], self.active_dm_user["id"], query)
                if results:
                    await members_list.mount(Static(f"Search Results for \"{query}\"", classes="search-results-title"))
                    for message in results:
                        await members_list.mount(SearchResult(message))
                
                else:
                    await members_list.mount(Static(f"No results found for \"{query}\"", classes="search-results-title"))


    async def on_button_pressed(self, event: Button.Pressed):
        button_id = event.button.id
        
        if button_id == "add-server-button":
            def option(choice):
                if choice == "create":
                    self.app.push_screen(CreateServerScreen(), self.server_created)

                elif choice == "join":
                    self.app.push_screen(JoinServerScreen(), self.server_joined)

            self.app.push_screen(ServerOptionsScreen(), option)

        elif button_id.startswith("server-"):
            server_id = button_id.split("-", 1)[1]
            await self.switch_server(server_id)

        elif button_id == "invite-button":
            if self.active_server:
                self.app.push_screen(InviteCodePopup(self.active_server["invite_code"], self.active_server["name"]))

        elif button_id == "add-channel-button":
            if self.active_server:
                self.app.push_screen(CreateChannelScreen(self.active_server["id"]), self.channel_created)

        elif button_id.startswith("channel-"):
            channel_id = button_id.split("-", 1)[1]
            await self.switch_channel(channel_id)

        elif button_id == "attach-button":
            if self.pending_attachment:
                self.pending_attachment = None
                self.query_one("#attach-button", Button).label = "+"

                if self.active_mode == "dm" and self.active_dm_user:
                    self.query_one("#message-input", Input).placeholder = f"Message @{self.active_dm_user['username']}..."
                elif self.active_channel:
                    self.query_one("#message-input", Input).placeholder = f"Message # {self.active_channel['name']}..."
                else:
                    self.query_one("#message-input", Input).placeholder = "Type a message..."

            else:
                self.app.push_screen(Attachment(), self.attachment_selected)

        elif button_id.startswith("download-"):
            message_single = event.button.parent.parent

            if isinstance(message_single, Message):
                data = message_single.message.get("attachment_data")
                filename = message_single.message.get("attachment_name")
                
                self.app.push_screen(DownloadScreen(filename, data))

        elif button_id == "dm-button":
            await self.switch_dm_mode()

        elif button_id == "dm-tab-online":
            self.query_one("#dm-tab-online", Button).add_class("active-dm-tab")
            self.query_one("#dm-tab-friends", Button).remove_class("active-dm-tab")
            self.query_one("#dm-tab-pending", Button).remove_class("active-dm-tab")
            await self.load_dm_online_view()

        elif button_id == "dm-tab-friends":
            self.query_one("#dm-tab-friends", Button).add_class("active-dm-tab")
            self.query_one("#dm-tab-pending", Button).remove_class("active-dm-tab")
            self.query_one("#dm-tab-online", Button).remove_class("active-dm-tab")
            await self.load_dm_friends_view()

        elif button_id == "dm-tab-pending":
            self.query_one("#dm-tab-pending", Button).add_class("active-dm-tab")
            self.query_one("#dm-tab-friends", Button).remove_class("active-dm-tab")
            self.query_one("#dm-tab-online", Button).remove_class("active-dm-tab")
            await self.load_dm_pending_view()

        elif button_id.startswith("sidebar-pending-button"):
            self.query_one("#dm-tab-pending", Button).add_class("active-dm-tab")
            self.query_one("#dm-tab-friends", Button).remove_class("active-dm-tab")
            self.query_one("#dm-tab-online", Button).remove_class("active-dm-tab")
            await self.load_dm_pending_view()

        elif button_id == "dm-add-friend":
            self.app.push_screen(AddFriendScreen(), self.after_add_friend)

        elif button_id.startswith("dm-"):
            user_id = button_id.split("-", 1)[1]
            await self.open_dm(user_id)

        elif button_id.startswith("accept-"):
            request = button_id.split("-", 1)[1]
            success, result = db.accept_friend_request(request)
            if success:
                await self.load_dm_sidebar()
                await self.load_dm_pending_view()
            else:
                self.notify(result, title="Error")

        elif button_id.startswith("decline-"):
            request = button_id.split("-", 1)[1]
            success, result = db.decline_friend_request(request)
            if success:
                await self.load_dm_sidebar()
                await self.load_dm_pending_view()
            else:
                self.notify(result, title="Error")

        elif button_id.startswith("member-"):
            user_id = button_id.split("-", 1)[1]
            target = db.get_user_by_id(user_id)
            if target:
                self.app.push_screen(UserProfileScreen(target)) #self.user_profile_closed

        elif button_id.startswith("removefriend-"):
            user_id = button_id.split("-", 1)[1]
            current_user = auth.get_current_user()
            success, result = db.remove_friend(current_user["id"], user_id)
            if success:
                self.notify("Friend removed.")
                await self.switch_dm_mode()

            else:
                self.notify(result, title="Error")

        elif button_id == "settings-button":
            user = auth.get_current_user()
            self.app.push_screen(SettingsScreen(user, self.dm_notifications, self.mention_notifications, self.compact_mode), self.after_settings_closed)

        elif button_id == "user-info-avatar":
            user = auth.get_current_user()
            avatar = self.query_one("#user-info-avatar", Avatar)

            list = {"online": "dnd", "dnd": "invisible", "invisible": "online"}
            current_presence = getattr(avatar, "presence", "online")
            new_presence = list.get(current_presence, "online")
            
            db.update_presence(user["id"], new_presence)
            self.change_presence(new_presence)
            labels = {"online": "Online", "dnd": "Do Not Disturb", "invisible": "Invisible"}
            self.notify(f"Presence set to {labels[new_presence]}", title="Presence")

        elif button_id == "logout-button":
            user = auth.get_current_user()
            db.update_presence(user["id"], "offline")
            auth.logout()
            self.app.pop_screen()

    
    async def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "message-input":
            content = event.value.strip()
            event.input.value = ""

            if not content and not self.pending_attachment:
                return
            
            if not content and self.pending_attachment:
                content = os.path.basename(self.pending_attachment)

            await self.send_message(content, attachment_path=self.pending_attachment)

        elif event.input.id == "search-input":
            query = event.value.strip()
            await self.search(query)
            return
        
        
    async def on_input_changed(self, event: Input.Changed):
        if event.input.id != "search-input":
            return
        
        if event.value.strip():
            return
        
        self.search_active = False
        self.query_one("#members-container").remove_class("search-active")

        if self.active_mode == "server" and self.active_server:
            await self.load_members(self.active_server["id"])
        
        elif self.active_mode == "dm" and self.active_dm_user:
            await self.query_one("#members-list").remove_children()
            await self.query_one("#members-list").mount(DMUserPanel(self.active_dm_user))
        
        

        #! later maybe
        # query = event.value.strip()
        # if self.active_mode == "server" and self.active_server:
        #     if not query:
        #         self.search_active = False
        #         await self.load_members(self.active_server["id"])


    
    async def server_created(self, server_id):
        if not server_id:
            return
        
        await self.load_servers()
        await self.switch_server(server_id)

    async def server_joined(self, server_id):
        if not server_id:
            return
        
        await self.load_servers()
        await self.switch_server(server_id)

    async def channel_created(self, channel_id):
        if not channel_id:
            return

        if self.active_server:
            await self.load_channels(self.active_server["id"])
            await self.switch_channel(channel_id)

    async def attachment_selected(self, path):
        if not path:
            return
        
        self.pending_attachment = path
        filename = os.path.basename(self.pending_attachment)
        self.query_one("#message-input", Input).placeholder = f"[Attached: {filename}] Type a message..."
        self.query_one("#attach-button", Button).label = "X"

    # async def user_profile_closed(self, result):
    #     return

    async def after_add_friend(self, result):
        if result:
            self.notify("Friend request sent!")
            await self.load_dm_sidebar()
            
        else:
            return
        
    # async def after_profile_edit(self, result):
    #     if result:
    #         user = auth.get_current_user()
    #         auth.current_user = db.get_user_by_id(user["id"])
    #         await self.refresh_user_info(db.get_user_by_id(user["id"]))
            
    #         self.notify("Profile updated", title="Profile")

    async def after_settings_closed(self, result):
        if not result:
            return
        
        if result == "delete":
            self.app.pop_screen()
            return
        
        self.dm_notifications = result.get("dm_notifications", self.dm_notifications)
        self.mention_notifications = result.get("mention_notifications", self.mention_notifications)
        self.compact_mode = result.get("compact_mode", self.compact_mode)
        self.theme = result.get("theme", self.theme)
        self.apply_theme(self.theme)

        user = auth.get_current_user()
        db.update_settings(user["id"], "dm_notifications", int(self.dm_notifications))
        db.update_settings(user["id"], "mention_notifications", int(self.mention_notifications))
        db.update_settings(user["id"], "compact_mode", int(self.compact_mode))
        db.update_settings(user["id"], "theme", self.theme)
        new = db.get_user_by_id(user["id"])
        await self.refresh_user_info(new)

        self.notify("Settings updated", title="Settings")



class Avatar(Button):
    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self.presence = "online"
        self.add_class("user-info-avatar")
        self.add_class("status-online")
    
    def update_label(self, letter):
        self.label = letter.upper()


class DaySeparator(Widget):
    def __init__(self, label):
        super().__init__()
        self.label = label
        self.add_class("day-separator")

    def compose(self) -> ComposeResult:
        yield Static(self.label, classes="day-separator-label")


class Message(Widget):
    def __init__(self, message, compact=False, compact_mode=False):
        super().__init__()
        self.message = message
        self.compact = compact
        self.compact_mode = compact_mode
        self.add_class("message")

        if self.compact:
            self.add_class("compact-message")
        
        if self.compact_mode:
            self.add_class("compact-mode-message")

    def compose(self) -> ComposeResult:
        name = get_display_name_markup(self.message)

        time = format_timestamp(self.message["created"])

        current_user = auth.get_current_user()
        highlighted_content = highlight_mention(self.message["content"], current_user["username"])

        if self.compact_mode:
            message = f"{name} [dim][{time}][/dim]: {highlighted_content}"
            yield Static(Text.from_markup(message), markup=True, classes="message-content compact-mode")
        
        else:
            if not self.compact:
                head = f"{name} [dim][{time}][/dim]"
                yield Static(Text.from_markup(head), classes="message-head")

            yield Static(highlighted_content, markup=True, classes="message-content")


        if self.message.get("attachment_name"):
            filename = os.path.basename(self.message["attachment_name"])
            extension = os.path.splitext(filename)[1].lower()
            if extension in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"] and self.message.get("attachment_data"):
                try:
                    raw = self.message.get("attachment_data")
                    pil_image = PImage.open(io.BytesIO(raw))
                    pil_image.load()
                    yield TImage(pil_image, classes="attachment-image")

                except Exception as e:
                    with Horizontal(classes="attachment-card"):
                        yield Static(f"Image Attachment: [bold]{filename}[/bold]", markup=True, classes="attachment-label")
                        yield Button("↓", id=f"download-{self.message['id']}", classes="download-button")
            else:
                with Horizontal(classes="attachment-card"):
                    yield Static(f"Attachment: [bold]{filename}[/bold]", markup=True, classes="attachment-label")
                    yield Button("↓", id=f"download-{self.message['id']}", classes="download-button")

            if extension in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"] and self.message.get("attachment_data"):
                with Horizontal(classes="attachment-card attachment-image-card"):
                    yield Static(f"[dim]{filename}[/dim]", markup=True, classes="attachment-label")
                    yield Button("↓", id=f"download-{self.message['id']}", classes="download-button")


class Attachment(ModalScreen):
    def compose(self) -> ComposeResult:
        with Container(id="screen-container"):
            yield Label("Attachment", id="screen-title")
            yield Label("", id="screen-error")
            yield Label("File Path", classes="field-label")
            yield Input(placeholder="File path...", id="file-path-input")
            with Horizontal(id="screen-buttons"):
                yield Button("Attach", id="attach-confirm-button", variant="primary")
                yield Button("Cancel", id="cancel-button")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "attach-confirm-button":
            path = self.query_one("#file-path-input", Input).value.strip()
            error = self.query_one("#screen-error", Label)

            if not path:
                error.update("File path cannot be empty.")
                return
            
            if not os.path.isfile(path):
                error.update("File not found. Check the path.")
                return
            
            self.dismiss(path)

        else:
            self.dismiss()


class DownloadScreen(ModalScreen):
    def __init__(self, filename, data):
        super().__init__()
        self.filename = filename
        self.data = data

    def compose(self) -> ComposeResult:
        with Container(id="screen-container"):
            yield Label("Download Attachment", id="screen-title")
            yield Label("", id="screen-error")
            yield Label(f"File: {self.filename}", classes="screen-subtitle")
            yield Label("Destination Path", classes="field-label")
            yield Input(value=os.path.expanduser("~/Downloads"), id="destination-input")
            with Horizontal(id="screen-buttons"):
                yield Button("Download", id="download-button", variant="primary")
                yield Button("Cancel", id="cancel-button")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "download-button":
            destination = self.query_one("#destination-input", Input).value.strip()
            error = self.query_one("#screen-error", Label)

            if not destination:
                error.update("Destination path cannot be empty.")
                return
            
            destination = os.path.expanduser(destination)
            if not os.path.isdir(destination):
                error.update("Destination folder not found.")
                return
            
            destination_path = os.path.join(destination, self.filename)
            
            try:
                with open(destination_path, "wb") as file:
                    file.write(self.data)

                self.app.notify(f"Attachment downloaded to {destination_path}", title="Download Complete")
                self.dismiss(destination_path)
            
            except Exception as e:
                error.update(f"Error: {str(e)}")

        else:
            self.dismiss()



class UserProfileScreen(ModalScreen):
    def __init__(self, user):
        super().__init__()
        self.user = user

    def compose(self) -> ComposeResult:
        current_user = auth.get_current_user()
        is_self = current_user["id"] == self.user["id"]
        if not is_self:
            already_friends = db.are_friends(current_user["id"], self.user["id"])
            request_pending = db.is_friend_request_pending(current_user["id"], self.user["id"])
        else:
            already_friends = False
            request_pending = False
        name = get_display_name(self.user)
        accent = get_accent_color(self.user)
        raw_connections = self.user.get("connections", [])
        current_connections = json.loads(raw_connections)
        markup_name = get_display_name_markup(self.user)
        member_since = datetime.fromtimestamp(self.user["created"]).strftime("%b %d, %Y")
        note = db.get_user_note(current_user["id"], self.user["id"])
            
        with ScrollableContainer(id="screen-container"):
            with Horizontal(id="profile-top-row"):
                yield Static("", classes="profile-top-row-separator")
                yield Button("X", id="profile-close-button")
            yield Label("", id="screen-error", classes="hidden")

            yield Static("", classes=f"profile-banner accent-{accent}")
            yield Static(name[0].upper(), classes="profile-avatar")
            yield Label(Text.from_markup(f"{get_presence_indicator(self.user)} {markup_name}"), classes="profile-name-label")
            yield Label(f"@{self.user['username']}", classes="profile-username-label")
            
            if self.user.get("pronouns"):
                yield Static(self.user["pronouns"], classes="profile-pronouns-label")
            
            if self.user.get("status"):
                yield Static(self.user["status"], classes=f"profile-status-label")
            
            yield Static("[dim]ABOUT ME[/dim]", markup=True, classes="profile-section-label")
            if self.user.get("bio"):
                yield Static(self.user["bio"], classes="profile-bio-label")
            else:
                yield Static("[dim]No bio[/dim]", markup=True, classes="profile-bio-label")

            if current_connections:
                yield Static("[dim]CONNECTED ACCOUNTS[/dim]", markup=True, classes="profile-section-label")
                for connection in current_connections:
                    label = connection.get("label", "No label")
                    url = connection.get("url", "")
                    if label or url:
                        if label and url:
                            yield Static(f"[link]{label}[/link] [dim]{url}[/dim]", markup=True, classes="profile-connection-item")
                        elif label:
                            yield Static(f"[link]{label}[/link]", markup=True, classes="profile-connection-item")
                        elif url:
                            yield Static(f"[dim]{url}[/dim]", markup=True, classes="profile-connection-item") 

            yield Static(f"[dim]Member since {member_since}[/dim]", markup=True, classes="profile-member-since")
            
            if not is_self:
                yield Static("[dim]NOTE (only visible to you)[/dim]", markup=True, classes="profile-section-label")
                yield Input(value=note, placeholder="Add note about this user...", id="profile-note-input")
                yield Button("Save Note", id="save-note-button")
            
            if is_self:
                yield Button("Edit Profile", id=f"member-{self.user['id']}", classes="profile-edit-button")
            else:
                if already_friends:
                    yield Static("Already friends", classes="profile-friend-status")
                
                elif request_pending:
                    yield Static("Request pending", id="add-friend-profile-button", disabled=True)

                else:
                    yield Button("+ Add Friend", id="add-friend-profile-button")

    def on_button_pressed(self, event: Button.Pressed):
        button_id = event.button.id
        if button_id == "add-friend-profile-button":
            current_user = auth.get_current_user()
            success, result = db.send_friend_request(current_user["id"], self.user["id"])
            error = self.query_one("#screen-error", Label)
            if success:
                event.button.disabled = True
                event.button.label = "Request Sent"

            else:
                error.remove_class("hidden")
                error.update(result)

        elif button_id and button_id.startswith("member-"):
            user_id = button_id.split("-", 1)[1]
            if user_id == str(auth.get_current_user()["id"]):
                self.app.push_screen(EditProfile(self.user), self.after_profile_edit)
                
            else:
                self.dismiss()

        elif button_id == "save-note-button":
            current_user = auth.get_current_user()
            note = self.query_one("#profile-note-input", Input).value
            db.set_user_note(current_user["id"], self.user["id"], note)
            self.notify("Note saved", title="Note")

        elif button_id == "profile-close-button":
            self.dismiss()

        else:
            self.dismiss()

    async def after_profile_edit(self, result):
        if result:
            user = auth.get_current_user()
            auth.current_user = db.get_user_by_id(user["id"])
            main = next(s for s in self.app.screen_stack if isinstance(s, MainScreen))
            await main.refresh_user_info(db.get_user_by_id(user["id"]))
            
            self.notify("Profile updated", title="Profile")

        self.dismiss()


class SearchResult(Widget):
    def __init__(self, message):
        super().__init__()
        self.message = message
        self.add_class("search-result")

    def compose(self) -> ComposeResult:
        name = get_display_name_markup(self.message)
        time = format_timestamp(self.message["created"])
        current_user = auth.get_current_user()

        yield Static(Text.from_markup(f"{name} [dim][{time}][/dim]"), classes="search-result-head")
        
        highlighted_content = highlight_mention(self.message["content"], current_user["username"])
        yield Static(highlighted_content, markup=True, classes="search-result-content")

class FriendCard(Widget):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.add_class("friend-card")

    def compose(self) -> ComposeResult:
        markup_name = f"{get_presence_indicator(self.user)} {get_display_name_markup(self.user)}"

        yield Label(Text.from_markup(f"{markup_name} [dim]@{self.user['username']}[/dim]"), classes="friend-card-name")

class FriendRequestCard(Widget):
    def __init__(self, request):
        super().__init__()
        self.request = request
        self.add_class("friend-request-card")

    def compose(self) -> ComposeResult:
        markup_name = get_display_name_markup(self.request)

        with Horizontal(classes="friend-request-row"):
            yield Label(Text.from_markup(f"{markup_name} [dim]@{self.request['username']}[/dim]"), classes="friend-request-name")
                
            yield Button("✓", id=f"accept-{self.request['id']}", classes="friend-request-accept-button", variant="success")
            yield Button("✗", id=f"decline-{self.request['id']}", classes="friend-request-decline-button", variant="error")


class AddFriendScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        with Container(id="screen-container"):
            yield Label("Add Friend", id="screen-title")
            yield Label("", id="screen-error")
            yield Label("Username", classes="field-label")
            yield Input(placeholder="Enter username...", id="username-input")
            with Horizontal(id="screen-buttons"):
                yield Button("Send Request", id="send-button", variant="primary")
                yield Button("Cancel", id="cancel-button")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "send-button":
            username = self.query_one("#username-input", Input).value.strip().lstrip("@")
            error = self.query_one("#screen-error", Label)
            current_user = auth.get_current_user()

            target = db.get_user_by_username(username)

            if not username:
                error.update("Username cannot be empty.")
                return
            
            if not target:
                error.update("User not found.")
                return
            
            success, result = db.send_friend_request(current_user["id"], target["id"])
            if success:
                self.dismiss(True)
            else:
                error.update(result)

        else:
            self.dismiss(False)


class DMUserPanel(Widget):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.add_class("dm-user-panel")

    def compose(self) -> ComposeResult:
        name = get_display_name(self.user)
        markup_name = get_display_name_markup(self.user)
        accent = get_accent_color(self.user)

        yield Static("", classes=f"dm-panel-banner accent-{accent}")
        yield Static(name[0].upper(), classes="dm-panel-avatar")
        yield Static(Text.from_markup(f"{get_presence_indicator(self.user)} {markup_name}"), classes="dm-panel-name")
        yield Static(f"@{self.user['username']}", classes="dm-panel-username")

        if self.user.get("pronouns"):
            yield Static(self.user["pronouns"], classes="dm-panel-pronouns")
        
        if self.user.get("status"):
            yield Static(self.user["status"], classes=f"dm-panel-status")

        yield Static("", classes="dm-panel-separator")
        yield Static("[dim]ABOUT ME[/dim]", markup=True, classes="dm-panel-section-label")
        bio = self.user.get("bio", "")
        if bio:
            yield Static(bio, classes="dm-panel-bio")
        else:
            yield Static("[dim]No bio[/dim]", markup=True, classes="dm-panel-bio")

        member_since = datetime.fromtimestamp(self.user["created"]).strftime("%b %d, %Y")
        yield Static(f"[dim]Member since {member_since}[/dim]", markup=True, classes="dm-panel-member-since")

        with Container(classes="dm-panel-buttons"):
            yield Button("View Profile", id=f"member-{self.user['id']}", classes="dm-panel-profile-button")
            yield Button("Remove Friend", id=f"removefriend-{self.user['id']}", classes="dm-panel-remove-button")



class EditProfile(ModalScreen):
    def __init__(self, user):
        super().__init__()
        self.user = user

    def compose(self) -> ComposeResult:
        name = get_display_name(self.user)
        markup_name = get_display_name_markup(self.user)
        accent = get_accent_color(self.user)

        with Container(id="edit-profile-container"):
            with Horizontal(id="edit-profile-header"):
                yield Label("Edit Profile", classes="screen-title")
                yield Button("X", id="edit-profile-close-button")
            
            yield Label("", id="edit-profile-error", classes="hidden")
            
            with Container(id="edit-profile-preview", classes=f"edit-profile-preview accent-{accent}"):
                yield Static(name[0].upper(), id="edit-profile-preview-avatar")
                yield Static(Text.from_markup(markup_name), markup=True, id="edit-profile-preview-name")
                if self.user.get("pronouns"):
                    yield Static(self.user["pronouns"], id="edit-profile-preview-pronouns")
            
            yield Label("ABOUT ME", classes="edit-profile-section-label")
            yield Label("Display Name", classes="field-label")
            yield Input(value=self.user.get("display_name", "Your display name"), id="edit-profile-display-name-input")

            yield Label("Pronouns", classes="field-label")
            yield Input(value=self.user.get("pronouns", ""), id="edit-profile-pronouns-input")

            yield Label("Bio (max 256 characters)", classes="field-label")
            yield Input(value=self.user.get("bio", ""), id="edit-profile-bio-input")

            yield Label("Status", classes="field-label")
            yield Input(value=self.user.get("status", ""), id="edit-profile-status-input")

            yield Label("APPEARANCE", classes="edit-profile-section-label")
            yield Label("Name Color", classes="field-label")
            yield Label("Choose a color for your display name.", classes="edit-profile-field-description")
            with Horizontal(classes="edit-profile-color-row"):
                for color in ["white", "cyan", "green", "yellow", "magenta", "red", "blue", "bright_cyan", "bright_green", "bright_yellow", "bright_magenta", "bright_red"]:
                    yield Button(f"A", id= f"name-color-{color}", classes="edit-profile-color-option" + (" edit-profile-color-selected" if self.user.get("name_color") == color else ""))

            yield Label("Profile Accent Color", classes="field-label")
            yield Label("Shown as your profile banner color.", classes="edit-profile-field-description")
            with Horizontal(classes="edit-profile-color-row"):
                for color in ["dark_blue", "dark_green", "dark_red", "dark_magenta", "dark_cyan"]:
                    yield Button(f"A", id= f"accent-color-{color}", classes="edit-profile-accent-option" + (" edit-profile-color-selected" if self.user.get("accent_color", "dark_blue") == color else ""))

            yield Label("CONNECTIONS", classes="edit-profile-section-label")
            yield Static("Each connection has a label and a URL.", classes="edit-profile-field-description")
            raw_connections = self.user.get("connections", [])
            current_connections = json.loads(raw_connections)

            for i in range(5):
                if len(current_connections) > i:
                    connection = current_connections[i]
                else:
                    connection = {}
                with Horizontal(classes="edit-profile-connection-row"):
                    yield Input(value=connection.get("label", ""), classes="edit-profile-connection-label-input", id=f"edit-profile-connection-label-{i}", placeholder=f"Label #{i+1}")
                    yield Input(value=connection.get("url", ""), classes="edit-profile-connection-url-input", id=f"edit-profile-connection-url-{i}", placeholder=f"URL #{i+1}")
                
            with Horizontal(id="edit-profile-buttons"):
                yield Button("Save Changes", id="edit-profile-save-button", variant="primary")
                yield Button("Cancel", id="edit-profile-cancel-button")

    
    async def on_button_pressed(self, event: Button.Pressed):
        button_id = event.button.id
        if button_id and button_id.startswith("name-color-"):
            color = button_id.split("name-color-", 1)[1]

            for color in ["white", "cyan", "green", "yellow", "magenta", "red", "blue", "bright_cyan", "bright_green", "bright_yellow", "bright_magenta", "bright_red"]:
                self.query_one(f"#name-color-{color}", Button).remove_class("edit-profile-color-selected")
            
            event.button.add_class("edit-profile-color-selected")
            return
        
        elif button_id and button_id.startswith("accent-color-"):
            color = button_id.split("accent-color-", 1)[1]
            for color in ["dark_blue", "dark_green", "dark_red", "dark_magenta", "dark_cyan"]:
                self.query_one(f"#accent-color-{color}", Button).remove_class("edit-profile-color-selected")
            
            event.button.add_class("edit-profile-color-selected")
            preview = self.query_one("#edit-profile-preview")
            for color in ["dark_blue", "dark_green", "dark_red", "dark_magenta", "dark_cyan"]:
                preview.remove_class(f"accent-{color}")
            
            preview.add_class(f"accent-{color}")
            return
        
        elif button_id == "edit-profile-close-button":
            self.dismiss()
            return
        
        elif button_id == "edit-profile-cancel-button":
            self.dismiss()
            return

        elif button_id == "edit-profile-save-button":
            error = self.query_one("#edit-profile-error", Label)
            display_name = self.query_one("#edit-profile-display-name-input", Input).value.strip()
            pronouns = self.query_one("#edit-profile-pronouns-input", Input).value.strip()
            bio = self.query_one("#edit-profile-bio-input", Input).value.strip()
            status = self.query_one("#edit-profile-status-input", Input).value.strip()
            
            name_color = ""
            for color in ["white", "cyan", "green", "yellow", "magenta", "red", "blue", "bright_cyan", "bright_green", "bright_yellow", "bright_magenta", "bright_red"]:
                if "edit-profile-color-selected" in self.query_one(f"#name-color-{color}", Button).classes:
                    name_color = color
                    break

            accent_color = self.user.get("accent_color", "dark_blue")
            for color in ["dark_blue", "dark_green", "dark_red", "dark_magenta", "dark_cyan"]:
                if "edit-profile-color-selected" in self.query_one(f"#accent-color-{color}", Button).classes:
                    accent_color = color
                    break
            
            connections = []
            for i in range(5):
                label = self.query_one(f"#edit-profile-connection-label-{i}", Input).value.strip()
                url = self.query_one(f"#edit-profile-connection-url-{i}", Input).value.strip()
                if label or url:
                    connections.append({"label": label, "url": url})
            
            success, result = db.update_profile(self.user["id"], display_name=display_name, pronouns=pronouns, bio=bio, status=status, name_color=name_color, accent_color=accent_color, connections=connections)
            if success:
                self.dismiss(True)
            else:
                error.remove_class("hidden")
                error.update(result)


class SettingsScreen(ModalScreen):
    def __init__(self, user, dm_notifications, mention_notifications, compact_mode):
        super().__init__()
        self.user = user
        self.active_tab = "account"
        self.dm_notifications = dm_notifications
        self.mention_notifications = mention_notifications
        self.compact_mode = compact_mode
        self.theme = db.get_user_settings(user["id"]).get("theme", "dark")

    def compose(self) -> ComposeResult:
        with Container(id="settings-container"):
            with Container(id="settings-navigation"):
                yield Label("Settings", classes="settings-title")
                yield Button("Account", id="settings-navigation-account", classes="settings-navigation-item settings-navigation-active")
                yield Button("Notifications", id="settings-navigation-notifications", classes="settings-navigation-item")
                yield Button("Appearance", id="settings-navigation-appearance", classes="settings-navigation-item")
                yield Button("Close", id="settings-close-button")

            with ScrollableContainer(id="settings-content-account", classes="settings-content"):
                yield Label("ACCOUNT", classes="settings-section-title")

                with Container(classes="settings-space"):
                    yield Label("PROFILE", classes="settings-section-label")
                    yield Static("Edit your profile information, including display name, pronouns, bio, status, name color, accent color, and connected accounts.", classes="settings-section-description")
                    yield Button("Edit Profile", id=f"member-{self.user['id']}", variant="primary")

                with Container(classes="settings-space"):
                    yield Label("CHANGE USERNAME", classes="settings-section-label")
                    yield Label("Username", classes="field-label")
                    yield Input(value=self.user.get("username", ""), id="settings-username-input")
                    yield Label("", id="settings-username-error", classes="hidden settings-error-label")
                    yield Button("Change Username", id="settings-change-username-button", variant="primary")

                with Container(classes="settings-space"):
                    yield Label("CHANGE PASSWORD", classes="settings-section-label")
                    yield Label("Current Password", classes="field-label")
                    yield Input(placeholder="••••••••", password=True, id="settings-current-password-input")
                    yield Label("New Password", classes="field-label")
                    yield Input(placeholder="••••••••", password=True, id="settings-new-password-input")
                    yield Label("", id="settings-password-error", classes="hidden settings-error-label")
                    yield Button("Change Password", id="settings-change-password-button", variant="primary")

                with Container(classes="settings-space"):
                    yield Label("DANGER ZONE", classes="settings-section-label")
                    yield Static("Delete your account permanently. (after clicking you will be asked to confirm)", classes="settings-section-description")
                    yield Button("Delete Account", id="settings-delete-account-button", variant="error")

                with Container(id="settings-delete-confirmation", classes="settings-space hidden"):
                    yield Label("Confirm Account Deletion", classes="settings-section-label")
                    yield Label("Enter your password to confirm:", classes="field-label")
                    yield Input(placeholder="••••••••", password=True, id="settings-delete-password-input")
                    yield Label("", id="settings-delete-error", classes="hidden settings-error-label")
                    with Horizontal(classes="settings-delete-buttons"):
                        yield Button("Confirm Deletion", id="settings-confirm-delete-button", variant="error")
                        yield Button("Cancel", id="settings-cancel-delete-button")
                    
            with ScrollableContainer(id="settings-content-notifications", classes="settings-content hidden"):
                yield Label("NOTIFICATIONS", classes="settings-section-title")

                with Container(classes="settings-space"):
                    yield Label("MESSAGE NOTIFICATIONS", classes="settings-section-label")
                    
                    with Horizontal(classes="settings-row"):
                        with Container(classes="settings-row-text"):
                            yield Label("Direct Messages Notifications", classes="settings-row-label")
                            yield Static("Get notified for new messages in your DMs.", classes="settings-row-description")
                        yield Button("On" if self.dm_notifications else "Off", id="settings-toggle-dm", classes="settings-toggle" + (" settings-toggle-on" if self.dm_notifications else "")) 

                    with Horizontal(classes="settings-row"):
                        with Container(classes="settings-row-text"):
                            yield Label("Mention Notifications", classes="settings-row-label")
                            yield Static("Get notified when someone mentions you in a server.", classes="settings-row-description")
                        yield Button("On" if self.mention_notifications else "Off", id="settings-toggle-mention", classes="settings-toggle" + (" settings-toggle-on" if self.mention_notifications else ""))                    

            with ScrollableContainer(id="settings-content-appearance", classes="settings-content hidden"):
                yield Label("APPEARANCE", classes="settings-section-title")

                with Container(classes="settings-space"):
                    yield Label("THEME", classes="settings-section-label")
                    
                    with Horizontal(classes="settings-row"):
                        with Container(classes="settings-row-text"):
                            yield Label("Color Theme", classes="settings-row-label")
                            yield Static("Choose between dark and light mode.", classes="settings-row-description")
                        yield Button("Dark" if self.theme == "dark" else "Light", id="settings-toggle-theme", classes="settings-toggle" + (" settings-toggle-on" if self.theme == "dark" else ""))
                
                with Container(classes="settings-space"):
                    yield Label("CHAT APPEARANCE", classes="settings-section-label")

                    with Horizontal(classes="settings-row"):
                        with Container(classes="settings-row-text"):
                            yield Label("Compact Mode", classes="settings-row-label")
                            yield Static("Messages will show with a more compact layout.", classes="settings-row-description")
                        yield Button("On" if self.compact_mode else "Off", id="settings-toggle-compact", classes="settings-toggle" + (" settings-toggle-on" if self.compact_mode else ""))
                    
                    
    def switch_tab(self, tab):
        for tabb in ["account", "notifications", "appearance"]:
            content = self.query_one(f"#settings-content-{tabb}")
            nav_button = self.query_one(f"#settings-navigation-{tabb}", Button)
            if tabb == tab:
                content.remove_class("hidden")
                nav_button.add_class("settings-navigation-active")
                
            else:
                content.add_class("hidden")
                nav_button.remove_class("settings-navigation-active")
            
            self.active_tab = tab
    
    def on_button_pressed(self, event: Button.Pressed):
        button_id = event.button.id

        if button_id == "settings-navigation-account":
            self.switch_tab("account")
        elif button_id == "settings-navigation-notifications":
            self.switch_tab("notifications")
        elif button_id == "settings-navigation-appearance":
            self.switch_tab("appearance")
        
        elif button_id == "settings-close-button":
            self.dismiss({"dm_notifications": self.dm_notifications, "mention_notifications": self.mention_notifications, "compact_mode": self.compact_mode, "theme": self.theme})

        elif button_id and button_id.startswith("member-"):
            user_id = button_id.split("-", 1)[1]
            if user_id == str(auth.get_current_user()["id"]):
                user = db.get_user_by_id(auth.get_current_user()["id"])
                self.app.push_screen(EditProfile(user), self.after_profile_edit)

        elif button_id == "settings-change-username-button":
            new_username = self.query_one("#settings-username-input", Input).value.strip().lstrip("@")
            success, result = auth.change_username(new_username)
            error = self.query_one("#settings-username-error", Label)
            if success:
                self.query_one("#settings-username-error", Label).update("")
                self.query_one("#settings-username-error", Label).add_class("hidden")
                self.after_username_edit(True)

            else:
                error.update(result)
                error.remove_class("hidden")
            
        elif button_id == "settings-change-password-button":
            old_password = self.query_one("#settings-current-password-input", Input).value
            new_password = self.query_one("#settings-new-password-input", Input).value
            success, result = auth.change_password(old_password, new_password)
            error = self.query_one("#settings-password-error", Label)
            if success:
                self.notify("Password changed successfully", title="Password")
                self.query_one("#settings-password-error", Label).update("")
                self.query_one("#settings-password-error", Label).add_class("hidden")

            else:
                error.update(result)
                error.remove_class("hidden")

        elif button_id == "settings-delete-account-button":
            self.query_one("#settings-delete-confirmation", Container).remove_class("hidden")
        
        elif button_id == "settings-cancel-delete-button":
            self.query_one("#settings-delete-confirmation", Container).add_class("hidden")
            self.query_one("#settings-delete-password-input", Input).value = ""
            self.query_one("#settings-delete-error", Label).update("")
            self.query_one("#settings-delete-error", Label).add_class("hidden")

        elif button_id == "settings-confirm-delete-button":
            password = self.query_one("#settings-delete-password-input", Input).value
            success, result = auth.delete_account(password)
            error = self.query_one("#settings-delete-error", Label)
            if success:
                self.dismiss("delete")
            else:
                error.update(result)
                error.remove_class("hidden")

        elif button_id == "settings-toggle-dm":
            self.dm_notifications = not self.dm_notifications
            if self.dm_notifications:
                event.button.label = "On"
                event.button.add_class("settings-toggle-on")
            else:
                event.button.label = "Off"
                event.button.remove_class("settings-toggle-on")
        
        elif button_id == "settings-toggle-mention":
            self.mention_notifications = not self.mention_notifications
            if self.mention_notifications:
                event.button.label = "On"
                event.button.add_class("settings-toggle-on")
            else:
                event.button.label = "Off"
                event.button.remove_class("settings-toggle-on")

        elif button_id == "settings-toggle-compact":
            self.compact_mode = not self.compact_mode
            if self.compact_mode:
                event.button.label = "On"
                event.button.add_class("settings-toggle-on")
            else:
                event.button.label = "Off"
                event.button.remove_class("settings-toggle-on")

        elif button_id == "settings-toggle-theme":
            self.theme = "light" if self.theme == "dark" else "dark"
            if self.theme == "light":
                self.app.add_class("light-mode")
            else:
                self.app.remove_class("light-mode")

            if self.theme == "dark":
                event.button.label = "Dark"
                event.button.add_class("settings-toggle-on")
            else:
                event.button.label = "Light"
                event.button.remove_class("settings-toggle-on")

    async def after_profile_edit(self, result):
        if result:
            user = auth.get_current_user()
            auth.current_user = db.get_user_by_id(user["id"])
            main = next(s for s in self.app.screen_stack if isinstance(s, MainScreen))
            await main.refresh_user_info(db.get_user_by_id(user["id"]))
            
            self.notify("Profile updated", title="Profile")

    async def after_username_edit(self, result):
        if result:
            user = auth.get_current_user()
            auth.current_user = db.get_user_by_id(user["id"])
            main = next(s for s in self.app.screen_stack if isinstance(s, MainScreen))
            await main.refresh_user_info(db.get_user_by_id(user["id"]))
            
            self.notify("Username updated", title="Username")



class ServerOptionsScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        with Container(id="screen-container"):
            yield Label("Add Server", id="screen-title")
            yield Label("What do you want to do?", classes="screen-subtitle")
            yield Button("Create a server", id="create-server-button", variant="primary")
            yield Button("Join a server", id="join-server-button")
            yield Button("Cancel", id="cancel-button")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "create-server-button":
            self.dismiss("create")
        elif event.button.id == "join-server-button":
            self.dismiss("join")
        else:
            self.dismiss()


class CreateServerScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        with Container(id="screen-container"):
            yield Label("Create Server", id="screen-title")
            yield Label("", id="screen-error")
            yield Label("Server Name", classes="field-label")
            yield Input(placeholder="Enter server name...", id="server-name-input")
            yield Label("Icon (single character) - optional", classes="field-label")
            yield Input(placeholder="Enter icon...", id="server-icon-input")
            yield Label("Description - optional", classes="field-label")
            yield Input(placeholder="Enter description...", id="server-description-input")
            with Horizontal(id="screen-buttons"):
                yield Button("Create", id="create-button", variant="primary")
                yield Button("Cancel", id="cancel-button")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "create-button":
            name = self.query_one("#server-name-input", Input).value.strip()
            icon = self.query_one("#server-icon-input", Input).value.strip()
            description = self.query_one("#server-description-input", Input).value.strip()
            error = self.query_one("#screen-error", Label)

            if not name:
                error.update("Server name cannot be empty.")
                return
            
            if len(name) < 3 or len(name) > 20:
                error.update("Server name must be between 3 and 20 characters.")
                return
            
            if not icon:
                icon = name[0].upper()

            user = auth.get_current_user()
            success, result = db.create_server(user["id"], name, icon, description=description)
            if success:
                self.dismiss(result)
            else:
                error.update(result)

        else:
            self.dismiss()
            return


class JoinServerScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        with Container(id="screen-container"):
            yield Label("Join Server", id="screen-title")
            yield Label("", id="screen-error")
            yield Label("Invite Code", classes="field-label")
            yield Input(placeholder="Enter invite code...", id="invite-code-input")
            with Horizontal(id="screen-buttons"):
                yield Button("Join", id="join-button", variant="primary")
                yield Button("Cancel", id="cancel-button")
            
    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "join-button":
            invite_code = self.query_one("#invite-code-input", Input).value.strip()
            error = self.query_one("#screen-error", Label)

            server = db.get_server_by_invite_code(invite_code)

            if not invite_code:
                error.update("Invite code cannot be empty.")
                return
            
            if not server:
                error.update("Invalid invite code.")
                return
            
            user = auth.get_current_user()
            success, result = db.join_server(user["id"], server["id"])
            if success:
                self.dismiss(server["id"])
            else:
                error.update(result)

        else:
            self.dismiss()
            return
        
    
class InviteCodePopup(ModalScreen):
    def __init__(self, invite_code, server_name):
        super().__init__()
        self.invite_code = invite_code
        self.server_name = server_name

    def compose(self) -> ComposeResult:
        with Container(id="screen-container"):
            yield Label(f"Invite Code", id="screen-title")
            yield Label(f"Share this code to invite others to {self.server_name}", classes="screen-subtitle")
            yield Label(self.invite_code, id="invite-code-label")
            yield Button("Close", id="close-button", variant="primary")
        
    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss()
            

class CreateChannelScreen(ModalScreen):
    def __init__(self, server_id):
        super().__init__()
        self.server_id = server_id

    def compose(self) -> ComposeResult:
        with Container(id="screen-container"):
            yield Label("Create Channel", id="screen-title")
            yield Label("", id="screen-error")
            yield Label("Channel Name", classes="field-label")
            yield Input(placeholder="Enter channel name...", id="channel-name-input")
            yield Label("Description - optional", classes="field-label")
            yield Input(placeholder="Enter description...", id="channel-description-input") 
            with Horizontal(id="screen-buttons"):
                yield Button("Create", id="create-button", variant="primary")
                yield Button("Cancel", id="cancel-button")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "create-button":
            name = self.query_one("#channel-name-input", Input).value.strip()
            description = self.query_one("#channel-description-input", Input).value.strip()
            error = self.query_one("#screen-error", Label)

            if not name:
                error.update("Channel name cannot be empty.")
                return
            
            name = name.lower().replace(" ", "-")
            success, result = db.create_channel(self.server_id, name, description=description)
            if success:
                self.dismiss(result)
            else:
                error.update(result)

        else:
            self.dismiss()
            return
