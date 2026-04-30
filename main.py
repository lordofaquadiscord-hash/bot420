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

REACTION_ROLE_FILE = "reaction_roles.json"


XP_NAME = "Weedpunkte"
LEVEL_NAME = "Weedstufe"
COIN_NAME = "Kiffer Coins"

XP_EMOJI = "<:weed_punkte:1475190720687243396>"
LEVEL_EMOJI = "<:weed_stufe:1475190650688376982>"
COIN_EMOJI = "<:kiffer_coins:1475190767961243719>"

LEVEL_UP_CHANNEL_ID = 1475186463946575873

BOT_OWNER_ID = 773442243138813982  # â† HIER DEINE DISCORD ID EINTRAGEN

last_weekly_reset = None

GUILD_ID = 983743026704826448

# ================== CHANNEL RESTRIKTIONEN ==================

COMMAND_ONLY_CHANNEL_IDS = [
    1464627521675984948,  # z.B. /commands
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


BLACKJACK_CHANNEL_ID = 1464627857497264288  # â¬…ï¸ Blackjack-Channel-ID

GIVEAWAY_CHANNEL_ID = 1475185983053103381  # <- dein Giveaway Channel

# KartenrÃ¼ckseite (optional)
CARD_BACK_IMAGE = "https://media.discordapp.net/attachments/1039293219491565621/1465151863514206361/content.png?ex=69781081&is=6976bf01&hm=a10cbdeed96afece3727d9cbf39959a82d89d640607ff10bf468a4ab64bc3f17&=&format=webp&quality=lossless&width=640&height=960"

# =====================================================
# ðŸƒ KARTEN & DECK
# =====================================================

SUITS = ["â™ ", "â™¥", "â™¦", "â™£"]
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

MINIGAME_CHANNEL_ID = 1464627521675984948  # â† HIER deinen Minigame-Kanal eintragen


# ================== BOT SETUP ==================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

class MyBot(commands.Bot):
    async def setup_hook(self):
        self.loop.create_task(weekly_reset_task())
        self.loop.create_task(giveaway_task())
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
    "schlampe","opfer","spasti","behindert","hund","kÃ¶ter",
    "jude","huso","gefickt","lutsch","mongo","wixxer","wichser"
]

WELCOME_CHANNEL_ID = 983743026704826450
AUTO_ROLE_ID = 983752389502836786
WELCOME_IMAGE_URL = "https://media.discordapp.net/attachments/1039293219491565621/1462608302033731680/gaming420.png?format=webp&quality=lossless"
LOG_CHANNEL_ID = 1462152930768589023


# ================== COIN REWARDS KONFIG ==================

COIN_REWARDS = {
    "message_bonus": 100,      # aktuell: 100 Coins pro 20 Nachrichten (wird indirekt genutzt)
    "voice_hour": 250,       # aktuell: 250 Coins pro Stunde Voice
    "level_up": 200,         # aktuell: +200 Coins pro Level
    "weekly": [800, 500, 300]
}

# ================== DATENBANK ==================

conn = sqlite3.connect("botdata.db", check_same_thread=False)
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

