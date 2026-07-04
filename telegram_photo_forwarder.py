import asyncio
import json
import os
import random
from telethon import TelegramClient, events, errors
from telethon.tl.functions.channels import GetFullChannelRequest
import re

# ====================================================================
# ⚠️ CONFIGURATION - FILL THESE OUT BEFORE RUNNING
# ====================================================================

# 1. Get your API credentials from https://my.telegram.org
API_ID = 12345678  # Replace with your API ID (integer)
API_HASH = 'your_api_hash_here'  # Replace with your API HASH (string)

# 2. Your public channel username (without @)
TARGET_CHANNEL_USERNAME = 'your_target_channel_username'

# 3. Source channels to forward photos from (public usernames without @)
SOURCE_CHANNELS = [
    'source_channel_1',
    'source_channel_2'
]

# Progress file to track what's been processed (Do not commit this file)
PROGRESS_FILE = 'forwarding_progress.json'

# Batch settings
BATCH_SIZE = 10  # Number of photos to collect before sending as an album

# 👤 HUMAN-LIKE BEHAVIOR DELAYS (Randomized to avoid spam filters)
HUMAN_DELAY_MIN = 4   # Minimum seconds to wait between forwards
HUMAN_DELAY_MAX = 12  # Maximum seconds to wait between forwards

# 🛑 ANTI-SPAM PROTECTIONS
MAX_FORWARDS_PER_RUN = 500  # Max photos to forward before taking a long break
COOLDOWN_SECONDS = 7200     # 2 hours pause when the limit is reached

# ====================================================================
# HELPER FUNCTIONS
# ====================================================================

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_progress(progress):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

async def human_pause():
    """Sleeps for a random duration to mimic human typing/scrolling."""
    delay = random.uniform(HUMAN_DELAY_MIN, HUMAN_DELAY_MAX)
    print(f"  ⏱️ Human pause: relaxing for {delay:.1f} seconds...")
    await asyncio.sleep(delay)

async def send_batch(client, target_channel, batch, batch_type="photos"):
    if not batch:
        return 0
    
    try:
        await client.send_file(
            target_channel,
            [item['photo'] for item in batch],
            caption=[item['caption'] for item in batch]
        )
        print(f"  📦 Forwarded batch of {len(batch)} {batch_type}")
        return len(batch)
        
    except errors.FloodWaitError as e:
        wait_time = e.seconds + 10
        print(f"\n  ⏳ TELEGRAM TIMEOUT HIT! Sleeping for {wait_time}s ({wait_time // 60} mins)...")
        await asyncio.sleep(wait_time)
        print("  ▶️ Resuming...")
        return await send_batch(client, target_channel, batch, batch_type)
        
    except Exception as e:
        print(f"  ❌ Error forwarding batch: {e}. Trying individually...")
        success_count = 0
        for item in batch:
            try:
                await client.send_file(
                    target_channel,
                    item['photo'],
                    caption=item['caption']
                )
                success_count += 1
                await human_pause()
            except errors.FloodWaitError as e2:
                wait_time = e2.seconds + 5
                print(f"  ⏳ TIMEOUT on individual! Sleeping for {wait_time}s...")
                await asyncio.sleep(wait_time)
            except Exception as e2:
                print(f"  ❌ Error forwarding individual photo: {e2}")
        return success_count

# ====================================================================
# MAIN BOT LOGIC
# ====================================================================

