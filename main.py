import discord
from discord.ext import commands
import os
import json
import time
import asyncio
from datetime import datetime
import sqlite3
import random




# ================== XP / LEVEL KONFIG ==================

REACTION_ROLE_FILE = "/data/reaction_roles.json"


XP_NAME = "Weedpunkte"
LEVEL_NAME = "Weedstufe"
COIN_NAME = "Kiffer Coins"

XP_EMOJI = "<:weed_punkte:1464315549021507645>"
LEVEL_EMOJI = "<:weed_stufe:1464315589844795434>"
COIN_EMOJI = "<:kiffer_coins:1464315487038083267>"

LEVEL_UP_CHANNEL_ID = 1464296536170037329

last_weekly_reset = None

GUILD_ID = 983743026704826448

# ================== GAMBLING / MINIGAMES ==================

MINIGAME_CHANNEL_ID = 1464627521675984948  # ← HIER deinen Minigame-Kanal eintragen


# ================== BOT SETUP ==================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

class MyBot(commands.Bot):
    async def setup_hook(self):
        self.loop.create_task(weekly_reset_task())
        self.loop.create_task(cleanup_pending_gambles())

bot = MyBot(command_prefix='/', intents=intents)



# ================== KONFIG ==================

BAD_WORDS = [
    "hurensohn","hure","fick","toten","nigger","neger","nigga","niger",
    "fotze","schwuchtel","homo","nuttensohn","nutte","bastard",
    "schlampe","opfer","leck","spasti","behindert","hund","köter",
    "jude","huso","hs","gefickt","lutsch","mongo","wixxer","wichser"
]

WELCOME_CHANNEL_ID = 983743026704826450
AUTO_ROLE_ID = 983752389502836786
WELCOME_IMAGE_URL = "https://media.discordapp.net/attachments/1039293219491565621/1462608302033731680/gaming420.png?format=webp&quality=lossless"
LOG_CHANNEL_ID = 1462152930768589023

# ================== DATENBANK ==================