cur.execute("""
CREATE TABLE IF NOT EXISTS giveaways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    description TEXT,
    price INTEGER,
    reward INTEGER,
    winners INTEGER,
    channel_id INTEGER,
    message_id INTEGER,
    created_at INTEGER,
    ends_at INTEGER,
    active INTEGER DEFAULT 1
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS giveaway_entries (
    giveaway_id INTEGER,
    user_id INTEGER,
    PRIMARY KEY (giveaway_id, user_id)
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

def is_bot_owner(obj):
    user = obj.user if hasattr(obj, "user") else obj.author
    return user.id == BOT_OWNER_ID

async def owner_only(obj):
    if not is_bot_owner(obj):
        if hasattr(obj, "response"):
            await obj.response.send_message("âŒ Keine Berechtigung", ephemeral=True)
        else:
            await obj.send("âŒ Keine Berechtigung")
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
# ðŸŽ° BLACKJACK SESSION
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
# ðŸŽ® VIEW & BUTTONS
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
                content="â±ï¸ Blackjack abgebrochen (Timeout).",
                view=None
            )
        except:
            pass


    async def interaction_check(self, interaction):
        return interaction.user.id == self.session.user_id

    def build_embed(self, final=False):
        embed = discord.Embed(
            title="ðŸƒ Blackjack",
            color=discord.Color.gold()
        )

        for i, hand in enumerate(self.session.hands):
            marker = "ðŸ‘‰ " if i == self.session.current_hand and not final else ""
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
            dealer_cards = f"{self.session.dealer[0][0]}{self.session.dealer[0][1]} ðŸ‚ "

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
                result_text += "âŒ Bust\n"

            elif val == 21 and len(hand) == 2:
                # Blackjack 3:2 Auszahlung (aufgerundet)
                payout = math.ceil(self.session.bet * 2.5)
                change_coins(self.session.user_id, payout)
                result_text += f"ðŸƒ Blackjack! (+{payout - self.session.bet} {COIN_NAME})\n"

            elif dealer_val > 21 or val > dealer_val:
                change_coins(self.session.user_id, self.session.bet * 2)
                result_text += "âœ… Gewinn\n"

            elif val == dealer_val:
                change_coins(self.session.user_id, self.session.bet)
                result_text += "âž– Push\n"

            else:
                result_text += "âŒ Verlust\n"


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
            await interaction.response.send_message("âŒ Split nicht mÃ¶glich.", ephemeral=True)
            return

        if not has_enough_coins(self.session.user_id, self.session.bet):
            await interaction.response.send_message("âŒ Nicht genug Coins fÃ¼r Split.", ephemeral=True)
            return

        change_coins(self.session.user_id, -self.session.bet)
        self.session.split()
        await interaction.response.edit_message(embed=self.build_embed())

    @discord.ui.button(label="Double", style=discord.ButtonStyle.danger)
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not self.session.can_double():
            await interaction.response.send_message(
                "âŒ Double Down ist nur bei genau 2 Karten mÃ¶glich.",
                ephemeral=True
            )
            return

        if not has_enough_coins(self.session.user_id, self.session.bet):
            await interaction.response.send_message(
                "âŒ Nicht genug Coins fÃ¼r Double Down.",
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
    (0 XP Fortschritt ins nÃ¤chste Level)
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
        coins += COIN_REWARDS["level_up"]
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
                    f"ðŸ”¥ **{member.mention}** ist aufgestiegen!\n\n"
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
                "UPDATE users SET coins = coins + ? WHERE user_id = ?",
                (COIN_REWARDS["voice_hour"], uid)
            )
            conn.commit()
    # ================== VOICE LOGS ==================

    # ðŸ”Š Channel Join
    if before.channel is None and after.channel is not None:
        await send_log(
            member.guild,
            "Voice beigetreten",
            f"**User:** {member.mention}\n**Channel:** {after.channel.mention}",
            discord.Color.green()
        )

    # ðŸ”‡ Channel verlassen
    if before.channel is not None and after.channel is None:
        await send_log(
            member.guild,
            "Voice verlassen",
            f"**User:** {member.mention}\n**Channel:** {before.channel.mention}",
            discord.Color.red()
        )

    # ðŸ” Channel gewechselt
    if before.channel and after.channel and before.channel != after.channel:
        await send_log(
            member.guild,
            "Voice gewechselt",
            (
                f"**User:** {member.mention}\n"
                f"**Von:** {before.channel.mention}\n"
                f"**Nach:** {after.channel.mention}"
            ),
            discord.Color.blue()
        )

    # ðŸ”‡ Server Mute
    if not before.mute and after.mute:
        moderator = "Unbekannt"
        async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
            if entry.target.id == member.id:
                moderator = entry.user.mention
                break

        await send_log(
            member.guild,
            "Voice stummgeschaltet",
            f"**User:** {member.mention}\n**Von:** {moderator}",
            discord.Color.orange()
        )

    # ðŸ”Š Server Unmute
    if before.mute and not after.mute:
        moderator = "Unbekannt"
        async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
            if entry.target.id == member.id:
                moderator = entry.user.mention
                break

        await send_log(
            member.guild,
            "Voice entstummt",
            f"**User:** {member.mention}\n**Von:** {moderator}",
            discord.Color.green()
        )

    # ðŸŽ§ Deaf
    if not before.deaf and after.deaf:
        moderator = "Unbekannt"
        async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
            if entry.target.id == member.id:
                moderator = entry.user.mention
                break

        await send_log(
            member.guild,
            "Voice taub geschaltet",
            f"**User:** {member.mention}\n**Von:** {moderator}",
            discord.Color.orange()
        )

    # ðŸŽ§ Undeaf
    if before.deaf and not after.deaf:
        moderator = "Unbekannt"
        async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
            if entry.target.id == member.id:
                moderator = entry.user.mention
                break

        await send_log(
            member.guild,
            "Voice Taubheit entfernt",
            f"**User:** {member.mention}\n**Von:** {moderator}",
            discord.Color.green()
        )




# ================== REACTION ROLES ==================

REACTION_ROLE_CHANNEL_ID = 983775494388461578

REACTION_ROLE_CONFIG = {
    "games": {
        "type": "multi",
        "title": "ðŸŽ® Spiele",
        "description": "WÃ¤hle die Spiele aus, die du spielst:",
        "roles": {
            "<:minecraft:1154917299145429083>": 1111976466868080682,
            "<:valorant:1154917333719072848>": 983750378396979290,
            "<:fortnite:1154917530989772800>": 983750983182061569,
            "<:gta5:1258452798719135825>": 1258450337665253437
        }
    },
    "valorant_rank": {
        "type": "single",
        "title": "ðŸ† Valorant Rang",
        "description": "WÃ¤hle **einen** Valorant Rang:",
        "roles": {
            "<:valorant_iron:1154918607462092821>": 1463382014395809813,
            "<:valorant_bronze:1475193587896684576>": 1463382723308814508,
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
        "title": "ðŸ”” Pings",
        "description": "WÃ¤hle, fÃ¼r welche Pings du benachrichtigt werden mÃ¶chtest:",
        "roles": {
            "<:valorant_competetive:1475190933153644829>": 1463384039410110494,
            "<:valorant_customs:1475190844406497410>": 1463384082120441967,
            "<:valorant_unrated:1475191000824549387>": 1463635078046552188
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

# ================== LOG SYSTEM ==================
# Zentrale Funktion fÃ¼r schÃ¶ne & einheitliche Logs

async def send_log(
    guild,
    title,
    description,
    color=discord.Color.dark_gray()
):
    """
    Universelle Log-Funktion
    â†’ sorgt fÃ¼r einheitliches Design
    â†’ einfach Ã¼berall wiederverwendbar
    """

    if not guild:
        return

    channel = guild.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return

    embed = discord.Embed(
        title=f"ðŸ“Œ {title}",
        description=description,
        color=color,
        timestamp=datetime.utcnow()
    )

    embed.set_footer(text=f"{guild.name}")

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

@bot.tree.command(
    name="blackjack",
    description="Spiele Blackjack mit Kiffer Coins",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.describe(coins="Einsatz")
async def blackjack(interaction: discord.Interaction, coins: int):



    if interaction.channel.id != BLACKJACK_CHANNEL_ID:
        await interaction.response.send_message(
            "âŒ Blackjack ist nur im Blackjack-Channel erlaubt.",
            ephemeral=True
        )
        return

    user_id = interaction.user.id

    if coins <= 0:
        await interaction.response.send_message("âŒ UngÃ¼ltiger Einsatz.", ephemeral=True)
        return

    if has_active_gamble(user_id):
        await interaction.response.send_message(
            "âŒ Du spielst bereits ein GlÃ¼cksspiel.",
            ephemeral=True
        )
        return

    if not has_enough_coins(user_id, coins):
        await interaction.response.send_message(
            "âŒ Nicht genug Kiffer Coins.",
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

class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    async def update_embed(self, interaction):
        cur.execute("SELECT * FROM giveaways WHERE id = ?", (self.giveaway_id,))
        g = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) FROM giveaway_entries
            WHERE giveaway_id = ?
        """, (self.giveaway_id,))
        count = cur.fetchone()[0]

        embed = interaction.message.embeds[0]

        embed.set_field_at(
            0,
            name="ðŸ‘¥ Teilnehmer",
            value=str(count),
            inline=False
        )

        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Teilnehmen ðŸŽ‰", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):

        user_id = interaction.user.id

        cur.execute("SELECT * FROM giveaways WHERE id = ?", (self.giveaway_id,))
        g = cur.fetchone()

        if not g or g["active"] == 0:
            await interaction.response.send_message("âŒ Giveaway beendet.", ephemeral=True)
            return

        cur.execute("""
            SELECT 1 FROM giveaway_entries
            WHERE giveaway_id = ? AND user_id = ?
        """, (self.giveaway_id, user_id))

        if cur.fetchone():
            await interaction.response.send_message("âŒ Du bist schon dabei.", ephemeral=True)
            return

        user = get_user(user_id)

        if user["coins"] < g["price"]:
            await interaction.response.send_message("âŒ Nicht genug Coins.", ephemeral=True)
            return

        change_coins(user_id, -g["price"])

        cur.execute("""
            INSERT INTO giveaway_entries (giveaway_id, user_id)
            VALUES (?, ?)
        """, (self.giveaway_id, user_id))
        conn.commit()

        await interaction.response.send_message("âœ… Du bist dabei!", ephemeral=True)

        await self.update_embed(interaction)

