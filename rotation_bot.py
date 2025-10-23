from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler 
import os
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.environ ['SLACK_BOT_TOKEN']
SLACK_APP_TOKEN = os.environ ['SLACK_APP_TOKEN']
app = App(token=SLACK_BOT_TOKEN)


@app.event("app_mention")
def mention_handler(event, say):
    user = event['user']
    say(f"Hello <@{user}>! I got your mention.")

if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()