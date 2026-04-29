from textual.app import App

import db
import auth
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

    async def on_shutdown(self) -> None:
        user = auth.get_current_user()
        if user:
            db.update_presence(user["id"], "offline")
        
        auth.logout()


if __name__ == "__main__":
    db.init_db()
    CLIMessage().run()
