import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import time
import asyncio
from datetime import datetime
import sqlite3
import random
import math




# ================== XP / LEVEL KONFIG ==================

REACTION_ROLE_FILE = "/data/reaction_roles.json"


XP_NAME = "Weedpunkte"
LEVEL_NAME = "Weedstufe"
COIN_NAME = "Kiffer Coins"

XP_EMOJI = "<:weed_punkte:1464315549021507645>"
LEVEL_EMOJI = "<:weed_stufe:1464315589844795434>"
COIN_EMOJI = "<:kiffer_coins:1464315487038083267>"

LEVEL_UP_CHANNEL_ID = 1464296536170037329

BOT_OWNER_ID = 773442243138813982  # ← HIER DEINE DISCORD ID EINTRAGEN

last_weekly_reset = None

GUILD_ID = 983743026704826448

# ================== CHANNEL RESTRIKTIONEN ==================

COMMAND_ONLY_CHANNEL_IDS = [
    1464627521675984948,  # z.B. /commands
    1464627857497264288,  # z.B. /bot-commands
    1463376411124305993   # z.B. /minigames
]

NO_COMMANDS_CHANNEL_IDS = [
    983749038077804554,  # z.B. normaler Chat
    999999999999999999,
    983743026704826451,
    983755098075316244,
    1166448170264436736,
    1242399463838974045 # z.B. media-chat
]


BLACKJACK_CHANNEL_ID = 1464627857497264288  # ⬅️ Blackjack-Channel-ID

# Kartenrückseite (optional)
CARD_BACK_IMAGE = "https://media.discordapp.net/attachments/1039293219491565621/1465151863514206361/content.png?ex=69781081&is=6976bf01&hm=a10cbdeed96afece3727d9cbf39959a82d89d640607ff10bf468a4ab64bc3f17&=&format=webp&quality=lossless&width=640&height=960"

# =====================================================
# 🃏 KARTEN & DECK
# =====================================================

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

def create_deck():
    deck = [(r, s) for r in RANKS for s in SUITS]
    random.shuffle(deck)
    return deck

def card_value(card):
    rank, _ = card
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)

def hand_value(hand):
    value = sum(card_value(c) for c in hand)
    aces = sum(1 for c in hand if c[0] == "A")
    while value > 21 and aces:
        value -= 10
        aces -= 1
    return value

def hand_to_string(hand):
    return " ".join(f"{r}{s}" for r, s in hand)



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


ALLOWED_MENTIONS = discord.AllowedMentions(
    users=True,
    roles=False,
    everyone=False
)
bot.allowed_mentions = ALLOWED_MENTIONS

# ================== XP COOLDOWN ==================

MESSAGE_XP_COOLDOWN = 120  # 2 Minuten
last_message_xp = {}      # user_id -> timestamp


# ================== KONFIG ==================

