# main.py — entry point. Creates the Bot and starts the event loop.
from bot import Bot
from settings import DISCORD_TOKEN

if __name__ == "__main__":
    Bot().run(DISCORD_TOKEN)
