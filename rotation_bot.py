from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import os, re, json
from dotenv import load_dotenv

load_dotenv()

app = App(token=os.environ['SLACK_BOT_TOKEN'])
SLACK_APP_TOKEN = os.environ['SLACK_APP_TOKEN']

STATE_FILE = "rotation_state.json"
PHONE_LOG_FILE = "assigned_numbers.txt"

# ------------------------------ State management ------------------------------
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"recruiters": [], "queue_pointer": 0, "priority": {}}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

# Load initial state
state = load_state()

# ------------------------------ Helper functions ------------------------------
def get_display_name(client, user_id):
    try:
        result = client.users_info(user=user_id)
        if result.get("ok"):
            user = result.get("user", {})
            profile = user.get("profile", {})
            # Try display_name first, fallback to real_name
            display_name = profile.get("display_name", "").strip()
            if display_name:
                return display_name
            real_name = profile.get("real_name", "").strip()
            if real_name:
                return real_name
        return user_id
    except Exception as e:
        print(f"Error getting display name for {user_id}: {e}")
        return user_id

# ------------------------------ Number validation ------------------------------
def extract_phone_number(text):
    """
    Extracts a 10-digit phone number from text.
    Returns the phone number if found, None otherwise.
    Looks for exactly 10 consecutive digits anywhere in the text.
    """
    # Find all sequences of digits
    matches = re.findall(r'\d+', text)
    
    for match in matches:
        if len(match) == 10:
            return match
    
    return None

def valid_number_format(text):
    """
    Checks if the message contains a valid 10-digit phone number.
    Returns True if valid, False otherwise.
    """
    return extract_phone_number(text) is not None

def is_phone_number_assigned(phone_number):
    """
    Checks if a phone number has already been assigned.
    Returns True if found in the log file, False otherwise.
    """
    if not os.path.exists(PHONE_LOG_FILE):
        return False
    
    try:
        with open(PHONE_LOG_FILE, 'r') as f:
            assigned_numbers = f.read().splitlines()
            return phone_number in assigned_numbers
    except:
        return False

def log_phone_number(phone_number):
    """
    Adds a phone number to the log file.
    """
    try:
        with open(PHONE_LOG_FILE, 'a') as f:
            f.write(phone_number + '\n')
    except Exception as e:
        print(f"Error logging phone number: {e}")

# ------------------------------ Recruiter rotation ------------------------------
def get_next_recruiter(poster_id):
    global state
    
    if not state["recruiters"]:
        return None
    
    # Check if anyone has priority
    for uid, count in state["priority"].items():
        if count > 0 and uid != poster_id and uid in state["recruiters"]:
            state["priority"][uid] -= 1
            if state["priority"][uid] == 0:
                del state["priority"][uid]
            save_state(state)
            return uid
    
    # Normal rotation
    n = len(state["recruiters"])
    current_candidate = state["recruiters"][state["queue_pointer"] % n]
    
    # Check if it's the poster's turn
    if current_candidate == poster_id:
        # Poster is sharing on their turn - give them priority
        if poster_id not in state["priority"]:
            state["priority"][poster_id] = 0
        state["priority"][poster_id] += 1
        
        # Find next recruiter who isn't the poster
        next_idx = (state["queue_pointer"] + 1) % n
        next_candidate = state["recruiters"][next_idx]
        
        if next_candidate != poster_id:
            # Assign to this person, move pointer forward by 2 (skip poster + assignee)
            state["queue_pointer"] = (state["queue_pointer"] + 2) % n
            save_state(state)
            return next_candidate
        
        # If next is also poster (only 1 recruiter total), no one to assign to
        state["queue_pointer"] = (state["queue_pointer"] + 1) % n
        save_state(state)
        return None
    
    # Not poster's turn - normal assignment
    assignee = current_candidate
    state["queue_pointer"] = (state["queue_pointer"] + 1) % n
    save_state(state)
    return assignee

def add_recruiter(uid):
    global state
    if uid not in state["recruiters"]:
        state["recruiters"].append(uid)
        save_state(state)
        return True
    return False

def remove_recruiter(uid):
    global state
    if uid in state["recruiters"]:
        state["recruiters"].remove(uid)
        if uid in state["priority"]:
            del state["priority"][uid]
        # Adjust pointer if needed
        if state["queue_pointer"] >= len(state["recruiters"]) and state["recruiters"]:
            state["queue_pointer"] = 0
        save_state(state)
        return True
    return False

# ------------------------------ Main event listener ------------------------------
@app.event("message")
def handle_message(event, say, client):
    text = event.get("text", "")
    user = event.get("user")
    channel = event.get("channel")
    ts = event.get("ts")

    if not text or not user:
        return

    # --- command: add recruiter
    if text.startswith("add_recruiter"):
        m = re.search(r"<@(\w+)>", text)
        if m:
            uid = m.group(1)
            if add_recruiter(uid):
                client.reactions_add(channel=channel, name="white_check_mark", timestamp=ts)
            else:
                client.reactions_add(channel=channel, name="warning", timestamp=ts)
        return

    # --- command: remove recruiter
    if text.startswith("remove_recruiter"):
        m = re.search(r"<@(\w+)>", text)
        if m:
            uid = m.group(1)
            if remove_recruiter(uid):
                client.reactions_add(channel=channel, name="white_check_mark", timestamp=ts)
            else:
                client.reactions_add(channel=channel, name="warning", timestamp=ts)
        return

    # --- command: show queue
    if text == "show_queue":
        if not state["recruiters"]:
            say("No recruiters in queue.", thread_ts=ts)
            return
        
        lines = ["*Current Queue:*"]
        for i, uid in enumerate(state["recruiters"]):
            name = get_display_name(client, uid)
            # Mark the next person to receive with an arrow
            if i == state["queue_pointer"]:
                lines.append(f"{i+1}. {name} ← next")
            else:
                lines.append(f"{i+1}. {name}")
        
        # Show priority if anyone has it
        if state["priority"]:
            lines.append("\n*Priority:*")
            for uid, count in state["priority"].items():
                if uid in state["recruiters"]:  # Only show if still a recruiter
                    name = get_display_name(client, uid)
                    lines.append(f"• {name}: {count}")
        
        say("\n".join(lines), thread_ts=ts)
        return

    # --- assign phone number (check for 10-digit number anywhere in message)
    if valid_number_format(text):
        phone_number = extract_phone_number(text)
        
        # Check if phone number was already assigned
        if is_phone_number_assigned(phone_number):
            try:
                client.reactions_add(channel=channel, name="x", timestamp=ts)
            except:
                pass
            say(text=f"Phone number {phone_number} was already assigned.", thread_ts=ts)
            return
        
        # Assign to next recruiter
        assignee = get_next_recruiter(user)
        if assignee:
            # Log the phone number
            log_phone_number(phone_number)
            client.reactions_add(channel=channel, name="white_check_mark", timestamp=ts)
            say(text=f"Assigned to <@{assignee}>", thread_ts=ts)
        else:
            say("No recruiters available.", thread_ts=ts)
        return
    
    # --- Everything else is invalid format
    try:
        client.reactions_add(channel=channel, name="x", timestamp=ts)
    except:
        pass
    say(
        text="Your message is in incorrect format. Please enter command again in format:\n"
            "\n"
             "*John Doe 7777777777 optional comment*\n"
             "\n"
             "(Phone number must be exactly 10 digits)",
        thread_ts=ts
    )

# ------------------------------ Run ------------------------------
if __name__ == "__main__":
    SocketModeHandler(app, SLACK_APP_TOKEN).start()