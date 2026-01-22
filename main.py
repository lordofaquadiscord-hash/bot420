import discord
from discord.ext import commands
import os

# ================== BOT SETUP ==================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)

# ================== KONFIG ==================

BAD_WORDS = [
    "hurensohn", "hure", "fick", "toten", "nigger", "neger", "nigga", "niger",
    "fotze", "schwuchtel", "homo", "nuttensohn", "nutte", "bastard",
    "schlampe", "opfer", "leck", "spasti", "behindert", "hund", "köter",
    "jude", "huso", "hs", "gefickt", "lutsch", "mongo"
]

WELCOME_CHANNEL_ID = 983743026704826450
AUTO_ROLE_ID = 983752389502836786
WELCOME_IMAGE_URL = "https://media.discordapp.net/attachments/1039293219491565621/1462608302033731680/gaming420.png?format=webp&quality=lossless"
LOG_CHANNEL_ID = 1462152930768589023

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
        "type": "multi",  # ⬅ mehrere Rollen gleichzeitig erlaubt
        "title": "🔔 Pings",
        "description": "Wähle, für welche Pings du benachrichtigt werden möchtest:",
        "roles": {
            "<:valorant_competetive:1463633051123974155>": 1463384039410110494,   # ⬅ HIER ÄNDERN
            "<:valorant_customs:1463634442135404605>": 1463384082120441967,
            "<:valorant_unrated:1463633001329197230>": 1463635078046552188 # ⬅ HIER ÄNDERN
        }
    }

}

REACTION_ROLE_MESSAGES = {}

# ================== COMMANDS ==================

@bot.command()
async def ping(ctx):
    await ctx.send("pong")

@bot.command()
@commands.has_permissions(administrator=True)
async def reactionroles(ctx):
    channel = ctx.guild.get_channel(REACTION_ROLE_CHANNEL_ID)
    if not channel:
        await ctx.send("❌ Reaction-Role-Channel nicht gefunden")
        return

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

        REACTION_ROLE_MESSAGES[msg.id] = data

        for emoji in data["roles"]:
            await msg.add_reaction(emoji)

    await ctx.send("✅ Reaction-Role-Embeds wurden gesendet")

# ================== LOG HELFER ==================

async def send_log_embed(guild, title, description, color=discord.Color.blue()):
    if not guild:
        return
    try:
        channel = guild.get_channel(LOG_CHANNEL_ID)
        if not channel:
            return

        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text=f"Server: {guild.name}")
        await channel.send(embed=embed)
    except Exception as e:
        print(f"Fehler beim Loggen: {e}")

# ================== EVENTS ==================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.lower()
    for word in BAD_WORDS:
        if word in content:
            try:
                await message.delete()
                await send_log_embed(
                    message.guild,
                    "🚫 Nachricht gelöscht (Blacklist)",
                    f"👤 **User:** {message.author} ({message.author.id})\n"
                    f"📍 **Channel:** {message.channel.mention}\n\n"
                    f"💬 **Inhalt:**\n```{message.content}```",
                    discord.Color.red()
                )
            except Exception as e:
                print(e)
            return

    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    guild = member.guild

    try:
        role = guild.get_role(AUTO_ROLE_ID)
        if role:
            await member.add_roles(role)
    except Exception as e:
        print(e)

    try:
        channel = guild.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="Herzlich Willkommen! 🎉",
                description=f"Tachchen {member.mention}, willkommen bei Gaming 420! Schön, dass du es hierher geschafft hast!",
                color=discord.Color.green()
            )
            embed.set_image(url=WELCOME_IMAGE_URL)
            await channel.send(embed=embed)
    except Exception as e:
        print(e)

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

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.message_id not in REACTION_ROLE_MESSAGES:
        return

    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    emoji = str(payload.emoji)
    data = REACTION_ROLE_MESSAGES[payload.message_id]

    role_id = data["roles"].get(emoji)
    if not role_id:
        return

    role = guild.get_role(role_id)
    if not role:
        return

    if data["type"] == "single":
        for r_id in data["roles"].values():
            r = guild.get_role(r_id)
            if r and r in member.roles:
                await member.remove_roles(r)

        channel = guild.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        for reaction in message.reactions:
            if str(reaction.emoji) != emoji:
                await reaction.remove(member)

    await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.message_id not in REACTION_ROLE_MESSAGES:
        return

    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    emoji = str(payload.emoji)
    data = REACTION_ROLE_MESSAGES[payload.message_id]

    role_id = data["roles"].get(emoji)
    if role_id:
        role = guild.get_role(role_id)
        if role:
            await member.remove_roles(role)

@bot.event
async def on_ready():
    print(f"✅ Bot online als {bot.user}")

    for guild in bot.guilds:
        channel = guild.get_channel(REACTION_ROLE_CHANNEL_ID)
        if not channel:
            continue

        # 🔴 WICHTIG: verhindert doppeltes Posten
        async for msg in channel.history(limit=20):
            if msg.author == bot.user and msg.embeds:
                print("⚠️ Reaction Roles existieren bereits – überspringe")
                return

        # 📩 Embeds senden
        for data in REACTION_ROLE_CONFIG.values():
            embed = discord.Embed(
                title=data["title"],
                description=data["description"],
                color=discord.Color.blurple()
            )

            text = ""
            for emoji, role_id in data["roles"].items():
                role = guild.get_role(role_id)
                if role:
                    text += f"{emoji} → {role.mention}\n"

            embed.add_field(name="Rollen", value=text, inline=False)
            msg = await channel.send(embed=embed)

            REACTION_ROLE_MESSAGES[msg.id] = data

            for emoji in data["roles"]:
                await msg.add_reaction(emoji)


# ================== START ==================

bot.run(os.environ["DISCORD_TOKEN"])