BAD_WORDS = [
    "hurensohn","hure","fick","toten","nigger","neger","nigga","niger",
    "fotze","schwuchtel","homo","nuttensohn","nutte","bastard",
    "schlampe","opfer","spasti","behindert","hund","köter",
    "jude","huso","gefickt","lutsch","mongo","wixxer","wichser"
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

def is_bot_owner(ctx):
    return ctx.author.id == BOT_OWNER_ID

async def owner_only(ctx):
    if not is_bot_owner(ctx):
        await ctx.send("❌ Dieser Befehl ist nur für den Bot-Owner verfügbar.")
        return False
    return True

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



# =====================================================
# 🎰 BLACKJACK SESSION
# =====================================================

class BlackjackSession:
    def __init__(self, user_id, bet):
        self.user_id = user_id
        self.bet = bet
        self.deck = create_deck()

        self.hands = [[self.deck.pop(), self.deck.pop()]]
        self.current_hand = 0

        self.dealer = [self.deck.pop(), self.deck.pop()]
        self.finished = False

    def current(self):
        return self.hands[self.current_hand]

    def hit(self):
        self.current().append(self.deck.pop())

    def can_split(self):
        hand = self.current()
        return len(hand) == 2 and hand[0][0] == hand[1][0]

    def split(self):
        hand = self.current()
        card = hand.pop()
        self.hands.append([card, self.deck.pop()])
        hand.append(self.deck.pop())

    def dealer_play(self):
        while hand_value(self.dealer) < 17:
            self.dealer.append(self.deck.pop())

    def can_double(self):
        return len(self.current()) == 2


# =====================================================
# 🎮 VIEW & BUTTONS
# =====================================================

class BlackjackView(discord.ui.View):
    def __init__(self, interaction, session):
        super().__init__(timeout=120)
        self.interaction = interaction
        self.session = session

    async def on_timeout(self):
        release_coins(self.session.user_id)
        try:
            await self.interaction.edit_original_response(
                content="⏱️ Blackjack abgebrochen (Timeout).",
                view=None
            )
        except:
            pass


    async def interaction_check(self, interaction):
        return interaction.user.id == self.session.user_id

    def build_embed(self, final=False):
        embed = discord.Embed(
            title="🃏 Blackjack",
            color=discord.Color.gold()
        )

        for i, hand in enumerate(self.session.hands):
            marker = "👉 " if i == self.session.current_hand and not final else ""
            embed.add_field(
                name=f"{marker}Hand {i+1} ({hand_value(hand)})",
                value=hand_to_string(hand),
                inline=False
            )

        if final:
            dealer_val = hand_value(self.session.dealer)
            dealer_cards = hand_to_string(self.session.dealer)
        else:
            dealer_val = "?"
            dealer_cards = f"{self.session.dealer[0][0]}{self.session.dealer[0][1]} 🂠"

        embed.add_field(
            name=f"Dealer ({dealer_val})",
            value=dealer_cards,
            inline=False
        )

        embed.set_footer(text=f"Einsatz: {self.session.bet} {COIN_NAME}")
        return embed

    async def end_game(self):
        self.session.dealer_play()
        dealer_val = hand_value(self.session.dealer)

        result_text = ""
        for hand in self.session.hands:
            val = hand_value(hand)

            if val > 21:
                result_text += "❌ Bust\n"

            elif val == 21 and len(hand) == 2:
                # Blackjack 3:2 Auszahlung (aufgerundet)
                payout = math.ceil(self.session.bet * 2.5)
                change_coins(self.session.user_id, payout)
                result_text += f"🃏 Blackjack! (+{payout - self.session.bet} {COIN_NAME})\n"

            elif dealer_val > 21 or val > dealer_val:
                change_coins(self.session.user_id, self.session.bet * 2)
                result_text += "✅ Gewinn\n"

            elif val == dealer_val:
                change_coins(self.session.user_id, self.session.bet)
                result_text += "➖ Push\n"

            else:
                result_text += "❌ Verlust\n"


        release_coins(self.session.user_id)

        embed = self.build_embed(final=True)
        embed.add_field(name="Ergebnis", value=result_text)

        await self.interaction.edit_original_response(embed=embed, view=None)

    async def next_hand(self, interaction):
        self.session.current_hand += 1
        if self.session.current_hand >= len(self.session.hands):
            await self.end_game()
        else:
            await interaction.response.edit_message(embed=self.build_embed())

    # ================= BUTTONS =================

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.success)
    async def hit(self, interaction, button):
        self.session.hit()
        if hand_value(self.session.current()) >= 21:
            await self.next_hand(interaction)
        else:
            await interaction.response.edit_message(embed=self.build_embed())

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction, button):
        await self.next_hand(interaction)

    @discord.ui.button(label="Split", style=discord.ButtonStyle.primary)
    async def split(self, interaction, button):
        if not self.session.can_split():
            await interaction.response.send_message("❌ Split nicht möglich.", ephemeral=True)
            return

        if not has_enough_coins(self.session.user_id, self.session.bet):
            await interaction.response.send_message("❌ Nicht genug Coins für Split.", ephemeral=True)
            return

        change_coins(self.session.user_id, -self.session.bet)
        self.session.split()
        await interaction.response.edit_message(embed=self.build_embed())

    @discord.ui.button(label="Double", style=discord.ButtonStyle.danger)
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not self.session.can_double():
            await interaction.response.send_message(
                "❌ Double Down ist nur bei genau 2 Karten möglich.",
                ephemeral=True
            )
            return

        if not has_enough_coins(self.session.user_id, self.session.bet):
            await interaction.response.send_message(
                "❌ Nicht genug Coins für Double Down.",
                ephemeral=True
            )
            return

        # Einsatz verdoppeln
        change_coins(self.session.user_id, -self.session.bet)
        self.session.bet *= 2

        # Genau eine Karte ziehen
        self.session.hit()

        # Danach automatisch Stand
        await self.next_hand(interaction)