# ================== TOP LISTS ==================

@bot.tree.command(
    name="listcoin",
    description="Top 10 Spieler nach Coins",
    guild=discord.Object(id=GUILD_ID)
)
async def listcoin(interaction: discord.Interaction):

    cur.execute("""
        SELECT user_id, coins FROM users
        ORDER BY coins DESC
        LIMIT 10
    """)
    rows = cur.fetchall()

    embed = discord.Embed(
        title="ðŸ† Top 10 Coins",
        color=discord.Color.gold()
    )

    for i, row in enumerate(rows, start=1):
        member = interaction.guild.get_member(row["user_id"])
        if member:
            embed.add_field(
                name=f"#{i}",
                value=f"{member.mention}\n{row['coins']} {COIN_NAME}",
                inline=False
            )

    await interaction.response.send_message(embed=embed, allowed_mentions=ALLOWED_MENTIONS)


@bot.tree.command(
    name="listvoice",
    description="Top 10 Voice Zeit (gesamt)",
    guild=discord.Object(id=GUILD_ID)
)
async def listvoice(interaction: discord.Interaction):

    cur.execute("""
        SELECT user_id, voice_seconds FROM users
        ORDER BY voice_seconds DESC
        LIMIT 10
    """)
    rows = cur.fetchall()

    embed = discord.Embed(
        title="ðŸŽ™ Top 10 Voice (gesamt)",
        color=discord.Color.blurple()
    )

    for i, row in enumerate(rows, start=1):
        member = interaction.guild.get_member(row["user_id"])
        if member:
            minutes = math.ceil(row["voice_seconds"] / 60)
            embed.add_field(
                name=f"#{i}",
                value=f"{member.mention}\n{minutes} Minuten",
                inline=False
            )

    await interaction.response.send_message(embed=embed, allowed_mentions=ALLOWED_MENTIONS)


