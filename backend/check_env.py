"""One-off check: confirm ANTHROPIC_API_KEY is readable from the environment without ever
printing (or logging) any part of its value."""
import os

from dotenv import load_dotenv

load_dotenv()  # loads backend/.env into the process environment if present

key = os.environ.get("ANTHROPIC_API_KEY")

if not key:
    print("ANTHROPIC_API_KEY: NOT SET")
elif not key.startswith("sk-ant-"):
    print("ANTHROPIC_API_KEY: SET, but does not match the expected 'sk-ant-...' prefix — double check it")
else:
    print("ANTHROPIC_API_KEY: SET (value not shown)")