conn = sqlite3.connect("/data/botdata.db", check_same_thread=False)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 0,
    coins INTEGER DEFAULT 0,
    messages INTEGER DEFAULT 0,
    voice_seconds INTEGER DEFAULT 0,
    total_xp INTEGER DEFAULT 0,
    weekly_xp INTEGER DEFAULT 0,
    weekly_messages INTEGER DEFAULT 0,
    weekly_voice_seconds INTEGER DEFAULT 0
)
""")
conn.commit()

cur.execute("""
CREATE TABLE IF NOT EXISTS active_gambles (
    user_id INTEGER PRIMARY KEY,
    opponent_id INTEGER,
    created_at INTEGER
)
""")
conn.commit()


def get_user(user_id: int):
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    if row is None:
        cur.execute(
            "INSERT INTO users (user_id) VALUES (?)",
            (user_id,)
        )
        conn.commit()
        return get_user(user_id)

    return dict(row)

def get_rank(user_id, weekly=False):
    if weekly:
        cur.execute("""
            SELECT COUNT(*) + 1 FROM users
            WHERE weekly_xp > (SELECT weekly_xp FROM users WHERE user_id = ?)
        """, (user_id,))
    else:
        cur.execute("""
            SELECT COUNT(*) + 1 FROM users
            WHERE total_xp > (SELECT total_xp FROM users WHERE user_id = ?)
        """, (user_id,))

    row = cur.fetchone()
    return row[0] if row else None


def has_enough_coins(user_id: int, amount: int) -> bool:
    user = get_user(user_id)
    return user["coins"] >= amount and amount > 0


def change_coins(user_id: int, amount: int):
    cur.execute(
        "UPDATE users SET coins = coins + ? WHERE user_id = ?",
        (amount, user_id)
    )
    conn.commit()

def has_active_gamble(user_id: int) -> bool:
    cur.execute(
        "SELECT 1 FROM active_gambles WHERE user_id = ?",
        (user_id,)
    )
    return cur.fetchone() is not None


def reserve_gamble(user_id: int, opponent_id: int | None):
    cur.execute("""
        INSERT OR REPLACE INTO active_gambles
        (user_id, opponent_id, created_at)
        VALUES (?, ?, ?)
    """, (user_id, opponent_id, int(time.time())))
    conn.commit()


def release_coins(user_id: int):
    cur.execute(
        "DELETE FROM active_gambles WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()


# ================== LEVEL SYSTEM ==================

def xp_needed_for_level(level):
    return 20 + (level - 1) * 5

async def add_xp(member, amount):
    user = get_user(member.id)

    xp = user["xp"] + amount
    total_xp = user["total_xp"] + amount
    weekly_xp = user["weekly_xp"] + amount

    level = user["level"]
    coins = user["coins"]

    leveled = False

    while xp >= xp_needed_for_level(level + 1):
        xp -= xp_needed_for_level(level + 1)
        level += 1
        coins += 20
        leveled = True

    cur.execute("""
        UPDATE users SET
            xp = ?, total_xp = ?, weekly_xp = ?,
            level = ?, coins = ?
        WHERE user_id = ?
    """, (xp, total_xp, weekly_xp, level, coins, member.id))
    conn.commit()

    if leveled:
        channel = member.guild.get_channel(LEVEL_UP_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title=f"{LEVEL_EMOJI} LEVEL UP!",
                description=(
                    f"🔥 **{member.mention}** ist aufgestiegen!\n\n"
                    f"{LEVEL_EMOJI} Neues Level: **{level}**\n"
                    f"{COIN_EMOJI} +20 {COIN_NAME}"
                ),
                color=discord.Color.green()
            )
            await channel.send(embed=embed)


# ================== VOICE TRACKING ==================

voice_times = {}
pending_gambles = {}

@bot.event
async def on_voice_state_update(member, before, after):
    get_user(member.id)
    uid = member.id
    now = time.time()

    # JOIN Voice
    if before.channel is None and after.channel is not None:
        voice_times[uid] = now
        return

    # SWITCH Voice Channel
    if before.channel is not None and after.channel is not None:
        if before.channel.id != after.channel.id:
            joined = voice_times.get(uid)
            if joined:
                duration = int(now - joined)

                cur.execute("""
                    UPDATE users SET
                        voice_seconds = voice_seconds + ?,
                        weekly_voice_seconds = weekly_voice_seconds + ?
                    WHERE user_id = ?
                """, (duration, duration, uid))
                conn.commit()

                xp = duration / 600
                if xp > 0:
                    await add_xp(member, round(xp, 2))

            voice_times[uid] = now
        return

    # LEAVE Voice
    if before.channel is not None and after.channel is None:
        joined = voice_times.pop(uid, None)
        if not joined:
            return

        duration = int(now - joined)

        cur.execute("""
            UPDATE users SET
                voice_seconds = voice_seconds + ?,
                weekly_voice_seconds = weekly_voice_seconds + ?
            WHERE user_id = ?
        """, (duration, duration, uid))
        conn.commit()

        xp = duration / 600
        if xp > 0:
            await add_xp(member, round(xp, 2))

        if duration >= 3600:
            cur.execute(
                "UPDATE users SET coins = coins + 10 WHERE user_id = ?",
                (uid,)
            )
            conn.commit()



            

# ================== REACTION ROLES ==================

REACTION_ROLE_CHANNEL_ID = 983775494388461578

REACTION_ROLE_CONFIG = {
    "games": {
        "type": "multi",
        "title": "🎮 Spiele",
        "description": "Wähle die Spiele aus, die du spielst:",
        "roles": {
            "<:minecraft:1154917299145429083>": 1111976466868080682,
            "<:valorant:1154917333719072848>": 983750378396979290,
            "<:fortnite:1154917530989772800>": 983750983182061569,
            "<:gta5:1258452798719135825>": 1258450337665253437
        }
    },
    "valorant_rank": {
        "type": "single",
        "title": "🏆 Valorant Rang",
        "description": "Wähle **einen** Valorant Rang:",
        "roles": {
            "<:valorant_iron:1154918607462092821>": 1463382014395809813,
            "<:valorant_bronze:1461781498351976498>": 1463382723308814508,
            "<:valorant_silver:1154918951847997471>": 1463382759790870630,
            "<:valorant_gold:1154920773903994921>": 1463382790899896559,
            "<:valorant_platinum:1154918888920858687>": 1463383093392965642,
            "<:valorant_diamond:1154918409528676413>": 1463383123512393798,
            "<:valorant_ascendant:1154917646228271235>": 1463383147558469807,
            "<:valorant_immortal:1154919052838436924>": 1463383443953025075
        }
    },
    "pings": {
        "type": "multi",
        "title": "🔔 Pings",
        "description": "Wähle, für welche Pings du benachrichtigt werden möchtest:",
        "roles": {
            "<:valorant_competetive:1463633051123974155>": 1463384039410110494,
            "<:valorant_customs:1463634442135404605>": 1463384082120441967,
            "<:valorant_unrated:1463633001329197230>": 1463635078046552188
        }
    }
}

def load_reaction_roles():
    try:
        with open(REACTION_ROLE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_reaction_roles():
    with open(REACTION_ROLE_FILE, "w") as f:
        json.dump(REACTION_ROLE_MESSAGES, f, indent=4)

REACTION_ROLE_MESSAGES = load_reaction_roles()


# ================== LOG HELFER ==================

async def send_log_embed(guild, title, description, color=discord.Color.blue()):
    if not guild:
        return
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=f"Server: {guild.name}")
    await channel.send(embed=embed)

# ================== COMMANDS ==================

@bot.command()
async def ping(ctx):
    await ctx.send("pong")


@bot.command()
async def stats(ctx, member: discord.Member = None):
    member = member or ctx.author
    user = get_user(member.id)

    needed = xp_needed_for_level(user["level"] + 1)
    rank = get_rank(member.id)

    embed = discord.Embed(
        title=f"📊 Stats von {member.display_name}",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name=f"{XP_EMOJI} {XP_NAME}",
        value=f"{user['xp']} / {needed}",
        inline=True
    )
    embed.add_field(
        name=f"{LEVEL_EMOJI} {LEVEL_NAME}",
        value=user["level"],
        inline=True
    )
    embed.add_field(
        name="🏆 Rang",
        value=f"#{rank}",
        inline=True
    )

    embed.add_field(name="💬 Nachrichten", value=user["messages"], inline=True)
    embed.add_field(
        name="🎙 Voice-Zeit",
        value=f"{int(user['voice_seconds']//60)} Minuten",
        inline=True
    )
    embed.add_field(
        name=f"{COIN_EMOJI} {COIN_NAME}",
        value=user["coins"],
        inline=True
    )

    await ctx.send(embed=embed)



@bot.command()
async def statsweek(ctx, member: discord.Member = None):
    member = member or ctx.author
    user = get_user(member.id)

    rank = get_rank(member.id, weekly=True)

    embed = discord.Embed(
        title=f"📊 Wochen-Stats von {member.display_name}",
        color=discord.Color.purple()
    )

    embed.add_field(name=f"{XP_EMOJI} {XP_NAME}", value=user["weekly_xp"])
    embed.add_field(name="💬 Nachrichten", value=user["weekly_messages"])
    embed.add_field(
        name="🎙 Voice-Zeit",
        value=f"{int(user['weekly_voice_seconds']//60)} Minuten"
    )

    embed.add_field(name="🏆 Wochenrang", value=f"#{rank}")

    await ctx.send(embed=embed)

@bot.command()
async def list(ctx):
    cur.execute("""
        SELECT user_id, total_xp FROM users
        ORDER BY total_xp DESC LIMIT 10
    """)
    rows = cur.fetchall()

    embed = discord.Embed(title="🏆 Top 10 Rangliste", color=discord.Color.gold())

    for i, row in enumerate(rows, start=1):
        member = ctx.guild.get_member(row["user_id"])
        if member:
            embed.add_field(
                name=f"#{i} {member.mention}",
                value=f"{row['total_xp']} XP",
                inline=False
            )

    await ctx.send(embed=embed)



@bot.command()
async def listweek(ctx):
    cur.execute("""
        SELECT user_id, weekly_xp FROM users
        ORDER BY weekly_xp DESC LIMIT 10
    """)
    rows = cur.fetchall()

    embed = discord.Embed(title="🏆 Wochenrangliste", color=discord.Color.purple())

    for i, row in enumerate(rows, start=1):
        member = ctx.guild.get_member(row["user_id"])
        if member:
            embed.add_field(
                name=f"#{i} {member.mention}",
                value=f"{row['weekly_xp']} XP",
                inline=False
            )

    await ctx.send(embed=embed)



@bot.command()
@commands.has_permissions(administrator=True)
async def reactionroles(ctx):
    REACTION_ROLE_MESSAGES.clear()
    channel = ctx.guild.get_channel(REACTION_ROLE_CHANNEL_ID)
    for data in REACTION_ROLE_CONFIG.values():
        embed = discord.Embed(
            title=data["title"],
            description=data["description"],
            color=discord.Color.blurple()
        )

        text = ""
        for emoji, role_id in data["roles"].items():
            role = ctx.guild.get_role(role_id)
            if role:
                text += f"{emoji} → {role.mention}\n"

        embed.add_field(name="Rollen", value=text, inline=False)
        msg = await channel.send(embed=embed)
        REACTION_ROLE_MESSAGES[str(msg.id)] = data
        save_reaction_roles()


        for emoji in data["roles"]:
            await msg.add_reaction(emoji)

@bot.command()
async def coins(ctx):
    user = get_user(ctx.author.id)

    embed = discord.Embed(
        title=f"{COIN_EMOJI} {COIN_NAME}",
        description=f"Du besitzt aktuell **{user['coins']} {COIN_NAME}**",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)


@bot.command()
async def gamble(ctx, coins: int):
    if coins <= 0:
        await ctx.send("❌ Der Einsatz muss größer als 0 sein.")
        return
    if has_active_gamble(ctx.author.id):
        await ctx.send("❌ Du hast bereits ein aktives Glücksspiel.")
        return
    if ctx.channel.id != MINIGAME_CHANNEL_ID:
        return

    if not has_enough_coins(ctx.author.id, coins):
        await ctx.send("❌ Du hast nicht genug Coins.")
        return
    # Einsatz abziehen
    change_coins(ctx.author.id, -coins)
    reserve_gamble(ctx.author.id, bot.user.id)

    user_roll = random.randint(1, 6)
    bot_roll = random.randint(1, 6)

    embed = discord.Embed(
        title="🎲 Würfelspiel gegen den Bot",
        color=discord.Color.gold()
    )

    embed.add_field(name=ctx.author.mention, value=f"🎲 {user_roll}")
    embed.add_field(name="🤖 Bot", value=f"🎲 {bot_roll}")

    if user_roll > bot_roll:
        change_coins(ctx.author.id, coins * 2)
        result = f"✅ Du gewinnst **{coins} {COIN_NAME}**!"
    elif user_roll < bot_roll:
        result = f"❌ Du verlierst **{coins} {COIN_NAME}**."
    else:
        change_coins(ctx.author.id, coins)
        result = "➖ Unentschieden – Einsatz zurück."


    embed.add_field(name="Ergebnis", value=result, inline=False)
    await ctx.send(embed=embed)
    release_coins(ctx.author.id)


@bot.command()
async def gambleinvite(ctx, opponent: discord.Member, coins: int):
    if coins <= 0:
        await ctx.send("❌ Der Einsatz muss größer als 0 sein.")
        return
    if (ctx.author.id, opponent.id) in pending_gambles or (opponent.id, ctx.author.id) in pending_gambles:
        await ctx.send("❌ Zwischen euch gibt es bereits eine offene Einladung.")
        return
    if has_active_gamble(ctx.author.id) or has_active_gamble(opponent.id):
        await ctx.send("❌ Einer von euch hat bereits ein aktives Glücksspiel.")
        return
    if ctx.channel.id != MINIGAME_CHANNEL_ID:
        return

    if opponent.bot or opponent == ctx.author:
        return

    if not has_enough_coins(ctx.author.id, coins) or not has_enough_coins(opponent.id, coins):
        await ctx.send("❌ Einer von euch hat nicht genug Coins.")
        return

    # Einsatz bei beiden abziehen
    change_coins(ctx.author.id, -coins)
    change_coins(opponent.id, -coins)

        

    reserve_gamble(ctx.author.id, opponent.id)
    reserve_gamble(opponent.id, ctx.author.id)
    pending_gambles[(ctx.author.id, opponent.id)] = {
        "coins": coins,
        "created_at": time.time()
    }

    embed = discord.Embed(
        title="🎲 Würfel-Herausforderung",
        description=(
            f"{ctx.author.mention} fordert {opponent.mention} heraus!\n"
            f"Einsatz: **{coins} {COIN_NAME}**\n\n"
            f"{opponent.mention} → nutze `/gambleaccept {ctx.author.mention}`"
        ),
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed)

@bot.command()
async def gambleaccept(ctx, opponent: discord.Member):
    if ctx.channel.id != MINIGAME_CHANNEL_ID:
        return
    if not has_active_gamble(ctx.author.id):
        await ctx.send("❌ Dein Einsatz ist nicht mehr reserviert.")
        return
    if not has_active_gamble(opponent.id):
        await ctx.send("❌ Der Gegner hat kein aktives Glücksspiel mehr.")
        return
    if (opponent.id, ctx.author.id) not in pending_gambles:
        await ctx.send("❌ Keine offene Herausforderung gefunden.")
        return
    key = (opponent.id, ctx.author.id)

    data = pending_gambles.pop(key, None)
    if not data:
        await ctx.send("❌ Diese Herausforderung ist nicht mehr gültig.")
        return

    coins = data["coins"]

    

    roll1 = random.randint(1, 6)
    roll2 = random.randint(1, 6)

    embed = discord.Embed(
        title="🎲 Würfelduell",
        color=discord.Color.gold()
    )

    embed.add_field(name=opponent.mention, value=f"🎲 {roll1}")
    embed.add_field(name=ctx.author.mention, value=f"🎲 {roll2}")

    if roll1 > roll2:
        change_coins(opponent.id, coins * 2)
        result = f"🏆 {opponent.mention} gewinnt!"
    elif roll2 > roll1:
        change_coins(ctx.author.id, coins * 2)
        result = f"🏆 {ctx.author.mention} gewinnt!"
    else:
        change_coins(ctx.author.id, coins)
        change_coins(opponent.id, coins)
        result = "➖ Unentschieden – Coins zurück."


    embed.add_field(name="Ergebnis", value=result, inline=False)
    await ctx.send(embed=embed)
    release_coins(ctx.author.id)
    release_coins(opponent.id)


# ================== EVENTS ==================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    get_user(message.author.id)

    content = message.content.lower()
    for word in BAD_WORDS:
        if word in content:
            await message.delete()
            await send_log_embed(
                message.guild,
                "🚫 Nachricht gelöscht (Blacklist)",
                f"{message.author}\n{message.channel.mention}\n```{message.content}```",
                discord.Color.red()
            )
            await bot.process_commands(message)
            return


    cur.execute("""
        UPDATE users SET
            messages = messages + 1,
            weekly_messages = weekly_messages + 1
        WHERE user_id = ?
    """, (message.author.id,))
    conn.commit()

    if not message.content.startswith(bot.command_prefix):
        await add_xp(message.author, 1)

    user = get_user(message.author.id)
    if user["messages"] % 10 == 0:
        cur.execute(
            "UPDATE users SET coins = coins + 5 WHERE user_id = ?",
            (message.author.id,)
        )
        conn.commit()


   

    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    role = member.guild.get_role(AUTO_ROLE_ID)
    if role:
        await member.add_roles(role)

    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="Herzlich Willkommen! 🎉",
            description=f"Tachchen {member.mention}, willkommen bei Gaming 420!",
            color=discord.Color.green()
        )
        embed.set_image(url=WELCOME_IMAGE_URL)
        await channel.send(embed=embed)

@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.message_id) not in REACTION_ROLE_MESSAGES:
        return

    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    if not member or member.bot:
        return
    emoji = str(payload.emoji)
    data = REACTION_ROLE_MESSAGES[str(payload.message_id)]

    role_id = data["roles"].get(emoji)
    if not role_id:
        return

    role = guild.get_role(role_id)
    if data["type"] == "single":
        for rid in data["roles"].values():
            r = guild.get_role(rid)
            if r and r in member.roles:
                await member.remove_roles(r)

    await member.add_roles(role)



@bot.event
async def on_raw_reaction_remove(payload):
    if str(payload.message_id) not in REACTION_ROLE_MESSAGES:
        return


    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    if not member or member.bot:
        return
    emoji = str(payload.emoji)
    role_id = REACTION_ROLE_MESSAGES[str(payload.message_id)]["roles"].get(emoji)
    if role_id:
        role = guild.get_role(role_id)
        await member.remove_roles(role)


@bot.event
async def on_ready():
    print(f"✅ Bot online als {bot.user}")
    # 🔄 ABGEBROCHENE GAMBLES NACH RESTART AUFRÄUMEN
    cur.execute("SELECT user_id FROM active_gambles")
    rows = cur.fetchall()

    for row in rows:
        uid = row["user_id"]
        # Coins zurückgeben (wir wissen hier nicht wie viele → safe Lösung)
        # → KEINE Rückgabe, sondern nur Freigabe
        release_coins(uid)

    pending_gambles.clear()

    now = time.time()

    # 🔊 ALLE User, die gerade im Voice sind, erfassen
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for member in vc.members:
                voice_times[member.id] = now





@bot.event
async def on_message_delete(message):
    if message.author and not message.author.bot:
        await send_log_embed(
            message.guild,
            "🗑️ Nachricht gelöscht",
            f"👤 {message.author}\n📍 {message.channel.mention}\n\n```{message.content}```",
            discord.Color.dark_red()
        )

@bot.event
async def on_message_edit(before, after):
    if after.author.bot or before.content == after.content:
        return

    await send_log_embed(
        before.guild,
        "✏️ Nachricht bearbeitet",
        f"👤 {after.author}\n📍 {after.channel.mention}\n\n"
        f"🕰️ Vorher:\n```{before.content}```\n"
        f"🆕 Nachher:\n```{after.content}```",
        discord.Color.orange()
    )

@bot.event
async def on_guild_channel_create(channel):
    await send_log_embed(
        channel.guild,
        "➕ Channel erstellt",
        f"{channel.name} ({channel.id})",
        discord.Color.green()
    )

@bot.event
async def on_guild_channel_delete(channel):
    await send_log_embed(
        channel.guild,
        "❌ Channel gelöscht",
        f"{channel.name} ({channel.id})",
        discord.Color.red()
    )


@bot.event
async def on_member_update(before, after):
    if before.nick != after.nick:
        old = before.nick or before.name
        new = after.nick or after.name

        await send_log_embed(
            after.guild,
            "👤 Nickname geändert",
            f"{old} → {new}",
            discord.Color.blue()
        )


async def weekly_reset_task():
    await bot.wait_until_ready()

    while not bot.is_closed():
        now = datetime.now()

        global last_weekly_reset

        if (
            now.weekday() == 0
            and now.hour == 20
            and (last_weekly_reset is None or last_weekly_reset.date() != now.date())
        ):
            last_weekly_reset = now
            guild = bot.get_guild(GUILD_ID)
            if not guild:
                await asyncio.sleep(60)
                continue

            channel = guild.get_channel(LEVEL_UP_CHANNEL_ID)
            if not channel:
                await asyncio.sleep(60)
                continue

            cur.execute("""
            SELECT * FROM users
            ORDER BY weekly_xp DESC
            LIMIT 3
            """)
            ranking = cur.fetchall()
            rewards = [50, 30, 15]

            embed = discord.Embed(
                title="🏆 Wochenrangliste (letzte 7 Tage)",
                color=discord.Color.gold()
            )

            for i, row in enumerate(ranking):
                member = guild.get_member(row["user_id"])

                cur.execute(
                    "UPDATE users SET coins = coins + ? WHERE user_id = ?",
                    (rewards[i], row["user_id"])
                )

                embed.add_field(
                    name=f"#{i+1} {member.mention}",
                    value=(
                        f"{XP_EMOJI} XP: {row['weekly_xp']}\n"
                        f"💬 Nachrichten: {row['weekly_messages']}\n"
                        f"🎙 Voice: {int(row['weekly_voice_seconds']//60)} Min\n"
                        f"{COIN_EMOJI} +{rewards[i]} Coins"
                    ),
                    inline=False
                )


                

            await channel.send(embed=embed)

            # 🔊 OFFENE VOICE-ZEIT VOR RESET SPEICHERN
            now_ts = time.time()

            for user_id, joined in voice_times.items():
                duration = int(now_ts - joined)
                if duration > 0:
                    cur.execute("""
                        UPDATE users SET
                            voice_seconds = voice_seconds + ?,
                            weekly_voice_seconds = weekly_voice_seconds + ?
                        WHERE user_id = ?
                    """, (duration, duration, user_id))

            conn.commit()
            voice_times.clear()
            now_ts = time.time()
            for guild in bot.guilds:
                for vc in guild.voice_channels:
                    for member in vc.members:
                        voice_times[member.id] = now_ts


            # 🔁 WOCHENWERTE RESETTEN
            cur.execute("""
            UPDATE users SET
                weekly_xp = 0,
                weekly_messages = 0,
                weekly_voice_seconds = 0
            """)
            conn.commit()



            await asyncio.sleep(60)

        await asyncio.sleep(30)

async def cleanup_pending_gambles():
    while True:
        await asyncio.sleep(300)  # alle 5 Minuten
        now = time.time()

        for (u1, u2), data in list(pending_gambles.items()):
            if now - data["created_at"] > 300:
                coins = data["coins"]

                # Coins nur zurückgeben, wenn das Gamble noch reserviert ist
                if has_active_gamble(u1):
                    change_coins(u1, coins)
                    release_coins(u1)

                if u2 != bot.user.id and has_active_gamble(u2):
                    change_coins(u2, coins)
                    release_coins(u2)

                pending_gambles.pop((u1, u2), None)




# ================== START ==================

try:
    bot.run(os.environ["DISCORD_TOKEN"])