@bot.tree.command(
    name="listvoiceweek",
    description="Top 10 Voice Zeit (Woche)",
    guild=discord.Object(id=GUILD_ID)
)
async def listvoiceweek(interaction: discord.Interaction):

    cur.execute("""
        SELECT user_id, weekly_voice_seconds FROM users
        ORDER BY weekly_voice_seconds DESC
        LIMIT 10
    """)
    rows = cur.fetchall()

    embed = discord.Embed(
        title="ðŸŽ™ Top 10 Voice (Woche)",
        color=discord.Color.purple()
    )

    for i, row in enumerate(rows, start=1):
        member = interaction.guild.get_member(row["user_id"])
        if member:
            minutes = math.ceil(row["weekly_voice_seconds"] / 60)
            embed.add_field(
                name=f"#{i}",
                value=f"{member.mention}\n{minutes} Minuten",
                inline=False
            )

    await interaction.response.send_message(embed=embed, allowed_mentions=ALLOWED_MENTIONS)


@bot.tree.command(
    name="listtext",
    description="Top 10 Nachrichten (gesamt)",
    guild=discord.Object(id=GUILD_ID)
)
async def listtext(interaction: discord.Interaction):

    cur.execute("""
        SELECT user_id, messages FROM users
        ORDER BY messages DESC
        LIMIT 10
    """)
    rows = cur.fetchall()

    embed = discord.Embed(
        title="ðŸ’¬ Top 10 Nachrichten (gesamt)",
        color=discord.Color.green()
    )

    for i, row in enumerate(rows, start=1):
        member = interaction.guild.get_member(row["user_id"])
        if member:
            embed.add_field(
                name=f"#{i}",
                value=f"{member.mention}\n{row['messages']} Nachrichten",
                inline=False
            )

    await interaction.response.send_message(embed=embed, allowed_mentions=ALLOWED_MENTIONS)


@bot.tree.command(
    name="listtextweek",
    description="Top 10 Nachrichten (Woche)",
    guild=discord.Object(id=GUILD_ID)
)
async def listtextweek(interaction: discord.Interaction):

    cur.execute("""
        SELECT user_id, weekly_messages FROM users
        ORDER BY weekly_messages DESC
        LIMIT 10
    """)
    rows = cur.fetchall()

    embed = discord.Embed(
        title="ðŸ’¬ Top 10 Nachrichten (Woche)",
        color=discord.Color.teal()
    )

    for i, row in enumerate(rows, start=1):
        member = interaction.guild.get_member(row["user_id"])
        if member:
            embed.add_field(
                name=f"#{i}",
                value=f"{member.mention}\n{row['weekly_messages']} Nachrichten",
                inline=False
            )

    await interaction.response.send_message(embed=embed, allowed_mentions=ALLOWED_MENTIONS)


@bot.command()
async def stats(ctx, member: discord.Member = None):
    member = member or ctx.author
    user = get_user(member.id)

    needed = xp_needed_for_level(user["level"] + 1)
    rank = get_rank(member.id)

    embed = discord.Embed(
        title=f"ðŸ“Š Stats von {member.display_name}",
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
        name="ðŸ† Rang",
        value=f"#{rank}",
        inline=True
    )

    embed.add_field(name="ðŸ’¬ Nachrichten", value=user["messages"], inline=True)
    embed.add_field(
        name="ðŸŽ™ Voice-Zeit",
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
        title=f"ðŸ“Š Wochen-Stats von {member.display_name}",
        color=discord.Color.purple()
    )

    embed.add_field(name=f"{XP_EMOJI} {XP_NAME}", value=user["weekly_xp"])
    embed.add_field(name="ðŸ’¬ Nachrichten", value=user["weekly_messages"])
    embed.add_field(
        name="ðŸŽ™ Voice-Zeit",
        value=f"{int(user['weekly_voice_seconds']//60)} Minuten"
    )

    embed.add_field(name="ðŸ† Wochenrang", value=f"#{rank}")

    await ctx.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)

@bot.command()
async def list(ctx):
    cur.execute("""
        SELECT user_id, total_xp FROM users
        ORDER BY total_xp DESC LIMIT 10
    """)
    rows = cur.fetchall()

    embed = discord.Embed(title="ðŸ† Top 10 Rangliste", color=discord.Color.gold())

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

    embed = discord.Embed(title="ðŸ† Wochenrangliste", color=discord.Color.purple())

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
                text += f"{emoji} â†’ {role.mention}\n"

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
        await ctx.send("âŒ Der Einsatz muss grÃ¶ÃŸer als 0 sein.")
        return
    if has_active_gamble(ctx.author.id):
        await ctx.send("âŒ Du hast bereits ein aktives GlÃ¼cksspiel.")
        return
    if ctx.channel.id != MINIGAME_CHANNEL_ID:
        return

    if not has_enough_coins(ctx.author.id, coins):
        await ctx.send("âŒ Du hast nicht genug Coins.")
        return
    # Einsatz abziehen
    change_coins(ctx.author.id, -coins)
    reserve_gamble(ctx.author.id, bot.user.id)

    user_roll = random.randint(1, 6)
    bot_roll = random.randint(1, 6)

    embed = discord.Embed(
        title="ðŸŽ² WÃ¼rfelspiel gegen den Bot",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="Spieler",
        value=f"{ctx.author.mention}\nðŸŽ² {user_roll}",
        inline=True
    )
    embed.add_field(name="ðŸ¤– Bot", value=f"ðŸŽ² {bot_roll}")

    if user_roll > bot_roll:
        change_coins(ctx.author.id, coins * 2)
        result = f"âœ… Du gewinnst **{coins} {COIN_NAME}**!"
    elif user_roll < bot_roll:
        result = f"âŒ Du verlierst **{coins} {COIN_NAME}**."
    else:
        change_coins(ctx.author.id, coins)
        result = "âž– Unentschieden â€“ Einsatz zurÃ¼ck."


    embed.add_field(name="Ergebnis", value=result, inline=False)
    await ctx.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)
    release_coins(ctx.author.id)


