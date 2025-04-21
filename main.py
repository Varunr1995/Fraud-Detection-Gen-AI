import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils import extract_text_from_image, extract_amount, extract_date, extract_city
from db_init import init_db, get_connection

# Load environment variables
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Initialize DB schema
init_db()

# Setup Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"🤖 Bot is ready. Logged in as {bot.user}")


@bot.command(name="upload")
async def upload_receipt(ctx):
    await ctx.send("📎 Please upload your receipt image(s) (JPG/JPEG). You can upload multiple.")


@bot.event
async def on_message(message):
    await bot.process_commands(message)
    if message.author.bot:
        return

    if bot.user.mentioned_in(message):
        await message.channel.send("👋 Need to verify a receipt? Use `!upload`.")

    if message.attachments:
        for att in message.attachments:
            if not att.filename.lower().endswith((".jpg", ".jpeg")):
                continue

            await message.channel.send(f"📥 Processing **{att.filename}**...")
            path = f"temp_{att.filename}"
            await att.save(path)

            try:
                # Extract text from image
                text = extract_text_from_image(path)
                print("\n===== OCR TEXT =====\n", text, "\n===================\n")

                # Extract details
                amount = extract_amount(text)
                date = extract_date(text)
                city = extract_city(text)

                if not all([amount, date, city]):
                    missing = []
                    if not amount: missing.append("amount")
                    if not date: missing.append("date")
                    if not city: missing.append("city")
                    await message.channel.send(f"❌ Could not extract: {', '.join(missing)}")
                    continue

                # Send result
                await message.channel.send(
                    f"🧾 **{att.filename}** — Verified ✅\n"
                    f"- Amount: {amount}\n"
                    f"- Date: {date}\n"
                    f"- City: {city}"
                )

                # Save to DB
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO receipts (user_id, amount, date, city, image_path) VALUES (?,?,?,?,?)",
                        (str(message.author.id), amount, date, city, path)
                    )
                    conn.commit()
                    conn.close()
                    await message.channel.send("✅ Your receipt is verified and pushed to approval")
                except Exception as db_err:
                    await message.channel.send(f"❌ Your receipt is rejected, please upload a valid receipt: {db_err}")

            except Exception as e:
                await message.channel.send(f"❌ Error: {e}")

            finally:
                if os.path.exists(path):
                    os.remove(path)


bot.run(DISCORD_BOT_TOKEN)