# ================== LEVEL SYSTEM ==================

def xp_needed_for_level(level):
    return 20 + (level - 1) * 5

def recalc_level_from_xp(total_xp: int):
    """
    Berechnet Level + Rest-XP anhand von Gesamt-XP
    """
    level = 0
    remaining_xp = total_xp

    while remaining_xp >= xp_needed_for_level(level + 1):
        remaining_xp -= xp_needed_for_level(level + 1)
        level += 1

    return level, remaining_xp


def recalc_xp_from_level(level: int):
    """
    Berechnet Gesamt-XP, sodass der User exakt auf diesem Level steht
    (0 XP Fortschritt ins nächste Level)
    """
    total_xp = 0
    for l in range(1, level + 1):
        total_xp += xp_needed_for_level(l)

    return total_xp


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
            await channel.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)


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

                xp = duration // 600
                if xp > 0:
                    await add_xp(member, xp)

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

        xp = duration // 600
        if xp > 0:
            await add_xp(member, xp)

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

def user_stats_embed(member, user, title):
    embed = discord.Embed(
        title=title,
        color=discord.Color.red()
    )

    embed.add_field(
        name=f"{LEVEL_EMOJI} {LEVEL_NAME}",
        value=user["level"],
        inline=True
    )
    embed.add_field(
        name=f"{XP_EMOJI} {XP_NAME}",
        value=user["xp"],
        inline=True
    )
    embed.add_field(
        name=f"{COIN_EMOJI} {COIN_NAME}",
        value=user["coins"],
        inline=True
    )

    embed.set_footer(text=f"User: {member} | ID: {member.id}")
    return embed


# ================== COMMANDS ==================

@bot.command()
async def ping(ctx):
    await ctx.send("pong")

@bot.tree.command(name="blackjack", description="Spiele Blackjack mit Kiffer Coins")
@app_commands.describe(coins="Einsatz")
async def blackjack(interaction: discord.Interaction, coins: int):

    if interaction.channel.id != BLACKJACK_CHANNEL_ID:
        await interaction.response.send_message(
            "❌ Blackjack ist nur im Blackjack-Channel erlaubt.",
            ephemeral=True
        )
        return

    user_id = interaction.user.id

    if coins <= 0:
        await interaction.response.send_message("❌ Ungültiger Einsatz.", ephemeral=True)
        return

    if has_active_gamble(user_id):
        await interaction.response.send_message(
            "❌ Du spielst bereits ein Glücksspiel.",
            ephemeral=True
        )
        return

    if not has_enough_coins(user_id, coins):
        await interaction.response.send_message(
            "❌ Nicht genug Kiffer Coins.",
            ephemeral=True
        )
        return

    change_coins(user_id, -coins)
    reserve_gamble(user_id, bot.user.id)

    session = BlackjackSession(user_id, coins)
    view = BlackjackView(interaction, session)

    await interaction.response.send_message(
        embed=view.build_embed(),
        view=view
    )


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

    await ctx.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)



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

    await ctx.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)

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
                name=f"#{i}",
                value=f"{member.mention}\n{row['total_xp']} XP",
                inline=False
            )

    await ctx.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)



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
                name=f"#{i}",
                value=f"{member.mention}\n{row['weekly_xp']} XP",
                inline=False
            )

    await ctx.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)



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
    await ctx.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)


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

    embed.add_field(
        name="Spieler",
        value=f"{ctx.author.mention}\n🎲 {user_roll}",
        inline=True
    )
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
    await ctx.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)
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
    await ctx.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)

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
    change_coins(ctx.author.id, -coins)
    change_coins(opponent.id, -coins)

    

    roll1 = random.randint(1, 6)
    roll2 = random.randint(1, 6)

    embed = discord.Embed(
        title="🎲 Würfelduell",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="Spieler 1",
        value=f"{opponent.mention}\n🎲 {roll1}",
        inline=True
    )

    embed.add_field(
        name="Spieler 2",
        value=f"{ctx.author.mention}\n🎲 {roll2}",
        inline=True
    )

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
    await ctx.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)
    release_coins(ctx.author.id)
    release_coins(opponent.id)