@bot.command()
async def gambleinvite(ctx, opponent: discord.Member, coins: int):
    if coins <= 0:
        await ctx.send("âŒ Der Einsatz muss grÃ¶ÃŸer als 0 sein.")
        return
    if (ctx.author.id, opponent.id) in pending_gambles or (opponent.id, ctx.author.id) in pending_gambles:
        await ctx.send("âŒ Zwischen euch gibt es bereits eine offene Einladung.")
        return
    if has_active_gamble(ctx.author.id) or has_active_gamble(opponent.id):
        await ctx.send("âŒ Einer von euch hat bereits ein aktives GlÃ¼cksspiel.")
        return
    if ctx.channel.id != MINIGAME_CHANNEL_ID:
        return

    if opponent.bot or opponent == ctx.author:
        return

    if not has_enough_coins(ctx.author.id, coins) or not has_enough_coins(opponent.id, coins):
        await ctx.send("âŒ Einer von euch hat nicht genug Coins.")
        return



    reserve_gamble(ctx.author.id, opponent.id)
    reserve_gamble(opponent.id, ctx.author.id)
    pending_gambles[(ctx.author.id, opponent.id)] = {
        "coins": coins,
        "created_at": time.time()
    }

    embed = discord.Embed(
        title="ðŸŽ² WÃ¼rfel-Herausforderung",
        description=(
            f"{ctx.author.mention} fordert {opponent.mention} heraus!\n"
            f"Einsatz: **{coins} {COIN_NAME}**\n\n"
            f"{opponent.mention} â†’ nutze `/gambleaccept {ctx.author.mention}`"
        ),
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)

@bot.command()
async def gambleaccept(ctx, opponent: discord.Member):
    if ctx.channel.id != MINIGAME_CHANNEL_ID:
        return
    if not has_active_gamble(ctx.author.id):
        await ctx.send("âŒ Dein Einsatz ist nicht mehr reserviert.")
        return
    if not has_active_gamble(opponent.id):
        await ctx.send("âŒ Der Gegner hat kein aktives GlÃ¼cksspiel mehr.")
        return
    if (opponent.id, ctx.author.id) not in pending_gambles:
        await ctx.send("âŒ Keine offene Herausforderung gefunden.")
        return
    key = (opponent.id, ctx.author.id)

    data = pending_gambles.pop(key, None)
    if not data:
        await ctx.send("âŒ Diese Herausforderung ist nicht mehr gÃ¼ltig.")
        return

    coins = data["coins"]
    change_coins(ctx.author.id, -coins)
    change_coins(opponent.id, -coins)



    roll1 = random.randint(1, 6)
    roll2 = random.randint(1, 6)

    embed = discord.Embed(
        title="ðŸŽ² WÃ¼rfelduell",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="Spieler 1",
        value=f"{opponent.mention}\nðŸŽ² {roll1}",
        inline=True
    )

    embed.add_field(
        name="Spieler 2",
        value=f"{ctx.author.mention}\nðŸŽ² {roll2}",
        inline=True
    )

    if roll1 > roll2:
        change_coins(opponent.id, coins * 2)
        result = f"ðŸ† {opponent.mention} gewinnt!"
    elif roll2 > roll1:
        change_coins(ctx.author.id, coins * 2)
        result = f"ðŸ† {ctx.author.mention} gewinnt!"
    else:
        change_coins(ctx.author.id, coins)
        change_coins(opponent.id, coins)
        result = "âž– Unentschieden â€“ Coins zurÃ¼ck."


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
    embed = user_stats_embed(member, user, "ðŸ›  Coins gesetzt")
    await ctx.send(embed=embed)


@bot.command()
async def addcoins(ctx, member: discord.Member, coins: int):
    if not await owner_only(ctx):
        return

    cur.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (coins, member.id))
    conn.commit()

    user = get_user(member.id)
    embed = user_stats_embed(member, user, "âž• Coins hinzugefÃ¼gt")
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
    embed = user_stats_embed(member, user, "ðŸ›  XP gesetzt (Level synchronisiert)")
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
    embed = user_stats_embed(member, user, "âž• XP hinzugefÃ¼gt (Level synchronisiert)")
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
    embed = user_stats_embed(member, user, "ðŸ›  Level gesetzt (XP synchronisiert)")
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
    embed = user_stats_embed(member, user, "âž• Level hinzugefÃ¼gt (XP synchronisiert)")
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
    embed = user_stats_embed(member, user, "â™» User zurÃ¼ckgesetzt")
    await ctx.send(embed=embed)


@bot.command()
async def resetcoins(ctx, member: discord.Member):
    if not await owner_only(ctx):
        return

    cur.execute("UPDATE users SET coins = 0 WHERE user_id = ?", (member.id,))
    conn.commit()

    user = get_user(member.id)
    embed = user_stats_embed(member, user, "â™» Coins zurÃ¼ckgesetzt")
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
        title="âš ï¸ GLOBAL RESET",
        description="Alle User wurden vollstÃ¤ndig zurÃ¼ckgesetzt.",
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
        title="ðŸ›  Coins global gesetzt",
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
        title="âž• Coins global hinzugefÃ¼gt",
        description=f"Allen Usern wurden **{coins} {COIN_NAME}** hinzugefÃ¼gt",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)


