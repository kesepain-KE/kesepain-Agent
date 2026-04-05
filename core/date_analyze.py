import subprocess
import sys
from pathlib import Path


root_dir = Path(__file__).resolve().parent.parent
payload = sys.argv[1]


if payload == "type:start":
    chat_output = subprocess.run(
        [sys.executable, str(root_dir / "core" / "chat.py"), "type:start"],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    if chat_output == "type:runed":
        memory_output = subprocess.run(
            [sys.executable, str(root_dir / "core" / "memory.py"), "type:read"],
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        if memory_output == "type:runed":
            subprocess.run([sys.executable, str(root_dir / "core" / "agent.py"), "type:start"])


if payload == "type:continue":
    memory_continue_output = subprocess.run(
        [sys.executable, str(root_dir / "core" / "memory.py"), "type:continue"],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    if memory_continue_output == "type:runed":
        chat_output = subprocess.run(
            [sys.executable, str(root_dir / "core" / "chat.py"), "type:continue"],
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        if chat_output == "type:runed":
            memory_read_output = subprocess.run(
                [sys.executable, str(root_dir / "core" / "memory.py"), "type:read"],
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            ).stdout.strip()
            if memory_read_output == "type:runed":
                subprocess.run([sys.executable, str(root_dir / "core" / "agent.py"), "type:continue"])