@bot.command()
async def setcoins(ctx, member: discord.Member, coins: int):
    if not await owner_only(ctx):
        return

    cur.execute("UPDATE users SET coins = ? WHERE user_id = ?", (coins, member.id))
    conn.commit()

    user = get_user(member.id)
    embed = user_stats_embed(member, user, "🛠 Coins gesetzt")
    await ctx.send(embed=embed)


@bot.command()
async def addcoins(ctx, member: discord.Member, coins: int):
    if not await owner_only(ctx):
        return

    cur.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (coins, member.id))
    conn.commit()

    user = get_user(member.id)
    embed = user_stats_embed(member, user, "➕ Coins hinzugefügt")
    await ctx.send(embed=embed)


@bot.command()
async def setxp(ctx, member: discord.Member, xp: int):
    if not await owner_only(ctx):
        return

    if xp < 0:
        xp = 0

    level, rest_xp = recalc_level_from_xp(xp)

    cur.execute("""
        UPDATE users SET
            total_xp = ?,
            weekly_xp = 0,
            level = ?,
            xp = ?
        WHERE user_id = ?
    """, (xp, level, rest_xp, member.id))
    conn.commit()

    user = get_user(member.id)
    embed = user_stats_embed(member, user, "🛠 XP gesetzt (Level synchronisiert)")
    await ctx.send(embed=embed)



@bot.command()
async def addxp(ctx, member: discord.Member, xp: int):
    if not await owner_only(ctx):
        return

    if xp == 0:
        return

    user = get_user(member.id)
    new_total_xp = max(0, user["total_xp"] + xp)

    level, rest_xp = recalc_level_from_xp(new_total_xp)

    cur.execute("""
        UPDATE users SET
            total_xp = ?,
            weekly_xp = weekly_xp + ?,
            level = ?,
            xp = ?
        WHERE user_id = ?
    """, (new_total_xp, max(0, xp), level, rest_xp, member.id))
    conn.commit()

    user = get_user(member.id)
    embed = user_stats_embed(member, user, "➕ XP hinzugefügt (Level synchronisiert)")
    await ctx.send(embed=embed)



@bot.command()
async def setlevel(ctx, member: discord.Member, level: int):
    if not await owner_only(ctx):
        return

    if level < 0:
        level = 0

    total_xp = recalc_xp_from_level(level)

    cur.execute("""
        UPDATE users SET
            level = ?,
            total_xp = ?,
            weekly_xp = 0,
            xp = 0
        WHERE user_id = ?
    """, (level, total_xp, member.id))
    conn.commit()

    user = get_user(member.id)
    embed = user_stats_embed(member, user, "🛠 Level gesetzt (XP synchronisiert)")
    await ctx.send(embed=embed)



@bot.command()
async def addlevel(ctx, member: discord.Member, level: int):
    if not await owner_only(ctx):
        return

    if level == 0:
        return

    user = get_user(member.id)
    new_level = max(0, user["level"] + level)

    total_xp = recalc_xp_from_level(new_level)

    cur.execute("""
        UPDATE users SET
            level = ?,
            total_xp = ?,
            weekly_xp = weekly_xp,
            xp = 0
        WHERE user_id = ?
    """, (new_level, total_xp, member.id))
    conn.commit()

    user = get_user(member.id)
    embed = user_stats_embed(member, user, "➕ Level hinzugefügt (XP synchronisiert)")
    await ctx.send(embed=embed)



@bot.command()
async def resetuser(ctx, member: discord.Member):
    if not await owner_only(ctx):
        return

    cur.execute("""
        UPDATE users SET
            xp = 0,
            level = 0,
            coins = 0,
            total_xp = 0,
            weekly_xp = 0
        WHERE user_id = ?
    """, (member.id,))

    conn.commit()

    user = get_user(member.id)
    embed = user_stats_embed(member, user, "♻ User zurückgesetzt")
    await ctx.send(embed=embed)


