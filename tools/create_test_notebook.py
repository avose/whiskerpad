import sys
import os
import random
import json
import time
import subprocess
from pathlib import Path
from uuid import uuid4

def get_fortune_text():
    """Get random text from fortune command, with fallback if not available."""
    try:
        # Try to get fortune text
        result = subprocess.run(['fortune', '-s'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback to simple random phrases if fortune not available
    fallback_texts = [
        "The early bird catches the worm.",
        "A journey of a thousand miles begins with a single step.",
        "When life gives you lemons, make lemonade.",
        "The pen is mightier than the sword.",
        "Actions speak louder than words.",
        "Better late than never.",
        "Don't count your chickens before they hatch.",
        "Every cloud has a silver lining.",
        "Fortune favors the bold.",
        "Good things come to those who wait.",
        "Honesty is the best policy.",
        "If at first you don't succeed, try, try again.",
        "Knowledge is power.",
        "Laughter is the best medicine.",
        "Money doesn't grow on trees.",
        "No pain, no gain.",
        "Practice makes perfect.",
        "Rome wasn't built in a day.",
        "The grass is always greener on the other side.",
        "Time heals all wounds.",
        "You can't judge a book by its cover.",
        "All that glitters is not gold.",
        "A picture is worth a thousand words.",
        "Beauty is in the eye of the beholder.",
        "Curiosity killed the cat.",
        "Don't put all your eggs in one basket.",
        "Easy come, easy go.",
        "Familiarity breeds contempt.",
        "Great minds think alike.",
        "Hope for the best, prepare for the worst.",
    ]
    return random.choice(fallback_texts)

def list_all_entry_ids(nb_dir):
    nb_dir = Path(nb_dir)
    entry_ids = []
    entries_dir = nb_dir / 'entries'
    if not entries_dir.is_dir():
        raise Exception(f"Entries directory not found: {entries_dir}")
    for shard_dir in entries_dir.iterdir():
        if not shard_dir.is_dir():
            continue
        for entry_dir in shard_dir.iterdir():
            if entry_dir.is_dir():
                entry_ids.append(entry_dir.name)
    return entry_ids

def load_entry(nb_dir, eid):
    path = Path(nb_dir) / 'entries' / eid[:2] / eid / 'entry.json'
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_entry(nb_dir, entry):
    path = Path(nb_dir) / 'entries' / entry['id'][:2] / entry['id'] / 'entry.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(entry, f, indent=2)

def create_node(nb_dir, parent_id, text):
    eid = uuid4().hex[:12]
    node_dir = Path(nb_dir) / 'entries' / eid[:2] / eid
    node_dir.mkdir(parents=True, exist_ok=True)

    # Generate random timestamps within the last year
    now = int(time.time())
    year_ago = now - (365 * 24 * 60 * 60)  # 365 days ago
    created_ts = random.randint(year_ago, now)
    updated_ts = random.randint(created_ts, now)  # Updated after created

    entry = {
        'id': eid,
        'parent_id': parent_id,
        'text': [{'content': text}],
        'edit': '',
        'items': [],
        'collapsed': False,
        'created_ts': created_ts,
        'updated_ts': updated_ts,
        'last_edit_ts': None
    }

    with open(node_dir / 'entry.json', 'w', encoding='utf-8') as f:
        json.dump(entry, f, indent=2)

    # Add to parent
    if parent_id:
        parent = load_entry(nb_dir, parent_id)
        parent.setdefault('items', []).append({'type': 'child', 'id': eid})
        save_entry(nb_dir, parent)
    else:
        nb_json = Path(nb_dir) / 'notebook.json'
        nb = {}
        if nb_json.exists():
            with open(nb_json, 'r', encoding='utf-8') as f:
                nb = json.load(f)
        nb.setdefault('root_ids', []).append(eid)
        with open(nb_json, 'w', encoding='utf-8') as f:
            json.dump(nb, f, indent=2)

    return eid

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} /path/to/notebook N")
        print("Note: Install 'fortune' command for better random text (apt install fortune-mod or brew install fortune)")
        sys.exit(1)

    nb_dir = sys.argv[1]
    count = int(sys.argv[2])

    if not os.path.isdir(nb_dir):
        print(f"Error: {nb_dir} is not a directory")
        sys.exit(1)

    # Test fortune availability
    try:
        subprocess.run(['fortune', '--version'], capture_output=True, timeout=2)
        print("Using fortune command for random text")
    except (subprocess.SubprocessError, FileNotFoundError):
        print("Fortune command not found, using fallback random phrases")

    ids = list_all_entry_ids(nb_dir)
    if not ids:
        print("No existing entries found; creating root")
        root_id = create_node(nb_dir, None, get_fortune_text())
        ids.append(root_id)

    for i in range(count):
        parent_id = random.choice(ids)
        fortune_text = get_fortune_text()
        new_id = create_node(nb_dir, parent_id, fortune_text)
        ids.append(new_id)
        if (i + 1) % 100 == 0:
            print(f"Created {i+1} nodes...")

    print("Done creating nodes")

if __name__ == '__main__':
    main()