async def main():
    progress = load_progress()
    print(f"📂 Loaded progress: {len(progress)} channels tracked")
    
    client = TelegramClient('photo_forwarder_session', API_ID, API_HASH)
    await client.start()
    print("✅ Client connected successfully.")
    
    try:
        target_channel = await client.get_entity(TARGET_CHANNEL_USERNAME)
        print(f"✅ Found target channel: '{target_channel.title}'")
    except Exception as e:
        print(f"❌ Error finding target channel @{TARGET_CHANNEL_USERNAME}: {e}")
        return
    
    discussion_groups = {}
    
    for channel_username in SOURCE_CHANNELS:
        try:
            channel_entity = await client.get_entity(channel_username)
            full_channel = await client(GetFullChannelRequest(channel=channel_entity))
            
            if full_channel.full_chat.linked_chat_id:
                discussion_group = await client.get_entity(full_channel.full_chat.linked_chat_id)
                discussion_groups[channel_username] = {
                    'channel': channel_entity,
                    'discussion': discussion_group
                }
                print(f"✅ Found discussion group for @{channel_username}: '{discussion_group.title}'")
            else:
                discussion_groups[channel_username] = {
                    'channel': channel_entity,
                    'discussion': None
                }
        except Exception as e:
            print(f"⚠️ Error checking @{channel_username}: {e}")
    
    print("\n" + "="*60)
    print("📜 Processing historical photos from all channels...")
    print("="*60 + "\n")
    
    session_forward_count = 0 

    for channel_username in SOURCE_CHANNELS:
        if channel_username not in discussion_groups:
            continue
            
        channel_entity = discussion_groups[channel_username]['channel']
        discussion_group = discussion_groups[channel_username]['discussion']
        
        if channel_username not in progress:
            progress[channel_username] = {
                'last_processed_id': 0, 'processed_messages': [], 'processed_comments': [] 
            }
        
        if 'processed_comments' not in progress[channel_username]:
            progress[channel_username]['processed_comments'] = []
        
        print(f"\n📥 Processing @{channel_username}...")
        last_processed = progress[channel_username]['last_processed_id']
        processed_messages = set(progress[channel_username]['processed_messages'])
        processed_comments = set(progress[channel_username]['processed_comments'])
        
        photos_forwarded = 0
        comments_forwarded = 0
        photo_batch = []
        comment_batch = []
        
        try:
            async for message in client.iter_messages(channel_entity, reverse=True):
                
                if session_forward_count >= MAX_FORWARDS_PER_RUN:
                    print("\n" + "🛑"*30)
                    print(f"ACCOUNT SAFEGUARD TRIGGERED: Reached {MAX_FORWARDS_PER_RUN} forwards.")
                    print(f"Pausing for {COOLDOWN_SECONDS // 3600} hours to keep your account safe...")
                    print("🛑"*30 + "\n")
                    await asyncio.sleep(COOLDOWN_SECONDS)
                    session_forward_count = 0 

                if message.id in processed_messages or message.id <= last_processed:
                    continue
                
                processed_messages.add(message.id)
                progress[channel_username]['last_processed_id'] = message.id
                
                if message.photo:
                    photo_batch.append({
                        'photo': message.photo,
                        'caption': message.text if message.text else "",
                        'message_id': message.id
                    })
                    
                    if len(photo_batch) >= BATCH_SIZE:
                        count = await send_batch(client, target_channel, photo_batch, "photos")
                        photos_forwarded += count
                        session_forward_count += count
                        photo_batch = []
                        
                        progress[channel_username]['processed_messages'] = list(processed_messages)
                        progress[channel_username]['processed_comments'] = list(processed_comments)
                        save_progress(progress)
                        
                        await human_pause()
                
                if discussion_group:
                    try:
                        async for reply in client.iter_messages(
                            discussion_group, reply_to=message.id, limit=100
                        ):
                            if reply.id in processed_comments:
                                continue
                            
                            if reply.photo:
                                processed_comments.add(reply.id)
                                comment_batch.append({
                                    'photo': reply.photo,
                                    'caption': f"💬 Comment: {reply.text if reply.text else ''}",
                                    'message_id': reply.id
                                })
                                
                                if len(comment_batch) >= BATCH_SIZE:
                                    count = await send_batch(client, target_channel, comment_batch, "comment photos")
                                    comments_forwarded += count
                                    session_forward_count += count
                                    comment_batch = []
                                    
                                    progress[channel_username]['processed_messages'] = list(processed_messages)
                                    progress[channel_username]['processed_comments'] = list(processed_comments)
                                    save_progress(progress)
                                    
                                    await human_pause()
                                    
                    except Exception as e:
                        if "message id" not in str(e).lower():
                            print(f"  ⚠️ Error checking comments for post {message.id}: {e}")
                
                if len(processed_messages) % 50 == 0:
                    progress[channel_username]['processed_messages'] = list(processed_messages)
                    progress[channel_username]['processed_comments'] = list(processed_comments)
                    save_progress(progress)
            
            if photo_batch:
                count = await send_batch(client, target_channel, photo_batch, "photos")
                photos_forwarded += count
                session_forward_count += count
                await human_pause()
            
            if comment_batch:
                count = await send_batch(client, target_channel, comment_batch, "comment photos")
                comments_forwarded += count
                session_forward_count += count
                await human_pause()
            
            progress[channel_username]['processed_messages'] = list(processed_messages)
            progress[channel_username]['processed_comments'] = list(processed_comments)
            save_progress(progress)
        
        except Exception as e:
            print(f"❌ Error processing @{channel_username}: {e}")
        
        print(f"✅ @{channel_username}: {photos_forwarded} photos, {comments_forwarded} comment photos")
        save_progress(progress)
    
    print("\n" + "="*60)
    print("✅ Historical processing complete!")
    print("="*60 + "\n")
    
    @client.on(events.NewMessage(chats=SOURCE_CHANNELS))
    async def handler(event):
        sender_chat = await event.get_chat()
        channel_username = sender_chat.username
        
        if channel_username not in progress:
            progress[channel_username] = {
                'last_processed_id': 0, 'processed_messages': [], 'processed_comments': []
            }
        
        if event.id in progress[channel_username]['processed_messages']:
            return
        
        if event.photo:
            try:
                await human_pause()
                await client.send_file(
                    target_channel, event.photo, caption=event.message.text if event.message.text else ""
                )
                print(f"📸 Forwarded new photo from @{channel_username}")
            except errors.FloodWaitError as e:
                print(f"⏳ TIMEOUT: Sleeping for {e.seconds}s...")
                await asyncio.sleep(e.seconds + 5)
                await client.send_file(target_channel, event.photo, caption=event.message.text)
            except Exception as e:
                print(f"❌ Error forwarding: {e}")
        
        progress[channel_username]['processed_messages'].append(event.id)
        progress[channel_username]['last_processed_id'] = event.id
        save_progress(progress)
    
    discussion_group_list = [info['discussion'] for info in discussion_groups.values() if info['discussion']]
    
    if discussion_group_list:
        @client.on(events.NewMessage(chats=discussion_group_list))
        async def comment_handler(event):
            if event.photo and event.is_reply:
                sender_chat = await event.get_chat()
                channel_username = None
                for username, info in discussion_groups.items():
                    if info['discussion'] and info['discussion'].id == sender_chat.id:
                        channel_username = username
                        break
                
                if not channel_username:
                    return
                if event.id in progress[channel_username]['processed_comments']:
                    return
                
                try:
                    await human_pause()
                    await client.send_file(
                        target_channel, event.photo, caption=f"💬 Comment: {event.message.text if event.message.text else ''}"
                    )
                    print(f"📸 Forwarded new comment photo from: '{sender_chat.title}'")
                    progress[channel_username]['processed_comments'].append(event.id)
                    save_progress(progress)
                except errors.FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 5)
                except Exception as e:
                    pass
    
    print("="*60)
    print("🤖 Bot now monitoring for NEW photos...")
    print("="*60)
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Bot stopped by user. Progress saved!")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")