@bot.command()
async def resetcoins(ctx, member: discord.Member):
    if not await owner_only(ctx):
        return

    cur.execute("UPDATE users SET coins = 0 WHERE user_id = ?", (member.id,))
    conn.commit()

    user = get_user(member.id)
    embed = user_stats_embed(member, user, "♻ Coins zurückgesetzt")
    await ctx.send(embed=embed)


@bot.command()
async def resetall(ctx):
    if not await owner_only(ctx):
        return

    cur.execute("""
        UPDATE users SET
            xp = 0,
            level = 0,
            coins = 0,
            total_xp = 0,
            weekly_xp = 0,
            weekly_messages = 0,
            weekly_voice_seconds = 0
    """)

    conn.commit()

    embed = discord.Embed(
        title="⚠️ GLOBAL RESET",
        description="Alle User wurden vollständig zurückgesetzt.",
        color=discord.Color.dark_red()
    )
    await ctx.send(embed=embed)


@bot.command()
async def setcoinsall(ctx, coins: int):
    if not await owner_only(ctx):
        return

    cur.execute("UPDATE users SET coins = ?", (coins,))
    conn.commit()

    embed = discord.Embed(
        title="🛠 Coins global gesetzt",
        description=f"Alle User haben jetzt **{coins} {COIN_NAME}**",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)


@bot.command()
async def addcoinsall(ctx, coins: int):
    if not await owner_only(ctx):
        return

    cur.execute("UPDATE users SET coins = coins + ?", (coins,))
    conn.commit()

    embed = discord.Embed(
        title="➕ Coins global hinzugefügt",
        description=f"Allen Usern wurden **{coins} {COIN_NAME}** hinzugefügt",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)


# ================== EVENTS ==================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # ❌ KEINE DMs (Bugfix gegen DM-Spam)
    if message.guild is None:
        return
    # ================== CHANNEL RESTRIKTIONEN ==================

    # 🔒 NUR /BEFEHLE ERLAUBT (MEHRERE CHANNELS)
    if message.channel.id in COMMAND_ONLY_CHANNEL_IDS:
        ctx = await bot.get_context(message)
        if not ctx.valid:
            try:
                await message.delete()
            except:
                pass
            return


    # 🚫 KEINE /BEFEHLE ERLAUBT (MEHRERE CHANNELS)
    if message.channel.id in NO_COMMANDS_CHANNEL_IDS:
        ctx = await bot.get_context(message)
        if ctx.valid:
            try:
                await message.delete()
            except:
                pass
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
    # ================== TEXT XP (MIT COOLDOWN) ==================

    # ❌ KEIN XP für Commands
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.process_commands(message)
        return

    now = time.time()
    last = last_message_xp.get(message.author.id, 0)

    # ✅ XP nur alle 10 Minuten
    if now - last >= MESSAGE_XP_COOLDOWN:
        await add_xp(message.author, 1)
        last_message_xp[message.author.id] = now

    # ================== TEXT COINS (ALLE 100 NACHRICHTEN) ==================

    user = get_user(message.author.id)
    if user["messages"] % 20 == 0:
        cur.execute(
            "UPDATE users SET coins = coins + 10 WHERE user_id = ?",
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
    await bot.tree.sync()
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
                    name=f"#{i+1}",
                    value=(
                        f"{member.mention}\n"
                        f"{XP_EMOJI} XP: {row['weekly_xp']}\n"
                        f"💬 Nachrichten: {row['weekly_messages']}\n"
                        f"🎙 Voice: {int(row['weekly_voice_seconds']//60)} Min\n"
                        f"{COIN_EMOJI} +{rewards[i]} Coins"
                    ),
                    inline=False
                )


                

            await channel.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)

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
    await bot.wait_until_ready()
    while True:
        await asyncio.sleep(300)  # alle 5 Minuten
        now = time.time()

        for (u1, u2), data in list(pending_gambles.items()):
            if now - data["created_at"] > 300:
                coins = data["coins"]

                # Coins nur zurückgeben, wenn das Gamble noch reserviert ist
                if has_active_gamble(u1):
                    release_coins(u1)

                if u2 != bot.user.id and has_active_gamble(u2):
                    release_coins(u2)

                pending_gambles.pop((u1, u2), None)




# ================== START ==================

bot.run(os.environ["DISCORD_TOKEN"])

