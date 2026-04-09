import os

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Input, Button, Static, Label
from textual.widget import Widget
from textual.containers import Horizontal, Container, ScrollableContainer

import auth
import db
from utils import format_timestamp


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
                self.app.push_screen("main")

            else:
                error.update(message)

        elif event.button.id == "register-button":
            success, message = auth.register(username, password)
            if success:
                auth.login(username, password)
                error.update("")
                self.app.push_screen("main")

            else:
                error.update(message)


class MainScreen(Screen):
    def __init__(self):
        super().__init__()
        self.active_server = None
        self.active_channel = None
        self.last_message_id = 0
        self.pending_attachment = None

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
                yield Label(f"", id="username-label")

        with Container(id="chat-container"):
            yield Label("", id="chat-title")
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
        await self.load_servers()
        self.set_interval(5, self.refresh_messages)


    async def refresh_messages(self):
        if not self.active_channel:
            return
        
        messages = db.get_messages_after(self.active_channel["id"], self.last_message_id)
        if not messages:
            return

        for message in messages:
            await self.query_one("#messages-container").mount(Message(message))
            self.last_message_id = message["id"]

        self.query_one("#messages-container").scroll_end(animate=False)


    async def load_servers(self):
        user = auth.get_current_user()
        servers = db.get_user_servers(user["id"])
        servers_container = self.query_one("#servers-container")
        await servers_container.remove_children()

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

            await channels_list.mount(Button(f"# {channel['name']}", id=f"channel-{channel['id']}", classes=classes))

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
            await members_list.mount(Label(name, classes="member-label"))


    async def load_messages(self, channel_id):
        messages = db.get_channel_messages(channel_id)
        messages_container = self.query_one("#messages-container")
        await messages_container.remove_children()

        channel = self.active_channel
        await messages_container.mount(Static(f"This is the beginning of # {channel["name"]}", classes="channel-start-placeholder"))

        for message in messages:
            await messages_container.mount(Message(message))

        if messages:
            self.last_message_id = messages[-1]["id"]
        else:
            self.last_message_id = 0

        messages_container.scroll_end(animate=False)

    
    async def switch_server(self, server_id): #! Check thisssssssssssss!!!!
        server = db.get_server_by_id(server_id)
        
        self.active_server = server
        self.active_channel = None
        self.last_message_id = 0

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
        self.pending_attachment = None

        await self.load_messages(channel_id)


    async def send_message(self, content, attachment_path=None):
        if not self.active_channel:
            return
        
        user = auth.get_current_user()
        
        attachment_data = None
        attachment_name = None
        if attachment_path:
            try:
                with open(attachment_path, "rb") as file:
                    attachment_data = file.read()

                attachment_name = os.path.basename(attachment_path)
            
            except Exception as e:
                pass

        success, result = db.send_message(self.active_channel["id"], user["id"], content, attachment_data=attachment_data, attachment_name=attachment_name)
        if not success:
            return
        
        messages = db.get_messages_after(self.active_channel["id"], self.last_message_id)
        for message in messages:
            await self.query_one("#messages-container").mount(Message(message))
            self.last_message_id = message["id"]

        self.query_one("#messages-container").scroll_end(animate=False)

        self.pending_attachment = None
        
        if self.pending_attachment:
            filename = os.path.basename(self.pending_attachment)
            self.query_one("#message-input", Input).placeholder = f"[Attached: {filename}] Type a message..."
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
            self.app.push_screen(Attachment(), self.attachment_selected)

        elif button_id.startswith("download-"):
            message_single = event.button.parent.parent

            if isinstance(message_single, Message):
                data = message_single.message.get("attachment_data")
                filename = message_single.message.get("attachment_name")
                
                self.app.push_screen(DownloadScreen(filename, data))
    

    
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
        if self.pending_attachment:
            filename = os.path.basename(self.pending_attachment)
            self.query_one("#message-input", Input).placeholder = f"[Attached: {filename}] Type a message..."
        else:
            self.query_one("#message-input", Input).placeholder = "Type a message..."


class Message(Widget):
    def __init__(self, message):
        super().__init__()
        self.message = message
        self.add_class("message")

    def compose(self) -> ComposeResult:
        if self.message.get("display_name"):
            name = self.message["display_name"]
        else:
            name = self.message["username"]

        time = format_timestamp(self.message["created"])

        text = f"[b]{name}[/b] [dim][{time}][/dim]\n{self.message['content']}"
        
        yield Static(text, markup=True, classes="message-content")

        if self.message.get("attachment_name"):
            filename = os.path.basename(self.message["attachment_name"])
            extension = os.path.splitext(filename)[1].lower()
            if extension in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]:
                sub = "Image Attachment"
            else:
                sub = "Attachment"

            with Horizontal(classes="attachment-card"):
                yield Static(f"{sub} [bold]{filename}[/bold]", markup=True, classes="attachment-label")
                yield Button("↓", id=f"download-{self.message['id']}", classes="download-button")


    '''
    def __init__(self, message):
        if message.get("display_name"):
            name = message["display_name"]
        else:
            name = message["username"]

        time = format_timestamp(message["created"])

        text = f"[b]{name}[/b] [dim][{time}][/dim]\n{message['content']}"
        
        if message.get("attachment_path"):
            filename =  os.path.basename(message["attachment_path"])
            extension = os.path.splitext(filename)[1].lower()

            if extension in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]:
                text += f"\n[Image Attachment: {filename}]"
            else:
                text += f"\n[Attachment: {filename}]"

        super().__init__(text, markup=True)
        self.add_class("message")
    '''


class Attachment(Screen):
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


class DownloadScreen(Screen):
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



class ServerOptionsScreen(Screen):
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


class CreateServerScreen(Screen):
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


class JoinServerScreen(Screen):
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
        
    
class InviteCodePopup(Screen):
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
            

class CreateChannelScreen(Screen):
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
