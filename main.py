import discord
from discord.ext import commands
import os
import json
import time
import asyncio
from datetime import datetime

# ================== XP / LEVEL KONFIG ==================

DATA_FILE = "userdata.json"
REACTION_ROLE_FILE = "reaction_roles.json"


XP_NAME = "Weedpunkte"
LEVEL_NAME = "Weedstufe"
COIN_NAME = "Kiffer Coins"

XP_EMOJI = "<:weed_punkte:1464315549021507645>"
LEVEL_EMOJI = "<:weed_stufe:1464315589844795434>"
COIN_EMOJI = "<:kiffer_coins:1464315487038083267>"

LEVEL_UP_CHANNEL_ID = 1464296536170037329

last_weekly_reset = None

# ================== BOT SETUP ==================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix='/', intents=intents)

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

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

def get_user(user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "xp": 0,
            "level": 0,
            "coins": 0,
            "messages": 0,
            "voice_seconds": 0,
            "total_xp": 0,
            "weekly": {
                "xp": 0,
                "messages": 0,
                "voice_seconds": 0
            }
        }
    return data[uid]

def get_sorted_users(by="xp", weekly=False):
    key = "weekly" if weekly else None

    def value(u):
        if weekly:
            return data[u]["weekly"][by]
        return data[u][by]

    return sorted(data.keys(), key=lambda u: value(u), reverse=True)

def get_rank(user_id, weekly=False):
    if weekly:
        sorted_users = get_sorted_users("xp", weekly=True)
    else:
        sorted_users = get_sorted_users("total_xp")

    try:
        return sorted_users.index(str(user_id)) + 1
    except ValueError:
        return None



# ================== LEVEL SYSTEM ==================

def xp_needed_for_level(level):
    return 20 + (level - 1) * 5

async def add_xp(member, amount):
    user = get_user(member.id)
    user["total_xp"] += amount
    user["xp"] += amount
    user["weekly"]["xp"] += amount

    leveled = False

    while user["xp"] >= xp_needed_for_level(user["level"] + 1):
        user["xp"] -= xp_needed_for_level(user["level"] + 1)
        user["level"] += 1
        user["coins"] += 20
        leveled = True


    save_data()

    if leveled:
        channel = member.guild.get_channel(LEVEL_UP_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title=f"{LEVEL_EMOJI} LEVEL UP!",
                description=(
                    f"🔥 **{member.mention}** ist aufgestiegen!\n\n"
                    f"{LEVEL_EMOJI} **Neue {LEVEL_NAME}:** {user['level']}\n"
                    f"{COIN_EMOJI} **+20 {COIN_NAME}**"
                ),
                color=discord.Color.green()
            )
            await channel.send(embed=embed)

# ================== VOICE TRACKING ==================

voice_times = {}

@bot.event
async def on_voice_state_update(member, before, after):
    uid = str(member.id)
    now = time.time()

    if before.channel is None and after.channel is not None:
        voice_times[uid] = now

    if before.channel is not None and after.channel is None:
        joined = voice_times.pop(uid, None)
        if joined:
            duration = int(now - joined)
            user = get_user(member.id)

            user["voice_seconds"] += duration
            user["weekly"]["voice_seconds"] += duration

            xp = int(duration // 600)
            if xp > 0:
                await add_xp(member, xp)

            if duration >= 3600:
                await add_xp(member, 3)
                user["coins"] += 10

            save_data()

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

    embed.add_field(name=f"{XP_EMOJI} {XP_NAME}", value=user["weekly"]["xp"])
    embed.add_field(name="💬 Nachrichten", value=user["weekly"]["messages"])
    embed.add_field(
        name="🎙 Voice-Zeit",
        value=f"{int(user['weekly']['voice_seconds']//60)} Minuten"
    )
    embed.add_field(name="🏆 Wochenrang", value=f"#{rank}")

    await ctx.send(embed=embed)

@bot.command()
async def list(ctx):
    users = get_sorted_users("total_xp")[:10]
    embed = discord.Embed(title="🏆 Top 10 Rangliste", color=discord.Color.gold())

    text = ""
    for i, uid in enumerate(users, start=1):
        member = ctx.guild.get_member(int(uid))
        if member:
            text += f"**#{i}** {member.display_name} — {data[uid]['total_xp']} XP\n"

    embed.description = text
    await ctx.send(embed=embed)


@bot.command()
async def listweek(ctx):
    users = get_sorted_users("xp", weekly=True)[:10]
    embed = discord.Embed(title="🏆 Top 10 Wochenrangliste", color=discord.Color.purple())

    text = ""
    for i, uid in enumerate(users, start=1):
        member = ctx.guild.get_member(int(uid))
        if member:
            text += f"**#{i}** {member.display_name} — {data[uid]['weekly']['xp']} XP\n"

    embed.description = text
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(administrator=True)
async def reactionroles(ctx):
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


# ================== EVENTS ==================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

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

    user = get_user(message.author.id)
    user["messages"] += 1
    user["weekly"]["messages"] += 1

    await add_xp(message.author, 1)

    if user["messages"] % 10 == 0:
        user["coins"] += 5

    save_data()
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

    # Reaction Roles sind bereits aus JSON geladen
    # Keine weitere Logik nötig – on_raw_reaction_* greift automatisch




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
        await send_log_embed(
            after.guild,
            "👤 Nickname geändert",
            f"{before.nick} → {after.nick}",
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
            guild = bot.guilds[0]
            channel = guild.get_channel(LEVEL_UP_CHANNEL_ID)

            ranking = get_sorted_users("xp", weekly=True)
            rewards = [50, 30, 15]

            embed = discord.Embed(
                title="🏆 Wochenrangliste (letzte 7 Tage)",
                color=discord.Color.gold()
            )

            for i, uid in enumerate(ranking[:3]):
                user = data[uid]
                member = guild.get_member(int(uid))

                user["coins"] += rewards[i]

                embed.add_field(
                    name=f"#{i+1} {member.display_name}",
                    value=(
                        f"{XP_EMOJI} XP: {user['weekly']['xp']}\n"
                        f"💬 Nachrichten: {user['weekly']['messages']}\n"
                        f"🎙 Voice: {int(user['weekly']['voice_seconds']//60)} Min\n"
                        f"{COIN_EMOJI} +{rewards[i]} Coins"
                    ),
                    inline=False
                )

            await channel.send(embed=embed)

            for u in data.values():
                u["weekly"] = {"xp": 0, "messages": 0, "voice_seconds": 0}

            save_data()
            await asyncio.sleep(60)

        await asyncio.sleep(30)

bot.loop.create_task(weekly_reset_task())



# ================== START ==================

bot.run(os.environ["DISCORD_TOKEN"])