@bot.tree.command(
    name="startgiveaway",
    description="Startet ein Giveaway",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.describe(
    name="Name des Giveaways",
    description="Beschreibung des Giveaways",
    price="Teilnahmekosten (0 = kostenlos)",
    winners="Anzahl Gewinner",
    reward="Gewinn pro Gewinner"
)
async def startgiveaway(
    interaction: discord.Interaction,
    name: str,
    description: str,
    price: int,
    winners: int,
    reward: int = 0
):
    if not await owner_only(interaction):
        return

    if not name or not description:
        await interaction.response.send_message(
            "âŒ Name und Beschreibung sind Pflicht.",
            ephemeral=True
        )
        return

    if price is None or winners is None:
        await interaction.response.send_message("âŒ Preis und Gewinneranzahl fehlen.")
        return

    if price < 0 or winners <= 0:
        await interaction.response.send_message("âŒ UngÃ¼ltige Werte.")
        return

    now = int(time.time())
    ends_at = now + 86400

    channel = interaction.guild.get_channel(GIVEAWAY_CHANNEL_ID)

    embed = discord.Embed(
        title="ðŸŽ‰ Giveaway (wird gleich aktualisiert)",
        description=description,
        color=discord.Color.gold()
    )

    embed.add_field(name="ðŸ‘¥ Teilnehmer", value="0", inline=False)
    embed.add_field(name="ðŸ† Gewinner", value=str(winners), inline=False)

    if price == 0:
        embed.add_field(name="ðŸ’¸ Teilnahme", value="Kostenlos", inline=False)
    else:
        embed.add_field(
            name="ðŸ’¸ TeilnahmegebÃ¼hr",
            value=f"{price} {COIN_EMOJI} {COIN_NAME}",
            inline=False
        )

    if reward > 0:
        embed.add_field(
            name="ðŸŽ Gewinn pro Gewinner",
            value=f"{reward} {COIN_EMOJI}",
            inline=False
        )

    msg = await channel.send(embed=embed)

    cur.execute("""
        INSERT INTO giveaways
        (name, description, price, reward, winners, channel_id, message_id, created_at, ends_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, description, price, reward, winners, channel.id, msg.id, now, ends_at))
    conn.commit()

    gid = cur.lastrowid

    embed.title = f"ðŸŽ‰ Giveaway Nr. {gid} | {name}"
    await msg.edit(embed=embed, view=GiveawayView(gid))

    await interaction.response.send_message(f"âœ… Giveaway #{gid} gestartet!", ephemeral=True)


@bot.command()
async def endgiveaway(ctx, giveaway_id: int):
    if not await owner_only(ctx):
        return

    await end_giveaway(giveaway_id, ctx.guild)
    await ctx.send(f"âœ… Giveaway #{giveaway_id} beendet.")


# ================== EVENTS ==================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # âŒ KEINE DMs (Bugfix gegen DM-Spam)
    if message.guild is None:
        return
    # ================== CHANNEL RESTRIKTIONEN ==================


    # ðŸ”’ NUR /BEFEHLE ERLAUBT (MEHRERE CHANNELS)
    if message.channel.id in COMMAND_ONLY_CHANNEL_IDS:

        # âœ… Slash-Command-Systemnachrichten IMMER erlauben
        if message.type == discord.MessageType.chat_input_command:
            return

        ctx = await bot.get_context(message)

        if not ctx.valid:
            try:
                await message.delete()
            except:
                pass
            return


    # ðŸš« KEINE /BEFEHLE ERLAUBT (MEHRERE CHANNELS)
    if message.channel.id in NO_COMMANDS_CHANNEL_IDS:
        ctx = await bot.get_context(message)

        # â›” Slash-Command-Systemnachrichten lÃ¶schen (gewollt!)
        if message.type == discord.MessageType.chat_input_command:
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
            await send_log(
                message.guild,
                "ðŸš« Nachricht gelÃ¶scht (Blacklist)",
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

    # âŒ KEIN XP fÃ¼r Commands
    ctx = await bot.get_context(message)
    await bot.process_commands(message)

    if ctx.valid:
        return

    now = time.time()
    last = last_message_xp.get(message.author.id, 0)

    # âœ… XP nur alle 10 Minuten
    if now - last >= MESSAGE_XP_COOLDOWN:
        await add_xp(message.author, 1)
        last_message_xp[message.author.id] = now

    # ================== TEXT COINS (ALLE 100 NACHRICHTEN) ==================

    user = get_user(message.author.id)
    if user["messages"] % 20 == 0:
        cur.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?",
            (COIN_REWARDS["message_bonus"], message.author.id)
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
            title="Herzlich Willkommen! ðŸŽ‰",
            description=f"Tachchen {member.mention}, willkommen bei Gaming 420!",
            color=discord.Color.green()
        )
        embed.set_image(url=WELCOME_IMAGE_URL)
        await channel.send(embed=embed)

# ================== MODERATION LOGS ==================

@bot.event
async def on_member_ban(guild, user):
    banner = "Unbekannt"

    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
        if entry.target.id == user.id:
            banner = entry.user.mention
            break

    await send_log(
        guild,
        "User gebannt",
        f"**User:** {user.mention}\n**Von:** {banner}",
        discord.Color.dark_red()
    )


@bot.event
async def on_member_remove(member):
    # Kann Kick ODER Leave sein â†’ prÃ¼fen
    guild = member.guild
    kicker = None

    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
        if entry.target.id == member.id:
            kicker = entry.user.mention
            break

    if kicker:
        await send_log(
            guild,
            "User gekickt",
            f"**User:** {member.mention}\n**Von:** {kicker}",
            discord.Color.red()
        )

@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.message_id) not in REACTION_ROLE_MESSAGES:
        return

    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
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
    print(f"âœ… Bot online als {bot.user}")

    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)

    print("âœ… Slash Commands fÃ¼r Guild synchronisiert")
    # ðŸ”„ ABGEBROCHENE GAMBLES NACH RESTART AUFRÃ„UMEN
    cur.execute("SELECT user_id FROM active_gambles")
    rows = cur.fetchall()

    for row in rows:
        uid = row["user_id"]
        # Coins zurÃ¼ckgeben (wir wissen hier nicht wie viele â†’ safe LÃ¶sung)
        # â†’ KEINE RÃ¼ckgabe, sondern nur Freigabe
        release_coins(uid)

    pending_gambles.clear()

    now = time.time()

    # ðŸ”Š ALLE User, die gerade im Voice sind, erfassen
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for member in vc.members:
                voice_times[member.id] = now





@bot.event
async def on_message_delete(message):
    if not message.guild or message.author.bot:
        return

    deleter = None

    async for entry in message.guild.audit_logs(limit=5, action=discord.AuditLogAction.message_delete):
        if entry.target.id == message.author.id and entry.extra and entry.extra.channel.id == message.channel.id:
            deleter = entry.user.mention
            break

    # ðŸ”¥ FALLBACK: User hat selbst gelÃ¶scht
    if deleter is None:
        deleter = f"{message.author.mention} (Selbst gelÃ¶scht)"

    content = message.content if message.content else "*Keine Nachricht / Embed / Datei*"

    await send_log(
        message.guild,
        "Nachricht gelÃ¶scht",
        (
            f"**Autor:** {message.author.mention}\n"
            f"**GelÃ¶scht von:** {deleter}\n"
            f"**Channel:** {message.channel.mention}\n\n"
            f"**Inhalt:**\n```{content}```"
        ),
        discord.Color.red()
    )

@bot.event
async def on_message_edit(before, after):
    if not before.guild or after.author.bot:
        return

    if before.content == after.content:
        return

    before_content = before.content or "*Kein Text*"
    after_content = after.content or "*Kein Text*"

    await send_log(
        before.guild,
        "Nachricht bearbeitet",
        (
            f"**Autor:** {after.author.mention}\n"
            f"**Channel:** {after.channel.mention}\n\n"
            f"**Vorher:**\n```{before_content}```\n\n"
            f"**Nachher:**\n```{after_content}```"
        ),
        discord.Color.orange()
    )

@bot.event
async def on_guild_channel_create(channel):
    creator = "Unbekannt"

    async for entry in channel.guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_create):
        if entry.target.id == channel.id:
            creator = entry.user.mention
            break

    await send_log(
        channel.guild,
        f"{'Kategorie' if str(channel.type) == 'category' else 'Channel'} erstellt",
        f"**Name:** {channel.name}\n**Channel:** {channel.mention if hasattr(channel, 'mention') else channel.name}\n**Von:** {creator}",
        discord.Color.green()
    )

@bot.event
async def on_guild_channel_delete(channel):
    deleter = "Unbekannt"

    async for entry in channel.guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_delete):
        if entry.target.id == channel.id:
            deleter = entry.user.mention
            break

    await send_log(
        channel.guild,
        f"{'Kategorie' if str(channel.type) == 'category' else 'Channel'} gelÃ¶scht",
        f"**Name:** {channel.name}\n**Von:** {deleter}",
        discord.Color.red()
    )


# ================== CHANNEL PERMISSIONS ==================

@bot.event
async def on_guild_channel_update(before, after):

    if before.overwrites != after.overwrites:
        moderator = "Unbekannt"

        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_update):
            if entry.target.id == after.id:
                moderator = entry.user.mention
                break

        await send_log(
            after.guild,
            "Channel Berechtigungen geÃ¤ndert",
            (
                f"**Channel:** {after.mention}\n"
                f"**Von:** {moderator}"
            ),
            discord.Color.blurple()
        )

# ================== ROLLEN LOGS ==================

@bot.event
async def on_guild_role_create(role):
    creator = "Unbekannt"

    async for entry in role.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_create):
        if entry.target.id == role.id:
            creator = entry.user.mention
            break

    await send_log(
        role.guild,
        "Rolle erstellt",
        f"**Rolle:** {role.mention}\n**Von:** {creator}",
        discord.Color.green()
    )


@bot.event
async def on_guild_role_delete(role):
    deleter = "Unbekannt"

    async for entry in role.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_delete):
        if entry.target.id == role.id:
            deleter = entry.user.mention
            break

    await send_log(
        role.guild,
        "Rolle gelÃ¶scht",
        f"**Rolle:** {role.name}\n**Von:** {deleter}",
        discord.Color.red()
    )

@bot.event
async def on_member_update(before, after):

    # ================== ROLLEN Ã„NDERUNGEN ==================
    before_roles = set(before.roles)
    after_roles = set(after.roles)

    added_roles = after_roles - before_roles
    removed_roles = before_roles - after_roles

    if added_roles or removed_roles:

        moderator = "Unbekannt"

        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
            if entry.target.id == after.id:
                moderator = entry.user.mention
                break

        for role in added_roles:
            await send_log(
                after.guild,
                "Rolle hinzugefÃ¼gt",
                (
                    f"**User:** {after.mention}\n"
                    f"**Von:** {moderator}\n"
                    f"**Rolle:** {role.mention}"
                ),
                discord.Color.green()
            )

        for role in removed_roles:
            await send_log(
                after.guild,
                "Rolle entfernt",
                (
                    f"**User:** {after.mention}\n"
                    f"**Von:** {moderator}\n"
                    f"**Rolle:** {role.mention}"
                ),
                discord.Color.red()
            )

    # ================== NICKNAME ==================
    if before.nick != after.nick:

        old = before.nick or before.name
        new = after.nick or after.name

        changer = "Unbekannt"

        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
            if entry.target.id == after.id:
                changer = entry.user.mention
                break

        await send_log(
            after.guild,
            "Nickname geÃ¤ndert",
            (
                f"**User:** {after.mention}\n"
                f"**GeÃ¤ndert von:** {changer}\n\n"
                f"**Vorher:** {old}\n"
                f"**Nachher:** {new}"
            ),
            discord.Color.blue()
        )

    # ================== TIMEOUT ==================
    if before.timed_out_until != after.timed_out_until:

        moderator = "Unbekannt"

        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
            if entry.target.id == after.id:
                moderator = entry.user.mention
                break

        if after.timed_out_until:
            duration = f"<t:{int(after.timed_out_until.timestamp())}:f>"

            await send_log(
                after.guild,
                "User Timeout",
                (
                    f"**User:** {after.mention}\n"
                    f"**Von:** {moderator}\n"
                    f"**Bis:** {duration}"
                ),
                discord.Color.orange()
            )
        else:
            await send_log(
                after.guild,
                "Timeout entfernt",
                (
                    f"**User:** {after.mention}\n"
                    f"**Von:** {moderator}"
                ),
                discord.Color.green()
            )

# ================== ROLLEN UPDATE ==================

@bot.event
async def on_guild_role_update(before, after):

    if before.permissions != after.permissions:
        moderator = "Unbekannt"

        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_update):
            if entry.target.id == after.id:
                moderator = entry.user.mention
                break

        await send_log(
            after.guild,
            "Rollenrechte geÃ¤ndert",
            (
                f"**Rolle:** {after.mention}\n"
                f"**Von:** {moderator}"
            ),
            discord.Color.blurple()
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
            rewards = COIN_REWARDS["weekly"]

            embed = discord.Embed(
                title="ðŸ† Wochenrangliste (letzte 7 Tage)",
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
                        f"ðŸ’¬ Nachrichten: {row['weekly_messages']}\n"
                        f"ðŸŽ™ Voice: {int(row['weekly_voice_seconds']//60)} Min\n"
                        f"{COIN_EMOJI} +{rewards[i]} Coins"
                    ),
                    inline=False
                )




            await channel.send(embed=embed, allowed_mentions=ALLOWED_MENTIONS)

            # ðŸ”Š OFFENE VOICE-ZEIT VOR RESET SPEICHERN
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


            # ðŸ” WOCHENWERTE RESETTEN
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

                # Coins nur zurÃ¼ckgeben, wenn das Gamble noch reserviert ist
                if has_active_gamble(u1):
                    release_coins(u1)

                if u2 != bot.user.id and has_active_gamble(u2):
                    release_coins(u2)

                pending_gambles.pop((u1, u2), None)


async def end_giveaway(giveaway_id: int, guild: discord.Guild):
    cur.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,))
    g = cur.fetchone()

    if not g or g["active"] == 0:
        return

    cur.execute("""
        SELECT user_id FROM giveaway_entries
        WHERE giveaway_id = ?
    """, (giveaway_id,))
    users = [r["user_id"] for r in cur.fetchall()]

    if users:
        winners = random.sample(users, min(g["winners"], len(users)))
    else:
        winners = []

    text = ""

    for uid in winners:
        if g["reward"] > 0:
            change_coins(uid, g["reward"])
        text += f"<@{uid}>\n"

    channel = guild.get_channel(g["channel_id"])

    await channel.send(
        f"ðŸ† Giveaway **{g['name']}** beendet!\n\n"
        f"Gewinner:\n{text or 'Niemand hat teilgenommen.'}"
    )

    cur.execute("UPDATE giveaways SET active = 0 WHERE id = ?", (giveaway_id,))
    conn.commit()

async def giveaway_task():
    await bot.wait_until_ready()

    while not bot.is_closed():
        now = int(time.time())

        cur.execute("""
            SELECT id FROM giveaways
            WHERE active = 1 AND ends_at <= ?
        """, (now,))

        rows = cur.fetchall()

        for r in rows:
            for guild in bot.guilds:
                await end_giveaway(r["id"], guild)

        await asyncio.sleep(60)


# ================== START ==================
from dotenv import load_dotenv
import os

load_dotenv()
bot.run(os.environ["DISCORD_TOKEN"])
