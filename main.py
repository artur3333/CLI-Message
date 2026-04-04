from textual.app import App

import db
from screens import LoginScreen, MainScreen


class CLIMessage(App):
    TITLE = "CLI-Message"
    CSS_PATH = "style.tcss"
    SCREENS = {
        "login": LoginScreen,
        "main": MainScreen
    }

    def on_mount(self):
        self.push_screen("login")


if __name__ == "__main__":
    db.init_db()
    CLIMessage().run()
