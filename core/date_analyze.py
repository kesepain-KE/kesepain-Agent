import subprocess
import sys
from pathlib import Path


root_dir = Path(__file__).resolve().parent.parent
payload = sys.argv[1]


def run_hidden(path, arg):
    result = subprocess.run(
        [sys.executable, str(path), arg],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


if payload == "type:start":
    chat_output = run_hidden(root_dir / "core" / "chat.py", "type:start")
    if chat_output == "type:exit":
        sys.exit(0)
    run_hidden(root_dir / "core" / "memory.py", "type:read")
    subprocess.run([sys.executable, str(root_dir / "core" / "agent.py"), "type:start"])

if payload == "type:continue":
    run_hidden(root_dir / "core" / "memory.py", "type:continue")
    chat_output = run_hidden(root_dir / "core" / "chat.py", "type:continue")
    if chat_output == "type:exit":
        sys.exit(0)
    run_hidden(root_dir / "core" / "memory.py", "type:read")
    subprocess.run([sys.executable, str(root_dir / "core" / "agent.py"), "type:continue"])
