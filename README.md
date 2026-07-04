# Telegram Photo Forwarder Bot (Userbot)

An advanced Telegram Userbot built with Python and Telethon that automatically scrapes historical photos from source channels, forwards them to a target channel, and continues to monitor live for new images.

Features built-in rate-limit handling, humanized randomized delays, album batching, and strict account safeguard limits to protect against Telegram's anti-spam algorithms.

## Features
- **Historical Scraping:** Scans source channels from oldest to newest.
- **Comment Support:** Automatically digs into linked discussion groups to find photos posted in the comments.
- **Album Batching:** Bundles up to 10 photos into a single album to reduce API requests.
- **State Saving:** Uses a local `.json` file to remember exactly which messages have been forwarded. It safely resumes if the script crashes or is restarted.
- **Anti-Spam Protections:** Automatically pauses for a configurable number of hours if a hard forward limit is reached.
- **FloodWait Handling:** Automatically catches Telegram API timeouts and waits them out dynamically.
- **Humanized Delays:** Implements randomized sleep timers between sends to mimic human behavior.

## Installation & Setup (Local)

1. **Clone the repository:**
   ```bash
   git clone git@github.com:MehranMahjour/Telegram-photo-forwarder.git
