from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Input, Button, Static, Label
from textual.containers import Horizontal, Container, ScrollableContainer

import auth


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
    def compose(self) -> ComposeResult:
        user = auth.get_current_user()

        with Container(id="servers-container"):
            yield Label(f"1", classes="server-icon")

        with Container(id="channels-container"):
            with ScrollableContainer(id="channels-list"):
                yield Label("Channels", id="channels-title")

            with Container(id="user-info"):
                yield Label(f"@{user['username']}", id="username-label")

        with Container(id="chat-container"):
            with ScrollableContainer(id="messages-container"):
                yield Static("Testttt, Hello Hack Club!", classes="message")
            
            yield Input(placeholder="Type a message...", id="message-input")

        with Container(id="members-container"):
            yield Label("Members", id="members-title")

        
    def on_input_submitted(self, event: Input.Submitted):
        pass
