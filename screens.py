import os
from datetime import datetime

from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.widgets import Input, Button, Static, Label
from textual.widget import Widget
from textual.containers import Horizontal, Container, ScrollableContainer

import auth
import db
from utils import format_timestamp, day_label, should_compact


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
                with Horizontal():
                    yield Label(f"", id="username-label")
                    yield Button("L", id="logout-button")

        with Container(id="chat-container"):
            yield Label("", id="chat-title")
            with Horizontal(id="dm-navbar"):
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
            yield Label("Members", id="members-title")
            with ScrollableContainer(id="members-list"):
                pass

        
    async def on_mount(self):
        user = auth.get_current_user()
        self.query_one("#username-label", Label).update(f"@{user['username']}")

        if self.active_mode == "dm":
            await self.switch_dm_mode()
        else:
            self.query_one("#dm-navbar").display = False
            await self.load_servers()

        self.set_interval(5, self.refresh_messages)


    async def refresh_messages(self):
        if self.active_server:
            await self.load_members(self.active_server["id"])

        if self.active_mode == "dm":
            if not self.active_dm_user:
                return
            user = auth.get_current_user()
            messages = db.get_dm_messages_after(user["id"], self.active_dm_user["id"], self.last_message_id)
        
        elif self.active_mode == "server":
            if not self.active_channel:
                return
            messages = db.get_messages_after(self.active_channel["id"], self.last_message_id)
        
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
            await self.query_one("#messages-container").mount(Message(message, compact=compact))
            prev = message
            
        self.last_message_previous = prev
        self.last_message_day = prev_day

        self.last_message_id = messages[-1]["id"]    

        self.query_one("#messages-container").scroll_end(animate=False)


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

        for channel in channels:
            if self.active_channel and self.active_channel["id"] == channel["id"]:
                classes = "channel-button active-channel"
            else:
                classes = "channel-button"

            await channels_list.mount(Button(f"#\u00a0{channel['name']}", id=f"channel-{channel['id']}", classes=classes))

        await channels_list.mount(Button("+ Add Channel", id=f"add-channel-button", classes="add-channel-button"))

    
    async def load_members(self, server_id):
        members = db.get_server_members(server_id)
        members_list = self.query_one("#members-list")
        await members_list.remove_children()

        for member in members:
            if member["display_name"]:
                name = member["display_name"]
            else:
                name = member["username"]

            await members_list.mount(Button(name, id=f"member-{member['id']}", classes="member-button"))


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
            await self.query_one("#messages-container").mount(Message(message, compact=compact))
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

        if self.active_dm_user.get("display_name"):
            name = self.active_dm_user["display_name"]
        else:
            name = self.active_dm_user["username"]

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
            await self.query_one("#messages-container").mount(Message(message, compact=compact))
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

        await self.query_one("#members-list").remove_children()
        await self.load_dm_friends_view()


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
                if friend["display_name"]:
                    name = friend["display_name"]
                else:
                    name = friend["username"]

                if self.active_dm_user and self.active_dm_user["id"] == friend["id"]:
                    button_classes = "channel-button active-channel"
                else:
                    button_classes = "channel-button"

                await channels_list.mount(Button(name, id=f"dm-{friend['id']}", classes=button_classes))
        
        else:
            await channels_list.mount(Static("No friends yet...", classes="channel-placeholder"))

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
        friend = db.get_user_by_id(user_id)
        if not friend:
            return
        
        if friend["display_name"]:
            name = friend["display_name"]
        else:
            name = friend["username"]
        
        self.active_dm_user = friend
        self.last_message_id = 0
        self.last_message_day = None
        self.last_message_previous = None

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
        
        self.query_one("#members-title", Label).update("")
        await self.query_one("#members-list").remove_children()
        
        await self.query_one("#members-list").mount(DMUserPanel(friend))

        await self.load_dm_messages(friend["id"])

    
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

        
        self.query_one("#chat-title").display = True
        self.query_one("#dm-navbar").display = False
        self.query_one("#input-row").display = True
        self.query_one("#members-container").display = True
        self.query_one("#members-title", Label).update("Members")

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
        
        self.active_channel = channel

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
        self.pending_attachment = None

        await self.load_messages(channel_id)


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
                with open(attachment_path, "rb") as file:
                    attachment_data = file.read()

                    if len(attachment_data) > 50 * 1024 * 1024: # 50 MB
                        self.notify("Attachment is too large. Max size is 50 MB.", title="Error")
                        return

                attachment_name = os.path.basename(attachment_path)
            
            except Exception as e:
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
            await self.query_one("#messages-container").mount(Message(message, compact=compact))
            prev = message
            
        self.last_message_previous = prev
        self.last_message_day = prev_day

        self.last_message_id = messages[-1]["id"]
        self.query_one("#messages-container").scroll_end(animate=False)

        self.pending_attachment = None
        self.query_one("#attach-button", Button).label = "+"

        if self.active_mode == "dm" and self.active_dm_user: #! idk
            self.query_one("#message-input", Input).placeholder = f"Message @{self.active_dm_user['username']}..."

        else:
            self.query_one("#message-input", Input).placeholder = "Type a message..."


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

        elif button_id == "dm-tab-friends":
            self.query_one("#dm-tab-friends", Button).add_class("active-dm-tab")
            self.query_one("#dm-tab-pending", Button).remove_class("active-dm-tab")
            await self.load_dm_friends_view()

        elif button_id == "dm-tab-pending":
            self.query_one("#dm-tab-pending", Button).add_class("active-dm-tab")
            self.query_one("#dm-tab-friends", Button).remove_class("active-dm-tab")
            await self.load_dm_pending_view()

        elif button_id.startswith("sidebar-pending-button"):
            self.query_one("#dm-tab-pending", Button).add_class("active-dm-tab")
            self.query_one("#dm-tab-friends", Button).remove_class("active-dm-tab")
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

        elif button_id == "logout-button":
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

        else:
            return


    
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


