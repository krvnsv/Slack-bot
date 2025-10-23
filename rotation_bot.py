from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import os, re
from dotenv import load_dotenv

load_dotenv()

app = App(token=os.environ['SLACK_BOT_TOKEN'])
SLACK_APP_TOKEN = os.environ['SLACK_APP_TOKEN']

# ------------------------------ Recruiter rotation ------------------------------
recruiters = []   # list of <@USERID>
queue_pointer = 0

def get_next_recruiter(poster_id):
    global queue_pointer
    if not recruiters:
        return None
    n = len(recruiters)
    for i in range(n):
        idx = (queue_pointer + i) % n
        if recruiters[idx] != poster_id:
            queue_pointer = (idx + 1) % n
            return recruiters[idx]
    return None

def valid_number(text):
    return re.match(r"^([A-Za-z ]+) (\d{8,15})( .*)?$", text)

def add_recruiter(uid):
    if uid not in recruiters:
        recruiters.append(uid)
        return True
    return False

def remove_recruiter(uid):
    if uid in recruiters:
        recruiters.remove(uid)
        return True
    return False

# ------------------------------ Main event listener ------------------------------
@app.event("message")
def handle_message(event, say, client):
    text = event.get("text","")
    user = event.get("user")
    channel = event.get("channel")
    ts = event.get("ts")

    if not text or not user: return

    # --- command: add recruiter
    if text.startswith("add_new_recruiter"):
        m = re.search(r"<@(\w+)>", text)
        if m:
            uid = m.group(1)
            if add_recruiter(uid):
                say(f"✅ <@{uid}> added to queue.")
            else:
                say(f"⚠️ <@{uid}> already in queue.")
        return

    # --- command: remove recruiter
    if text.startswith("remove_recruiter"):
        m = re.search(r"<@(\w+)>", text)
        if m:
            uid = m.group(1)
            if remove_recruiter(uid):
                say(f"♻️ <@{uid}> removed from queue.")
            else:
                say(f"⚠️ <@{uid}> not in queue.")
        return

    # --- assign phone number
    if valid_number(text):
        assignee = get_next_recruiter(user)
        if assignee:
            client.reactions_add(channel=channel, name="white_check_mark", timestamp=ts)
            say(text=f"Assigned to <@{assignee}>", thread_ts=ts)
        else:
            say("⚠️ No recruiters available.", thread_ts=ts)

# ------------------------------ Run ------------------------------
if __name__ == "__main__":
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