class DaySeparator(Widget):
    def __init__(self, label):
        super().__init__()
        self.label = label
        self.add_class("day-separator")

    def compose(self) -> ComposeResult:
        yield Static(self.label, classes="day-separator-label")


class Message(Widget):
    def __init__(self, message, compact=False):
        super().__init__()
        self.message = message
        self.compact = compact
        self.add_class("message")
        if self.compact:
            self.add_class("compact-message")

    def compose(self) -> ComposeResult:
        if self.message.get("display_name"):
            name = self.message["display_name"]
        else:
            name = self.message["username"]

        time = format_timestamp(self.message["created"])

        if not self.compact:
            head = f"[bold]{name}[/bold] [dim][{time}][/dim]"
            yield Static(head, markup=True, classes="message-head")
        
        yield Static(self.message["content"], markup=True, classes="message-content")

        if self.message.get("attachment_name"):
            filename = os.path.basename(self.message["attachment_name"])
            extension = os.path.splitext(filename)[1].lower()
            if extension in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]:
                sub = "Image Attachment" #TODO: maybe show image preview?
            else:
                sub = "Attachment"

            with Horizontal(classes="attachment-card"):
                yield Static(f"{sub} [bold]{filename}[/bold]", markup=True, classes="attachment-label")
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

        if self.user.get("display_name"):
            name = self.user["display_name"]
        else:
            name = self.user["username"]

        member_since = datetime.fromtimestamp(self.user["created"]).strftime("%b %d, %Y")
            
        with Container(id="screen-container"):
            with Horizontal(id="profile-top-row"):
                yield Static("", classes="profile-top-row-separator")
                yield Button("X", classes="profile-close-button")
            yield Label("", id="screen-error", classes="hidden")

            yield Static(name[0].upper(), classes="profile-avatar")
            yield Label(f"[bold]{name}[/bold]", markup=True, classes="profile-name-label")
            yield Label(f"@{self.user['username']}", classes="profile-username-label")

            if self.user.get("bio"): #TODO: later add option to edit bio
                yield Static(self.user["bio"], classes="profile-bio-label")
            else:
                yield Static("[dim]No bio[/dim]", markup=True, classes="profile-bio-label")

            yield Static(f"[dim]Member since {member_since}[/dim]", markup=True, classes="profile-member-since")

            if not is_self:
                if already_friends:
                    yield Static("Already friends", id="profile-friend-status")
                
                elif request_pending:
                    yield Static("Request pending", id="add-friend-profile-button", disabled=True)

                else:
                    yield Button("+ Add Friend", id="add-friend-profile-button")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "add-friend-profile-button":
            current_user = auth.get_current_user()
            success, result = db.send_friend_request(current_user["id"], self.user["id"])
            error = self.query_one("#screen-error", Label)
            if success:
                event.button.disabled = True
                event.button.label = "Request Sent"

            else:
                error.remove_class("hidden")
                error.update(result)

        else:
            self.dismiss()



class FriendCard(Widget):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.add_class("friend-card")

    def compose(self) -> ComposeResult:
        if self.user.get("display_name"):
            name = self.user["display_name"]
        else:
            name = self.user["username"]

        yield Label(f"[bold]{name}[/bold] [dim]@{self.user['username']}[/dim]", markup=True, classes="friend-card-name")

class FriendRequestCard(Widget):
    def __init__(self, request):
        super().__init__()
        self.request = request
        self.add_class("friend-request-card")

    def compose(self) -> ComposeResult:
        if self.request.get("display_name"):
            name = self.request["display_name"]
        else:
            name = self.request["username"]

        with Horizontal(classes="friend-request-row"):
            yield Label(f"[bold]{name}[/bold] [dim]@{self.request['username']}[/dim]", markup=True, classes="friend-request-name")
                
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
        if self.user.get("display_name"):
            name = self.user["display_name"]
        else:
            name = self.user["username"]

        yield Static(name[0].upper(), classes="dm-panel-avatar")
        yield Static(f"[bold]{name}[/bold]", markup=True, classes="dm-panel-name")
        yield Static(f"@{self.user['username']}", classes="dm-panel-username")

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
            yield Label("Icon (emoji or single character) - optional", classes="field-label")
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
