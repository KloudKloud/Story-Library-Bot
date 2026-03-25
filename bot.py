from dotenv import load_dotenv
load_dotenv()

from database import initialize_database, initialize_economy
initialize_database()
initialize_economy()

import discord
import asyncio
import os

from discord import app_commands, ui
from discord.ext import commands
from ui import TimeoutMixin
from features.stories.views.library_view import LibraryView
from features.stories.views.update_view import UpdateSelectView
from workers.update_worker import run_update
from workers.add_worker import add_worker

from core.queues import add_queue
from core.startup import StartupManager
from features.characters.views.character_quick_view import CharacterQuickView
from embeds.character_embeds import build_character_card
from database import get_all_characters_random
from features.characters.views.character_gallery_view import CharacterGalleryView
from features.stories.views.remove_story_view import RemoveStorySelectView
from datetime import datetime, timezone
from database import add_fanart
from database import get_fanart_by_discord_user
from features.characters.views.character_build_view import CharacterBuildView
from database import get_character_by_id
from embeds.character_embeds import unpack_character
from features.fanart.views.author_builder_view import AuthorBuilderView
from features.fanart.views.fanart_gallery_view import FanartGalleryView
from database import get_fanart_character_names
from database import get_story_by_id
from features.stories.views.fic_build_view import FicBuildView
from utils.tag_parser import normalize_tags

from features.characters.service import (
    create_character,
    get_user_characters,
    update_character_details,
    get_characters_by_story
)
from features.stories.views.showcase_view import ShowcaseView
from features.characters.views.characters_view import CharactersView
from ao3_parser import fetch_ao3_metadata, normalize_ao3_url
from wattpad_parser import normalize_wattpad_url, WattpadError
from features.characters.views.confirm_delete_view import(ConfirmDeleteCharacterView)
from pad_placeholder import ensure_padded_placeholder, get_placeholder_url

from database import (
    get_user_id,
    get_stories_by_user,
    get_story_by_url,
    delete_story,
    get_all_stories_sorted,
    get_story_id_by_title,
    get_characters_by_story_and_user,
    get_stories_by_discord_user,
    update_profile,
    get_character_id_by_name,
    add_user,
    get_all_characters,
    get_character_by_id,
    get_characters_by_story,
    _migrate_shiny_columns,
)

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
GUILD = discord.Object(id=GUILD_ID)
STORAGE_CHANNEL_ID = 1478560442723864737

startup = StartupManager()

intents = discord.Intents.default()
intents.message_content = True   # ⭐ REQUIRED FOR wait_for

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

def detect_platform(url):
    """Return 'ao3', 'wattpad', or None if the URL is not a supported platform."""
    url_lower = url.lower()
    if "archiveofourown.org" in url_lower:
        return "ao3"
    if "wattpad.com" in url_lower:
        return "wattpad"
    return None


async def rehost_attachment(
    attachment: discord.Attachment,
    guild: discord.Guild,
    pad: bool = False
) -> str | None:
    """
    Downloads a Discord attachment and re-uploads it to the storage channel
    so the URL never expires. Returns the permanent CDN URL, or None on failure.

    If pad=True, the image is composited onto a 1920x1080 transparent canvas
    before upload so Discord always renders the embed at full width.
    """
    import io

    allowed_types = ["image/png", "image/jpeg", "image/webp", "image/gif"]
    if attachment.content_type not in allowed_types:
        return None

    try:
        file_bytes = await attachment.read()
    except Exception:
        return None

    if pad:
        file_bytes = _pad_image_bytes(file_bytes)
        if file_bytes is None:
            return None

    storage_channel = guild.get_channel(STORAGE_CHANNEL_ID)
    if not storage_channel:
        try:
            storage_channel = await bot.fetch_channel(STORAGE_CHANNEL_ID)
        except Exception as e:
            print(f"❌ Could not fetch storage channel {STORAGE_CHANNEL_ID}: {e}")
            return None

    try:
        filename = attachment.filename if not pad else _padded_filename(attachment.filename)
        file = discord.File(io.BytesIO(file_bytes), filename=filename)
        storage_msg = await storage_channel.send(file=file)
        return storage_msg.attachments[0].url.split("?")[0]
    except Exception as e:
        print(f"❌ Failed to upload to storage channel: {e}")
        return None


def _padded_filename(original: str) -> str:
    """Force a .png extension since the padded canvas is always saved as PNG."""
    base = original.rsplit(".", 1)[0]
    return f"{base}_padded.png"


def _pad_image_bytes(file_bytes: bytes) -> bytes | None:
    """
    Widens the canvas toward 16:9, but caps padding at 25% of the image
    width per side so tall/portrait images don't get shrunk into a tiny
    strip. Images already at 16:9 or wider are returned untouched.
    Returns PNG bytes, or None on failure.
    """
    try:
        from PIL import Image
        import io as _io

        TARGET_RATIO    = 16 / 9
        MAX_PAD_FRAC    = 0.25   # each side never exceeds 25% of image width

        src = Image.open(_io.BytesIO(file_bytes)).convert("RGBA")
        ow, oh = src.size

        if ow / oh >= TARGET_RATIO:
            out = _io.BytesIO()
            src.save(out, format="PNG", optimize=True)
            return out.getvalue()

        # Ideal canvas to hit 16:9, but cap how much we actually add
        ideal_canvas_w = int(oh * TARGET_RATIO)
        max_pad_px     = int(ow * MAX_PAD_FRAC)
        actual_pad_px  = min((ideal_canvas_w - ow) // 2, max_pad_px)
        canvas_w       = ow + actual_pad_px * 2

        canvas = Image.new("RGBA", (canvas_w, oh), (0, 0, 0, 0))
        canvas.paste(src, (actual_pad_px, 0), src)

        out = _io.BytesIO()
        canvas.save(out, format="PNG", optimize=True)
        return out.getvalue()

    except ImportError:
        return file_bytes
    except Exception:
        return None


# =====================================================
# READY
# =====================================================

async def global_character_autocomplete(interaction, current):

    chars = get_all_characters()

    if not current:
        # Smart defaults: up to 3 most-recent characters from this user, then 1 random from others
        from features.characters.service import get_user_characters
        import random

        user_chars = get_user_characters(interaction.user.id)
        # Sort by id descending (most recently created first)
        user_chars_sorted = sorted(user_chars, key=lambda c: c["id"], reverse=True)

        choices = []
        for c in user_chars_sorted[:3]:
            story = c["story_title"] if "story_title" in c.keys() else "Unknown Story"
            label = f"✦ {c['name']} ✦ — {story}"
            choices.append(app_commands.Choice(name=label[:100], value=str(c["id"])))

        # Fill remaining slot with a random character from someone else
        other_chars = [c for c in chars if str(c.get("author", "")) != interaction.user.name
                       and not any(str(c["id"]) == ch.value for ch in choices)]
        if other_chars:
            pick = random.choice(other_chars)
            label = f"✦ {pick['name']} ✦ — {pick['story_title']} ({pick['author']})"
            choices.append(app_commands.Choice(name=label[:100], value=str(pick["id"])))

        # Always cap at 4 real choices, then append the hint as slot 5
        choices = choices[:4]
        choices.append(
            app_commands.Choice(
                name="✏️ Start typing to search all characters…",
                value="__hint__"
            )
        )
        return choices

    name_matches = []
    other_matches = []

    for c in chars:
        cid   = c["id"]
        name  = c["name"]
        story = c["story_title"]
        author = c["author"]
        label = f"✦ {name} ✦ — {story} ({author})"
        q = current.lower()
        if q in name.lower():
            name_matches.append(app_commands.Choice(name=label[:100], value=str(cid)))
        elif q in (story or "").lower() or q in (author or "").lower():
            other_matches.append(app_commands.Choice(name=label[:100], value=str(cid)))

    results = name_matches + other_matches
    choices = results[:4]

    if len(results) > 4:
        choices.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )

    return choices

async def charbuild_autocomplete(interaction, current):

    from features.characters.service import get_user_characters

    chars = get_user_characters(interaction.user.id)

    choices = []

    for c in chars:

        cid = c["id"]
        name = c["name"]

        story = c["story_title"] if "story_title" in c.keys() else "Unknown Story"

        label = f"✦ {name} ✦ {story}"

        if current.lower() not in label.lower():
            continue

        choices.append(
            app_commands.Choice(
                name=label[:100],
                value=str(cid)
            )
        )

    capped = choices[:4]
    if len(choices) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped

async def library_tag_autocomplete(interaction, current):

    from database import get_all_story_tags, get_top_tags

    if not current:
        # Show the 4 most-used tags as helpful suggestions
        top = get_top_tags(4)
        return [
            app_commands.Choice(name=f"🔥 {tag}", value=tag)
            for tag in top
        ]

    tags = get_all_story_tags()

    results = []

    for tag in tags:

        if current.lower() not in tag.lower():
            continue

        results.append(
            app_commands.Choice(
                name=tag[:100],
                value=tag
            )
        )

    choices = results[:4]

    if len(results) > 4:
        choices.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )

    return choices

async def fanart_name_autocomplete(
    interaction: discord.Interaction,
    current: str
):

    if not current:
        return []

    from database import get_all_fanart_titles

    fanarts = get_all_fanart_titles()
    guild = interaction.guild

    choices = []

    for f in fanarts:

        title = f["title"]
        discord_id = f["discord_id"]

        if current.lower() not in title.lower():
            continue

        uploader = "Unknown"

        if guild and discord_id:

            discord_id = int(discord_id)

            member = guild.get_member(discord_id)

            # If not cached, fetch from API
            if not member:
                try:
                    member = await guild.fetch_member(discord_id)
                except:
                    member = None

            if member:
                uploader = member.display_name   # ⭐ SERVER NICKNAME

        label = f"🎨 {title} ✦ 👤 {uploader}"

        choices.append(
            app_commands.Choice(
                name=label[:100],
                value=title
            )
        )

    capped = choices[:4]
    if len(choices) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped

async def fanart_character_autocomplete(
    interaction: discord.Interaction,
    current: str
):

    if not current:
        return []

    from database import get_all_characters

    chars = get_all_characters()

    choices = []

    for c in chars:

        name = c["name"]

        if current.lower() not in name.lower():
            continue

        label = f"{name} • {c['story_title']}"

        choices.append(
            app_commands.Choice(
                name=label[:100],
                value=name
            )
        )

    capped = choices[:4]
    if len(choices) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped

async def fanart_ship_autocomplete(
    interaction: discord.Interaction,
    current: str
):

    if not current:
        return []

    from database import get_all_ships

    ships = get_all_ships()

    choices = []

    for s in ships:

        name = s["name"]
        chars = s["characters"]

        if current.lower() not in name.lower():
            continue

        if chars:

            # show up to 3 characters
            display = chars[:3]

            char_text = " ✦ ".join(display)

            if len(chars) > 3:
                char_text += f" (+{len(chars)-3})"

            label = f"💞 {name}  ✦  {char_text}"

        else:
            label = f"💞 {name}"

        choices.append(
            app_commands.Choice(
                name=label[:100],
                value=name
            )
        )

    capped = choices[:4]
    if len(choices) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped

async def fanart_story_autocomplete(
    interaction: discord.Interaction,
    current: str
):

    if not current:
        return []

    from database import get_all_stories_sorted

    stories = get_all_stories_sorted()

    choices = []

    for s in stories:

        title = s[0]

        if current.lower() not in title.lower():
            continue

        choices.append(
            app_commands.Choice(
                name=title[:100],
                value=title
            )
        )

    capped = choices[:4]
    if len(choices) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped

async def fanart_autocomplete(interaction: discord.Interaction, current: str):

    fanarts = get_fanart_by_discord_user(str(interaction.user.id))

    choices = []

    for f in fanarts:

        title = f["title"]

        chars = get_fanart_character_names(f["id"])

        if chars:

            display = chars[:3]
            char_text = " ".join(f"🧬 {c}" for c in display)

            if len(chars) > 3:
                char_text += f" (+{len(chars) - 3})"

            label = f"✦ {title} ✦ • {char_text}"

        else:
            label = f"✦ {title} ✦"

        choices.append(
            app_commands.Choice(
                name=label[:100],
                value=str(f["id"])
            )
        )

    capped = choices[:4]
    if len(choices) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped

async def fanart_tag_autocomplete(
    interaction: discord.Interaction,
    current: str
):

    if not current:
        return []

    from database import get_all_fanart_tags

    tags = get_all_fanart_tags()

    choices = []

    for tag in tags:

        if current.lower() not in tag.lower():
            continue

        choices.append(
            app_commands.Choice(
                name=tag[:100],
                value=tag
            )
        )

    capped = choices[:4]
    if len(choices) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped

async def showcase_character_autocomplete(interaction, current):

    story_id = interaction.namespace.story

    if not story_id:
        return []

    chars = get_characters_by_story(int(story_id))

    return [
        app_commands.Choice(
            name=c[1],     # character name
            value=str(c[0])  # character id
        )
        for c in chars
        if current.lower() in c[1].lower()
    ][:4]

async def story_autocomplete(
    interaction: discord.Interaction,
    current: str
):

    discord_id = str(interaction.user.id)
    user_id = get_user_id(discord_id)

    if not user_id:
        return []

    stories = get_stories_by_user(user_id)

    results = []

    for story in stories:
        story_id = story[0]
        title = story[1]

        if current.lower() in title.lower():
            results.append(
                app_commands.Choice(
                    name=title,           # what user sees
                    value=str(story_id)   # what bot receives ⭐
                )
            )

    capped = results[:4]
    if len(results) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped


async def global_story_autocomplete(
    interaction: discord.Interaction,
    current: str
):
    import random as _random
    from database import get_all_stories_sorted, get_stories_by_discord_user

    HINT = app_commands.Choice(name="✏️ Type to find stories!", value="__hint__")

    stories_all = get_all_stories_sorted()

    # ── No input: user's own stories first, then random filler ───────
    if not current:
        user_stories = get_stories_by_discord_user(interaction.user.id)
        user_ids     = {s["id"] for s in user_stories}

        choices = []

        # Up to 4 slots: user's stories first
        for s in user_stories:
            if len(choices) >= 4:
                break
            choices.append(app_commands.Choice(
                name=s["title"][:100], value=str(s["id"])
            ))

        # Fill remaining slots with random stories from other authors
        others = [s for s in stories_all if s[9] not in user_ids]
        _random.shuffle(others)
        for s in others:
            if len(choices) >= 4:
                break
            choices.append(app_commands.Choice(
                name=s[0][:100], value=str(s[9])
            ))

        choices.append(HINT)
        return choices

    # ── Typing: filter by current input ──────────────────────────────
    matched = [
        app_commands.Choice(name=s[0][:100], value=str(s[9]))
        for s in stories_all
        if current.lower() in s[0].lower()
    ]

    choices = matched[:4]
    choices.append(HINT)
    return choices

def resolve_story_id(story_value, interaction):
    try:
        return int(story_value)
    except ValueError:
        # fallback → lookup by title
        sid = get_story_id_by_title(story_value)
        return sid


def resolve_character_id(story_id, char_value, interaction):
    try:
        return int(char_value)
    except ValueError:
        # fallback lookup by name
        chars = get_characters_by_story_and_user(
            story_id,
            interaction.user.id
        )

        for cid, name in chars:
            if name.lower() == char_value.lower():
                return cid

        return None
    
async def character_autocomplete(interaction, current):

    # story chosen in command UI
    story_value = interaction.namespace.story

    if not story_value:
        return []

    # resolve story id safely
    try:
        story_id = int(story_value)
    except ValueError:
        story_id = get_story_id_by_title(story_value)

    if not story_id:
        return []

    chars = get_characters_by_story_and_user(
        story_id,
        interaction.user.id
    )

    return [
        app_commands.Choice(
            name=name,
            value=str(cid)
        )
        for cid, name in chars
        if current.lower() in name.lower()
    ][:4]

@bot.event
async def on_ready():

    await bot.tree.sync(guild=GUILD)
    print(f"Logged in as {bot.user}")

    await startup.start_add_worker(bot, add_worker)

    await ensure_padded_placeholder(bot, 1478560442723864737)

    # Ensure the activity gem table exists
    from database import ensure_activity_table
    ensure_activity_table()


@bot.event
async def on_message(message: discord.Message):
    """Grant a small crystal reward for active chatting (anti-spam cooldown + daily cap)."""
    # Ignore bots, DMs, and messages outside our guild
    if message.author.bot:
        return
    if not message.guild or message.guild.id != GUILD.id:
        return

    from database import get_user_id, add_user, try_grant_activity_gem
    add_user(str(message.author.id), message.author.name)
    uid = get_user_id(str(message.author.id))
    if uid:
        try_grant_activity_gem(uid)

    # Allow other event handlers / commands to process
    await bot.process_commands(message)

# =====================================================
# ADD COMMAND
# =====================================================

# =====================================================
# HELP COMMAND
# =====================================================
@bot.tree.command(name="help", guild=GUILD)
async def help_command(interaction: discord.Interaction):

    add_user(str(interaction.user.id), interaction.user.name)

    class HelpView(TimeoutMixin, ui.View):

        def __init__(self, invoker_id):
            super().__init__(timeout=120)
            self.section = "home"
            self._invoker_id = invoker_id

        def build_embed(self):
            if self.section == "stories":    return self._stories()
            elif self.section == "characters": return self._characters()
            elif self.section == "fanart":   return self._fanart()
            elif self.section == "author":   return self._author()
            return self._home()

        def _home(self):
            embed = discord.Embed(
                title="✨ Welcome to the Library Pokédex! ✨",
                description=(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Your one-stop guide to every command in the Library Bot!\n"
                    "Choose a section below — *Gotta use 'em all~* 📖\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "📖 **Start here → `/library`**\n"
                    "*The heart of the bot! Browse every story, read chapters,\n"
                    "explore characters, discover fanart, and support your fellow authors!*\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "🛠 **The Builders** — Make it yours!\n"
                    "`/fic build` · `/fic chapbuild` · `/char build` · `/fanart build` · `/profile build`\n"
                    "*Each one has its own editor to fill in all the details — bios, lore, playlists, and more.*\n\n"
                    "🖼 *No character art yet? No worries! This bot is for fun, so find a picture online and paste it in `/char build`~*\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "📚 **Stories** — Add, browse, and manage fics\n"
                    "🧬 **Characters** — Create, build, and collect favorites\n"
                    "🎨 **Fanart** — Upload and browse artwork\n"
                    "🌸 **Author** — Profiles, badges, and reader journey\n\n"
                    "🃏 **Character Trading Cards** — Use `/ctc help` for the full CTC Pokédex!\n\n"
                    "*Use the buttons below to explore each section!*"
                ),
                color=discord.Color.from_rgb(255, 182, 255)
            )
            embed.set_footer(text="📖 Library Pokédex • Start with /library — it's where the magic happens~")
            return embed

        def _stories(self):
            embed = discord.Embed(
                title="📚 Story Pokédex — Fic Commands",
                description="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n*Catch every fic and build your library!*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.from_rgb(105, 185, 255)
            )
            embed.add_field(name="📖 /library", value="Browse the full global story library.\nOpen any fic, see characters, explore fanart, and more!", inline=False)
            embed.add_field(name="➕ /fic add `url` `cover`", value="Add your story to the library.\n• AO3 **or** Wattpad link accepted • Optional cover image (Wattpad cover used automatically if none provided)", inline=False)
            embed.add_field(name="🔄 /fic refresh", value="Re-download and refresh a story's metadata from AO3.\nUpdates chapter count, word count, and summary.", inline=False)
            embed.add_field(name="🗑 /fic delete", value="Remove one of your stories from the library.\nCleanly deletes all associated chapters, characters, progress, and more.", inline=False)
            embed.add_field(name="📋 /fic myfics", value="See a list of your own stories. Click a number to jump straight to that story's page!", inline=False)
            embed.add_field(name="🎬 /fic build `story`", value="Open your story's creative builder.\nAdd playlist, story notes, appreciation, roadmap, and extra links!", inline=False)
            embed.add_field(name="📄 /fic chapbuild `story`", value="Build your story's chapter pages — add summaries, links, and images per chapter.", inline=False)
            embed.add_field(name="🏷 /story search `tag`", value="Filter the library by tag — up to 3 tags at once!", inline=False)
            embed.add_field(name="🔗 /story open  •  🎭 /story cast  •  🖼 /story fanart  •  📊 /story stats", value="Quick-access commands for any story:\n**open** — jump straight to a story's page\n**cast** — browse a story's character roster\n**fanart** — see all fanart for a story\n**stats** — view activity stats", inline=False)
            embed.set_footer(text="📚 Story Pokédex • Stories are the backbone of the library~")
            return embed

        def _characters(self):
            embed = discord.Embed(
                title="🧬 Character Pokédex — Character Commands",
                description="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n*Build your roster and collect your favorites!*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.from_rgb(150, 255, 180)
            )
            embed.add_field(name="✨ /char add `story` `name`", value="Create a new character for one of your stories.\nRequires owning a story in the library first.", inline=False)
            embed.add_field(name="🛠 /char build `character`", value="Open the character builder — add bio, age, height, quote, lore, image, and more!\n\n🖼 **Don't have art? No problem!**\nYou're encouraged to find a reference image online — Pinterest, ArtStation, character creators, anime screenshots — anything that captures your character's vibe! Just paste the URL in the image field.", inline=False)
            embed.add_field(name="📋 /char mychars", value="Browse all your characters, grouped by story. Click to open any one directly!", inline=False)
            embed.add_field(name="🔍 /char search `character`", value="Search and view any character in the whole library.\nAutocomplete searches everyone — just start typing!", inline=False)
            embed.add_field(name="🗑 /char delete `character`", value="Delete one of your characters.\nAlso cleans up favorites, ship tags, and fanart links.", inline=False)
            embed.add_field(name="⭐ /char favs  •  💔 /char unfav", value="**✦ Favorite** while browsing to add up to 2 characters per story.\n**/char favs** — See your full favorites Pokédex!\n**/char unfav** — Remove a fav.", inline=False)
            embed.add_field(name="🚢 /ships create  •  ✏️ /ships edit  •  🗑 /ships delete", value="**/ships create** — Create a named ship for your characters.\n**/ships edit** — Rename an existing ship.\n**/ships delete** — Delete a ship and remove it from all fanart.", inline=False)
            embed.set_footer(text="🧬 Character Pokédex • No image? Find one online — Pinterest, ArtStation, anywhere works~")
            return embed

        def _fanart(self):
            embed = discord.Embed(
                title="🎨 Fanart Pokédex — Fanart Commands",
                description=(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "*Upload and browse artwork made for the stories in this library!*\n\n"
                    "⚠️ **Fanart should probably be art that belongs to you or was made for your story.\n**"
                    "Unlike character refs, fanart is more about exploring your world, and it's not\n"
                    "encouraged to use random pictures online that have no affiliation to your story.\n"
                    "Instead, post your commissions, gifted art, self-made, or pictures that are\n"
                    "designated for your characters or story. Don't just recycle online galleries\n" 
                    "that exist already! Make your own! :)\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                color=discord.Color.from_rgb(255, 210, 120)
            )
            embed.add_field(name="🖼 /fanart add `title` `image`", value="Upload a fanart piece with a title and image attachment.\nThe image is permanent once uploaded — choose carefully!\nUse `/fanart build` to add all the details afterwards.", inline=False)
            embed.add_field(name="🛠 /fanart build `fanart`", value="Open the editor for your fanart.\nTag characters, ships, link a story, add scene description, gen tags, and inspiration!", inline=False)
            embed.add_field(name="🔍 /fanart search", value="Search the community gallery.\nFilter by: `tag`, `character`, `ship`, `story`, or `name`.\nNo filters = random shuffle of everything!", inline=False)
            embed.add_field(name="🖼 /fanart myart", value="Browse your own fanart gallery in a shuffled view.", inline=False)
            embed.add_field(name="💖 /fanart liked", value="Browse all the fanart pieces you've liked!", inline=False)
            embed.add_field(name="🗑 /fanart delete `fanart`", value="Delete one of your fanart pieces.\nFully removes all character/ship/story tags.", inline=False)
            embed.set_footer(text="🎨 Fanart Pokédex • Your art, your story, your community~")
            return embed

        def _author(self):
            embed = discord.Embed(
                title="🌸 Author Pokédex — Profile & Reader Commands",
                description="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n*Build your profile and track your reading journey!*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                color=discord.Color.from_rgb(255, 150, 200)
            )
            embed.add_field(name="👤 /profile view `user`", value="View any user's profile — bio, stats, stories, characters.\nNo tag = your own profile. Works for readers too!", inline=False)
            embed.add_field(name="✏️ /profile build", value="Edit your author profile.\nBio, pronouns, favorite Pokémon, favorite fics, hobbies, fun facts, and more!", inline=False)
            embed.add_field(name="🏅 Story Badges", value="Earned automatically by completing 100% of a story's chapters.\nTrack your collection in `/profile view` — how many can you collect?", inline=False)
            embed.add_field(name="💫 /char favs `story`", value="View your Pokédex of favorited characters.\nSorted by story, 6 per page — filter to one story optionally!", inline=False)
            embed.set_footer(text="🌸 Author Pokédex • Every reader has a story too~")
            return embed

        def _update_buttons(self):
            for btn in self.children:
                btn.disabled = (btn.custom_id == f"help_{self.section}")

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.message:
                self.message = interaction.message
            if interaction.user.id != self._invoker_id:
                await interaction.response.send_message(
                    "❌ This help menu belongs to someone else.", ephemeral=True, delete_after=5
                )
                return False
            return True

        @ui.button(label="🏠 Home",       style=discord.ButtonStyle.success, custom_id="help_home",       row=0)
        async def btn_home(self, inter, button):
            self.section = "home";       self._update_buttons()
            await inter.response.edit_message(embed=self.build_embed(), view=self)

        @ui.button(label="📚 Stories",    style=discord.ButtonStyle.primary,   custom_id="help_stories",    row=0)
        async def btn_stories(self, inter, button):
            self.section = "stories";    self._update_buttons()
            await inter.response.edit_message(embed=self.build_embed(), view=self)

        @ui.button(label="🧬 Characters", style=discord.ButtonStyle.primary,   custom_id="help_characters", row=0)
        async def btn_characters(self, inter, button):
            self.section = "characters"; self._update_buttons()
            await inter.response.edit_message(embed=self.build_embed(), view=self)

        @ui.button(label="🎨 Fanart",     style=discord.ButtonStyle.primary,   custom_id="help_fanart",     row=1)
        async def btn_fanart(self, inter, button):
            self.section = "fanart";     self._update_buttons()
            await inter.response.edit_message(embed=self.build_embed(), view=self)

        @ui.button(label="🌸 Author",     style=discord.ButtonStyle.primary,   custom_id="help_author",     row=1)
        async def btn_author(self, inter, button):
            self.section = "author";     self._update_buttons()
            await inter.response.edit_message(embed=self.build_embed(), view=self)

    view = HelpView(interaction.user.id)
    view._update_buttons()
    await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)
# ── Command groups ────────────────────────────────
fic_group      = app_commands.Group(name="fic",    description="Story commands",         guild_ids=[GUILD_ID])
profile_group  = app_commands.Group(name="profile",  description="Profile commands",       guild_ids=[GUILD_ID])
ships_group    = app_commands.Group(name="ships",    description="Ship commands",          guild_ids=[GUILD_ID])
fanart_group   = app_commands.Group(name="fanart",   description="Fanart commands",        guild_ids=[GUILD_ID])
character_group = app_commands.Group(name="char",      description="Character commands",   guild_ids=[GUILD_ID])
ctc_group      = app_commands.Group(name="ctc",       description="Character Trading Cards",  guild_ids=[GUILD_ID])
gem_group      = app_commands.Group(name="gem",       description="Gems & economy",            guild_ids=[GUILD_ID])
story_group    = app_commands.Group(name="story",     description="Quick story access",        guild_ids=[GUILD_ID])
set_group      = app_commands.Group(name="set",       description="Bot settings",              guild_ids=[GUILD_ID])


# =====================================================
# /set announcements
# =====================================================

@set_group.command(name="announcements", description="Set a channel where the bot announces your story updates")
@app_commands.describe(channel="The channel or thread where announcements should go")
async def set_announcements(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.Thread = None
):
    from database import (
        get_user_id, set_announcement_channel,
        remove_announcement_channel, get_announcement_channel
    )

    add_user(str(interaction.user.id), interaction.user.name)
    uid = get_user_id(str(interaction.user.id))

    # No channel = show current setting or clear
    if channel is None:
        current = get_announcement_channel(uid)
        if current:
            remove_announcement_channel(uid)
            await interaction.response.send_message(
                "🔕 Your announcement channel has been **removed**. "
                "Your story updates will no longer be announced.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "You don't have an announcement channel set.\n"
                "Use `/set announcements #channel` to pick one!",
                ephemeral=True
            )
        return

    # Verify the bot can send messages in that channel
    perms = channel.permissions_for(interaction.guild.me)
    if not perms.send_messages:
        await interaction.response.send_message(
            f"❌ I can't send messages in {channel.mention}. "
            "Please make sure I have permission to talk there, then try again.",
            ephemeral=True
        )
        return

    set_announcement_channel(uid, str(channel.id))
    await interaction.response.send_message(
        f"✅ Story update announcements will now be posted in {channel.mention}!",
        ephemeral=True
    )

bot.tree.add_command(set_group)


@fic_group.command(name="add", description="Add your AO3 or Wattpad story to the library")
@app_commands.describe(url="AO3 or Wattpad link", cover="Optional cover image (overrides Wattpad's auto cover)")
async def add(
    interaction: discord.Interaction,
    url: str,
    cover: discord.Attachment = None
):
    from database import get_story_by_url

    platform = detect_platform(url)

    if platform is None:
        await interaction.response.send_message(
            "❌ That doesn't look like a supported link.\n"
            "Please use an **AO3** link (`archiveofourown.org`) or a **Wattpad** link (`wattpad.com`).",
            ephemeral=True
        )
        return

    # ── Pre-check: reject duplicate URLs before even queuing ──
    if platform == "ao3":
        normalized = normalize_ao3_url(url)
    else:
        normalized = normalize_wattpad_url(url)

    existing = get_story_by_url(normalized, platform)

    if existing:
        await interaction.response.send_message(
            "❌ That story is already in the library! You can't add the same story twice~\n"
            "View it with `/library browse` 📚",
            ephemeral=True
        )
        return

    await interaction.response.defer()

    if cover:
        cover_url = await rehost_attachment(cover, interaction.guild)
        if not cover_url:
            cover_url = cover.url.split("?")[0]
    elif platform == "ao3":
        # AO3 has no cover — use placeholder until author uploads one
        cover_url = get_placeholder_url()
    else:
        # Wattpad has its own cover — pass None so the worker fetches it from the API
        cover_url = None

    pos = add_queue.qsize() + 1

    await add_queue.put(
        (interaction, url, platform, cover_url)
    )

    await interaction.followup.send(
        f"📚 Added to queue! Position: **{pos}**"
    )

# =====================================================
# /character — command group
# =====================================================


# ── /character search ─────────────────────────────

@character_group.command(name="search", description="Browse all characters, or jump straight to one")
@app_commands.describe(character="Optional: jump straight to a specific character")
@app_commands.autocomplete(character=global_character_autocomplete)
async def character_search(
    interaction: discord.Interaction,
    character: str = None
):
    from database import get_all_characters
    from features.characters.views.char_search_view import CharSearchRosterView, CharSearchDetailView, PAGE_SIZE

    add_user(str(interaction.user.id), interaction.user.name)

    # ── No character specified: open roster ───────────────────────
    if not character or character == "__hint__":
        all_chars = get_all_characters()
        if not all_chars:
            await interaction.response.send_message(
                "No characters in the library yet.", ephemeral=True, delete_after=4
            )
            return
        # Pass minimal dicts directly — roster only needs name/story_title/author/id
        view = CharSearchRosterView(all_chars, interaction.user)
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        return

    # ── Character specified: open detail directly ─────────────────
    try:
        character_id = int(character)
    except ValueError:
        await interaction.response.send_message(
            "Please select a character from autocomplete.", ephemeral=True
        )
        return

    selected = get_character_by_id(character_id)
    if not selected:
        await interaction.response.send_message(
            "Character not found.", ephemeral=True
        )
        return

    # Build the full roster so Return + arrows behave like the default path
    all_chars = get_all_characters()
    roster = CharSearchRosterView(all_chars, interaction.user)

    selected_index = next(
        (i for i, c in enumerate(roster._sorted) if c["id"] == character_id), 0
    )
    return_page = selected_index // PAGE_SIZE
    roster.page = return_page

    view = CharSearchDetailView(
        chars=roster._sorted,
        index=selected_index,
        viewer=interaction.user,
        roster=roster,
        return_page=return_page
    )
    await interaction.response.send_message(embed=view.build_embed(), view=view)

# ── /character view ───────────────────────────────

async def _my_chars_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete scoped to the caller's own characters only."""
    from features.characters.service import get_user_characters

    chars = get_user_characters(interaction.user.id)

    if not current:
        sorted_chars = sorted(chars, key=lambda c: c["id"], reverse=True)
        choices = []
        for c in sorted_chars[:4]:
            story = c["story_title"] if "story_title" in c.keys() else "Unknown Story"
            label = f"✦ {c['name']} ✦ — {story}"
            choices.append(app_commands.Choice(name=label[:100], value=str(c["id"])))
        choices.append(
            app_commands.Choice(
                name="✏️ Start typing to search your characters…",
                value="__hint__"
            )
        )
        return choices

    results = []
    for c in chars:
        story = c["story_title"] if "story_title" in c.keys() else "Unknown Story"
        label = f"✦ {c['name']} ✦ — {story}"
        if current.lower() in label.lower():
            results.append(app_commands.Choice(name=label[:100], value=str(c["id"])))

    capped = results[:4]
    if len(results) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped


@character_group.command(name="mychars", description="Browse all your characters, or open one directly")
@app_commands.describe(character="Optional: jump straight to a character's card")
@app_commands.autocomplete(character=_my_chars_autocomplete)
async def char_mychars(
    interaction: discord.Interaction,
    character: str = None
):
    from features.characters.service import get_user_characters
    from features.characters.views.my_chars_roster_view import MyCharsRosterView, MyCharDetailView, build_roster_embed

    add_user(str(interaction.user.id), interaction.user.name)

    chars = [dict(c) for c in get_user_characters(interaction.user.id)]

    if not chars:
        await interaction.response.send_message(
            "You don't have any characters yet! Use `/char add` to create one~",
            ephemeral=True
        )
        return

    # Sort alphabetically
    chars = sorted(chars, key=lambda c: c["name"].lower())

    # ── Optional: jump straight to a specific character ──
    if character and character != "__hint__":
        try:
            char_id = int(character)
        except ValueError:
            await interaction.response.send_message(
                "Please select a character from autocomplete.", ephemeral=True
            )
            return

        char_index = next((i for i, c in enumerate(chars) if c["id"] == char_id), None)
        if char_index is None:
            await interaction.response.send_message(
                "That character wasn't found in your roster.", ephemeral=True
            )
            return

        detail_view = MyCharDetailView(chars, char_index, interaction.user, return_page=0)
        await interaction.response.send_message(
            embed=detail_view.build_embed(),
            view=detail_view
        )
        return

    # ── Default: open roster page 1 ──────────────────────
    total_pages = max(1, (len(chars) + 7 - 1) // 7)
    view = MyCharsRosterView(chars, interaction.user, start_page=0)
    await interaction.response.send_message(
        embed=build_roster_embed(chars, 0, total_pages, interaction.user.display_name,
                                 viewer_discord_id=str(interaction.user.id)),
        view=view
    )


@story_group.command(name="search", description="Search the story library by tags")
@app_commands.autocomplete(
    tag=library_tag_autocomplete,
    tag2=library_tag_autocomplete,
    tag3=library_tag_autocomplete
)
async def libraryview(
    interaction: discord.Interaction,
    tag: str = None,
    tag2: str = None,
    tag3: str = None
):

    from database import get_stories_by_tags, get_all_stories_sorted
    from features.stories.views.library_view import LibraryView

    add_user(str(interaction.user.id), interaction.user.name)

    tags = [t for t in [tag, tag2, tag3] if t and t != "__hint__"]

    if not tags:
        # No tags provided — behave exactly like /library
        stories = get_all_stories_sorted("alphabetical")
        if not stories:
            await interaction.response.send_message("Library empty.", ephemeral=True)
            return
        view = LibraryView(stories, "📚 Global Library", interaction.user)
    else:
        stories = get_stories_by_tags(tags)
        if not stories:
            await interaction.response.send_message(
                f"No stories found with tags: **{', '.join(tags)}**",
                ephemeral=True,
                delete_after=5
            )
            return
        view = LibraryView(
            stories,
            f"📚 Stories tagged: {', '.join(tags)}",
            interaction.user,
            filtered_stories=stories,
            tag_stories=stories,
            tag_title=f"📚 Stories tagged: {', '.join(tags)}"
        )

    await interaction.response.send_message(
        embed=view.generate_list_embed(),
        view=view
    )

    view.message = await interaction.original_response()

@fic_group.command(name="myfics", description="Browse your stories, or jump to one directly")
@app_commands.describe(story="Optional: jump straight to a specific story")
@app_commands.autocomplete(story=story_autocomplete)
async def fic_myfics(
    interaction: discord.Interaction,
    story: str = None
):
    from features.stories.views.my_fics_view import MyFicsView, MyFicDetailView, build_my_fics_embed

    add_user(str(interaction.user.id), interaction.user.name)

    user_id = get_user_id(str(interaction.user.id))
    if not user_id:
        await interaction.response.send_message(
            "You don't have any stories yet! Use `/fic add` to add one~",
            ephemeral=True
        )
        return

    stories = get_stories_by_user(user_id)

    if not stories:
        await interaction.response.send_message(
            "You don't have any stories yet! Use `/fic add` to add one~",
            ephemeral=True
        )
        return

    # Optional: jump straight to a specific story
    if story and story != "__hint__":
        try:
            story_id = int(story)
        except ValueError:
            story_id = get_story_id_by_title(story)

        if story_id:
            # Find which page this story sits on in the user's list
            story_ids = [s[0] for s in stories]
            if story_id in story_ids:
                idx         = story_ids.index(story_id)
                return_page = idx // 5  # PAGE_SIZE = 5
            else:
                return_page = 0

            story_data = get_story_by_id(story_id)
            if story_data:
                roster = MyFicsView(stories, interaction.user, start_page=return_page)
                detail_view = MyFicDetailView(
                    story_data=dict(story_data),
                    viewer=interaction.user,
                    roster=roster,
                    return_page=return_page
                )
                await interaction.response.send_message(
                    embed=detail_view.build_embed(),
                    view=detail_view
                )
                return

        await interaction.response.send_message(
            "❌ Story not found.", ephemeral=True
        )
        return

    # Default: open roster page 1
    total_pages = max(1, (len(stories) + 4) // 5)
    view = MyFicsView(stories, interaction.user, start_page=0)
    await interaction.response.send_message(
        embed=build_my_fics_embed(
            stories, 0, total_pages,
            interaction.user.display_name,
            viewer_discord_id=str(interaction.user.id)
        ),
        view=view
    )


@fic_group.command(name="build", description="Open your story's creative builder")
@app_commands.autocomplete(story=story_autocomplete)
async def ficbuild(
    interaction: discord.Interaction,
    story: str
):
    
        await interaction.response.defer(ephemeral=True)

        # --------------------------------
        # Resolve story ID
        # --------------------------------

        try:
            story_id = int(story)
        except ValueError:

            story_id = get_story_id_by_title(story)

        if not story_id:
            await interaction.followup.send(
                "❌ Story not found.",
                ephemeral=True
            )
            return


        # --------------------------------
        # Ownership Check
        # --------------------------------

        user_id = get_user_id(str(interaction.user.id))

        stories = get_stories_by_user(user_id)

        valid_ids = {s[0] for s in stories}

        if story_id not in valid_ids:

            await interaction.followup.send(
                "❌ You do not own that story.",
                ephemeral=True
            )
            return


        # --------------------------------
        # Load Story
        # --------------------------------

        story_data = get_story_by_id(story_id)

        if not story_data:

            await interaction.followup.send(
                "❌ Story could not be loaded.",
                ephemeral=True
            )
            return


        # --------------------------------
        # Open Builder
        # --------------------------------

        view = FicBuildView(
            story_data,
            interaction.user
        )

        msg = await interaction.followup.send(
            embed=view.build_embed(),
            view=view,
            ephemeral=True
        )

        await view.attach_message(msg)

# =====================================================
# /fic chapbuild
# =====================================================

@fic_group.command(name="chapbuild", description="Build chapter pages — add summaries, links, and images")
@app_commands.describe(story="Your story")
@app_commands.autocomplete(story=story_autocomplete)
async def fic_chapters(interaction: discord.Interaction, story: str):
    from features.chapters.chapter_builder_view import ChapterBuilderView
    from database import get_chapters_full

    await interaction.response.defer(ephemeral=True)

    try:
        story_id = int(story)
    except ValueError:
        story_id = get_story_id_by_title(story)

    if not story_id:
        await interaction.followup.send("❌ Story not found.", ephemeral=True)
        return

    user_id = get_user_id(str(interaction.user.id))
    stories = get_stories_by_user(user_id)
    if story_id not in {s[0] for s in stories}:
        await interaction.followup.send("❌ You don't own that story.", ephemeral=True)
        return

    story_data = get_story_by_id(story_id)
    if not story_data:
        await interaction.followup.send("❌ Story not found.", ephemeral=True)
        return

    chapters = get_chapters_full(story_id)
    if not chapters:
        await interaction.followup.send(
            "No chapters found for this story. Use `/fic refresh` to sync chapters first.",
            ephemeral=True
        )
        return

    # sqlite3.Row supports named access regardless of dict vs Row
    story_title = story_data["title"]
    try:
        cover_url = story_data["cover_url"]
    except (IndexError, KeyError):
        cover_url = None

    view = ChapterBuilderView(story_id, story_title, interaction.user, cover_url=cover_url)
    msg  = await interaction.followup.send(
        embed=view.build_embed(), view=view, ephemeral=True
    )
    view.builder_message = msg


# =====================================================
# /updatefic
# =====================================================

@fic_group.command(name="refresh", description="Re-download a story's metadata from AO3")
@app_commands.describe(story="Select one of your stories to update")
@app_commands.autocomplete(story=story_autocomplete)
async def updatefic(
    interaction: discord.Interaction,
    story: str
):
    """Re-download a story's HTML from AO3 and update chapter count, words, and summary."""

    add_user(str(interaction.user.id), interaction.user.name)

    # Resolve story ID from autocomplete value
    try:
        story_id = int(story)
    except ValueError:
        await interaction.response.send_message(
            "❌ Please select a story from the autocomplete list.",
            ephemeral=True,
            delete_after=6
        )
        return

    # Ownership check — only the story's author can update it
    story_row = get_story_by_id(story_id)

    if not story_row:
        await interaction.response.send_message(
            "❌ Story not found.",
            ephemeral=True,
            delete_after=6
        )
        return

    requester_id = get_user_id(str(interaction.user.id))
    if story_row["user_id"] != requester_id:
        await interaction.response.send_message(
            "❌ You can only update your own stories.",
            ephemeral=True,
            delete_after=6
        )
        return

    await run_update(interaction, story_id)


# =====================================================
# REMOVE
# =====================================================
@fic_group.command(name="delete", description="Remove one of your stories from the library")
async def remove(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True)

    requester_id = get_user_id(str(interaction.user.id))

    if not requester_id:
        await interaction.followup.send(
            "❌ You don't have any stories."
        )
        return

    stories = get_stories_by_user(requester_id)

    if not stories:
        await interaction.followup.send(
            "❌ You don't have any stories to remove."
        )
        return

    view = RemoveStorySelectView(stories)

    await interaction.followup.send(
        "Select a story to remove:",
        view=view,
        ephemeral=True
    )


# =====================================================
# /fic private — create a DNE private character collection
# =====================================================
@fic_group.command(name="private", description="Create a private character collection (for characters not on AO3)")
async def fic_private(interaction: discord.Interaction):
    from database import get_user_id, add_user, get_dummy_story, add_dummy_story

    add_user(str(interaction.user.id), interaction.user.name)
    uid = get_user_id(str(interaction.user.id))

    # Already has one — show info instead
    existing = get_dummy_story(uid)
    if existing:
        await interaction.response.send_message(
            embed=discord.Embed(
                title="📦  Private Collection Already Exists",
                description=(
                    f"You already have a private collection: **{existing['title']}**\n\n"
                    f"Add characters to it via `/char build`, and move them to a real story "
                    f"anytime with `/char swap`."
                ),
                color=discord.Color.from_rgb(100, 181, 246),
            ),
            ephemeral=True
        )
        return

    # Confirmation embed + buttons
    class _ConfirmView(ui.View):
        def __init__(self):
            super().__init__(timeout=60)

        async def on_timeout(self):
            try:
                await interaction.edit_original_response(
                    embed=discord.Embed(description="-# This session expired.", color=discord.Color.greyple()),
                    view=None
                )
            except Exception:
                pass

        @ui.button(label="Create Private Collection", style=discord.ButtonStyle.success)
        async def confirm(self, intr: discord.Interaction, button: ui.Button):
            add_dummy_story(uid, intr.user.display_name)
            self.stop()
            await intr.response.edit_message(
                embed=discord.Embed(
                    title="📦  Private Collection Created!",
                    description=(
                        f"Your private collection is ready.\n\n"
                        f"Use `/char build` to add characters — your private collection will appear "
                        f"in the story dropdown.\n\n"
                        f"When you're ready to move a character to a real story, use `/char swap`."
                    ),
                    color=discord.Color.green(),
                ),
                view=None
            )
            await asyncio.sleep(15)
            try:
                await intr.delete_original_response()
            except Exception:
                pass

        @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, intr: discord.Interaction, button: ui.Button):
            self.stop()
            await intr.response.edit_message(
                embed=discord.Embed(description="-# Cancelled.", color=discord.Color.greyple()),
                view=None
            )
            await asyncio.sleep(15)
            try:
                await intr.delete_original_response()
            except Exception:
                pass

    embed = discord.Embed(
        title="📦  Private Character Collection",
        description=(
            "This is a storage place that enables you to add characters, build character "
            "trading cards, and link fanart.\n\n"
            "**This is not a story that will display in `/library` or be searchable**, "
            "and it is simply for storing characters that don't belong to a story for whatever reason. "
            "Everyone is free to create characters! :3\n\n"
            "At any point, you can move a character from this storage place to a book you "
            "have registered through `/fic add` with the `/char swap` command.\n\n"
            "*Would you like to proceed with creation of your private collection?*"
        ),
        color=discord.Color.from_rgb(100, 181, 246),
    )
    await interaction.response.send_message(embed=embed, view=_ConfirmView(), ephemeral=True)


# =====================================================
# LIBRARY COMMAND
# =====================================================
@bot.tree.command(name="library", description="Open the global story library", guild=GUILD)
async def library(interaction: discord.Interaction):

    add_user(
        str(interaction.user.id),
        interaction.user.name
    )

    stories = get_all_stories_sorted("alphabetical")

    if not stories:
        await interaction.response.send_message("Library empty.")
        return

    view = LibraryView(stories, "📚 Global Library", interaction.user)

    await interaction.response.send_message(
        embed=view.generate_list_embed(),
        view=view
    )

    view.message = await interaction.original_response()

# =====================================================
# CHARACTER COMMAND
# =====================================================

@character_group.command(name="add", description="Create a new character for one of your stories")
@app_commands.describe(story="Your story", name="Character name")
@app_commands.autocomplete(story=story_autocomplete)
async def character_add(
    interaction: discord.Interaction,
    story: str,
    name: str
):
    try:
        from database import get_user_id, grant_character_credit
        character_id = create_character(
            interaction.user.id,
            interaction.user.name,
            int(story),
            name
        )

        credit_msg = ""
        if character_id:
            uid = get_user_id(str(interaction.user.id))
            granted, new_balance = grant_character_credit(uid, character_id)
            if granted:
                credit_msg = f"\n-# 💎 +50 crystals earned  ·  {new_balance:,} total"

        await interaction.response.send_message(
            f"✨ Character **{name}** created!{credit_msg}",
            ephemeral=True,
            delete_after=6
        )

    except ValueError as e:

        await interaction.response.send_message(
            f"❌ {str(e)}",
            ephemeral=True
        )


@character_group.command(name="build", description="Open the character builder for one of your characters")
@app_commands.describe(character="Choose a character to build")
@app_commands.autocomplete(character=charbuild_autocomplete)
async def character_build(
    interaction: discord.Interaction,
    character: str
):
    await interaction.response.defer(ephemeral=True)

    try:
        character_id = int(character)
    except ValueError:
        await interaction.followup.send(
            "❌ Please select a character from autocomplete.",
            ephemeral=True
        )
        return

    character_data = get_character_by_id(character_id)

    if not character_data:
        await interaction.followup.send(
            "❌ Character not found.",
            ephemeral=True
        )
        return

    if str(character_data["user_id"]) != str(get_user_id(str(interaction.user.id))):
        await interaction.followup.send(
            "❌ You do not own that character.",
            ephemeral=True
        )
        return

    view = CharacterBuildView(
        character_data,
        interaction.user
    )

    builder_message = await interaction.followup.send(
        embed=view.build_embed(),
        view=view,
        ephemeral=True
    )

    view.builder_message = builder_message


async def delchar_autocomplete(interaction, current):
    from features.characters.service import get_user_characters

    chars = get_user_characters(interaction.user.id)
    # Most recently created first
    chars_sorted = sorted(chars, key=lambda c: c["id"], reverse=True)

    if not current:
        choices = []
        for c in chars_sorted[:4]:
            story = c["story_title"] if "story_title" in c.keys() else "Unknown Story"
            label = f"🔴 {c['name']} ✦ {story}"
            choices.append(app_commands.Choice(name=label[:100], value=str(c["id"])))
        choices.append(
            app_commands.Choice(
                name="✏️ Start typing to search your characters…",
                value="__hint__"
            )
        )
        return choices

    results = []
    for c in chars_sorted:
        story = c["story_title"] if "story_title" in c.keys() else "Unknown Story"
        label = f"🔴 {c['name']} ✦ {story}"
        if current.lower() in label.lower():
            results.append(app_commands.Choice(name=label[:100], value=str(c["id"])))

    capped = results[:4]
    if len(results) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped


async def swapchar_char_autocomplete(interaction, current):
    """Autocomplete: user's own characters (for /char swap source)."""
    from features.characters.service import get_user_characters
    chars = get_user_characters(interaction.user.id)
    chars_sorted = sorted(chars, key=lambda c: c["id"], reverse=True)
    hint = app_commands.Choice(name="✏️ Keep typing to narrow down results…", value="__hint__")
    if not current:
        choices = [
            app_commands.Choice(
                name=f"🔀 {c['name']} ✦ {c.get('story_title', '?')}"[:100],
                value=str(c["id"])
            )
            for c in chars_sorted[:4]
        ]
        choices.append(app_commands.Choice(name="✏️ Start typing to search your characters…", value="__hint__"))
        return choices
    results = [
        app_commands.Choice(
            name=f"🔀 {c['name']} ✦ {c.get('story_title', '?')}"[:100],
            value=str(c["id"])
        )
        for c in chars_sorted if current.lower() in c["name"].lower()
    ]
    return (results[:4] + [hint]) if len(results) > 4 else results


async def swapchar_story_autocomplete(interaction, current):
    """Autocomplete: caller's stories (including DNE private collection) as swap target."""
    uid = get_user_id(str(interaction.user.id))
    if not uid:
        return []
    stories = get_stories_by_user(uid)
    choices = []
    for s in stories:
        title    = s["title"]
        is_dummy = s["is_dummy"]
        label    = f"🔒 [Private] {title}" if is_dummy else title
        if current.lower() in title.lower():
            choices.append(app_commands.Choice(name=label[:100], value=str(s["id"])))
    return choices[:25]


@character_group.command(name="swap", description="Move one of your characters to a different story")
@app_commands.describe(
    character="The character to move",
    story="The story (or private collection) to move them into"
)
@app_commands.autocomplete(character=swapchar_char_autocomplete, story=swapchar_story_autocomplete)
async def character_swap(interaction: discord.Interaction, character: str, story: str):
    from database import get_user_id, get_character_by_id, get_story_by_id, swap_character_story
    from features.characters.service import get_user_characters

    if character == "__hint__":
        await interaction.response.send_message("✏️ Keep typing to find your character!", ephemeral=True)
        return

    try:
        char_id  = int(character)
        story_id = int(story)
    except ValueError:
        await interaction.response.send_message("❌ Please select from the autocomplete options.", ephemeral=True)
        return

    uid = get_user_id(str(interaction.user.id))

    # Verify ownership of character
    user_chars = get_user_characters(interaction.user.id)
    char_data  = next((c for c in user_chars if c["id"] == char_id), None)
    if not char_data:
        await interaction.response.send_message("❌ That character doesn't belong to you.", ephemeral=True, delete_after=8)
        return

    # Verify target story belongs to user
    all_user_stories = {s["id"]: s["title"] for s in get_stories_by_user(uid)}
    if story_id not in all_user_stories:
        await interaction.response.send_message("❌ That story doesn't belong to you.", ephemeral=True, delete_after=8)
        return

    if char_data.get("story_id") == story_id:
        await interaction.response.send_message("❌ That character is already in that story.", ephemeral=True, delete_after=8)
        return

    old_story_name = char_data.get("story_title") or "their old story"
    new_story_name = all_user_stories[story_id]

    swap_character_story(char_id, story_id)

    # Invalidate character cache
    from database import _all_characters_cache
    _all_characters_cache.invalidate()

    embed = discord.Embed(
        title="🔀  Character Moved",
        description=(
            f"**{char_data['name']}** has been moved from "
            f"*{old_story_name}* → **{new_story_name}**.\n\n"
            f"-# All CTC cards, fanart, and favorites carry over automatically."
        ),
        color=discord.Color.green(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@character_group.command(name="delete", description="Delete one of your characters")
@app_commands.describe(character="Choose one of your characters to delete")
@app_commands.autocomplete(character=delchar_autocomplete)
async def character_delete(
    interaction: discord.Interaction,
    character: str
):
    if character == "__hint__":
        await interaction.response.send_message(
            "✏️ That's just a hint — keep typing to find your character!",
            ephemeral=True
        )
        return

    try:
        character_id = int(character)
    except ValueError:
        await interaction.response.send_message(
            "Please select a character from autocomplete.",
            ephemeral=True
        )
        return

    # Verify it belongs to this user
    from features.characters.service import get_user_characters
    user_chars = get_user_characters(interaction.user.id)
    selected = next((c for c in user_chars if c["id"] == character_id), None)

    if not selected:
        await interaction.response.send_message(
            "Character not found, or you don't own that character.",
            ephemeral=True
        )
        return

    character_name = selected["name"]
    story_name = selected["story_title"] if "story_title" in selected.keys() else "Unknown Story"

    view = ConfirmDeleteCharacterView(
        character_id,
        character_name,
        story_name
    )

    await interaction.response.send_message(
        (
            f"⚠️ Are you sure you want to remove "
            f"**{character_name}** from **{story_name}**?"
        ),
        view=view,
        ephemeral=True
    )

@profile_group.command(name="view", description="View any user's profile")
async def showcase(
    interaction: discord.Interaction,
    user: discord.Member = None
):
    # Always register the caller so they exist in the DB
    add_user(str(interaction.user.id), interaction.user.name)

    if user is None:
        user = interaction.user

    # Also register the target user if different
    add_user(str(user.id), user.name)

    stories = get_stories_by_discord_user(user.id)

    # Readers may have no stories — still show their profile
    view = ShowcaseView(
        stories,          # may be empty list
        interaction.user,
        user
    )

    await interaction.response.send_message(
        embed=view.generate_bio_embed(),
        view=view
    )

@profile_group.command(name="build", description="Edit your author profile")
async def authorbuild(interaction: discord.Interaction):

    add_user(str(interaction.user.id), interaction.user.name)

    view = AuthorBuilderView(interaction.user)

    msg = await interaction.response.send_message(
        embed=view.build_embed(),
        view=view,
        ephemeral=True
    )

    view.builder_message = await interaction.original_response()

@ships_group.command(name="create", description="Create a new ship for your characters")
@app_commands.autocomplete(story=story_autocomplete)
async def createship(
    interaction: discord.Interaction,
    story: str,
    shipname: str
):
    from database import get_character_id_by_name, create_ship, get_user_id

    story_id = int(story)

    class ShipCharactersModal(discord.ui.Modal, title=f"Add Characters to {shipname[:40]}"):

        characters = discord.ui.TextInput(
            label="Character names (comma separated)",
            style=discord.TextStyle.paragraph,
            placeholder="e.g. Aria, Marcus, Lune",
            required=True,
            max_length=500
        )

        async def on_submit(self_, interaction: discord.Interaction):
            names = [n.strip() for n in self_.characters.value.split(",") if n.strip()]

            if len(names) < 2:
                await interaction.response.send_message(
                    "❌ A ship needs at least **two** characters! Separate names with a comma.",
                    ephemeral=True,
                    delete_after=5
                )
                return

            char_ids = []
            invalid  = []
            for name in names:
                cid = get_character_id_by_name(story_id, name)
                if cid:
                    char_ids.append(cid)
                else:
                    invalid.append(name)

            if invalid:
                bad = ", ".join(f"**{n}**" for n in invalid)
                await interaction.response.send_message(
                    f"❌ Couldn't find: {bad}"
                    f"-# Names are case-sensitive. Check your characters with `/char mychars`, "
                    f"or add missing ones with `/char add`.",
                    ephemeral=True,
                    delete_after=5
                )
                return

            user_id = get_user_id(str(interaction.user.id))
            result  = create_ship(user_id, shipname, char_ids)

            if result is None:
                await interaction.response.send_message(
                    "❌ A ship with this exact pairing already exists! Use `/ships edit` to manage existing ships.",
                    ephemeral=True,
                    delete_after=6
                )
            else:
                await interaction.response.send_message(
                    f"💞 Ship **{shipname}** created with {len(char_ids)} characters!",
                    ephemeral=True,
                    delete_after=4
                )

    await interaction.response.send_modal(ShipCharactersModal())

# =====================================================
# EDIT SHIPS COMMAND
# =====================================================

async def user_ship_autocomplete(interaction: discord.Interaction, current: str):
    from database import get_user_id, get_ships_by_user

    uid = get_user_id(str(interaction.user.id))
    if not uid:
        return []

    ships = get_ships_by_user(uid)
    choices = []

    for s in ships:
        char_preview = " / ".join(s["characters"][:3])
        if len(s["characters"]) > 3:
            char_preview += f" (+{len(s['characters'])-3})"
        label = f"💞 {s['name']}  ✦  {char_preview}"
        if current.lower() in label.lower():
            choices.append(
                app_commands.Choice(name=label[:100], value=str(s["id"]))
            )

    return choices[:10]


@ships_group.command(name="edit", description="Rename one of your ships")
@app_commands.describe(ship="Type to find your ship (shows characters in the preview)")
@app_commands.autocomplete(ship=user_ship_autocomplete)
async def editships(interaction: discord.Interaction, ship: str):
    from database import get_ship_by_id, get_user_id, rename_ship, delete_ship

    add_user(str(interaction.user.id), interaction.user.name)

    try:
        ship_id = int(ship)
    except ValueError:
        await interaction.response.send_message(
            "❌ Please select a ship from autocomplete.",
            ephemeral=True,
            delete_after=6
        )
        return

    uid = get_user_id(str(interaction.user.id))
    ship_data = get_ship_by_id(ship_id)

    if not ship_data:
        await interaction.response.send_message("❌ Ship not found.", ephemeral=True)
        return

    if ship_data["user_id"] != uid:
        await interaction.response.send_message("❌ You don't own that ship.", ephemeral=True)
        return

    char_list = ", ".join(c["name"] for c in ship_data["characters"])
    ship_name = ship_data["name"]

    class EditShipView(ui.View):
        def __init__(self):
            super().__init__(timeout=60)

        @ui.button(label="✏️ Change Name", style=discord.ButtonStyle.primary)
        async def change_name(self, inter, button):
            class RenameModal(discord.ui.Modal, title="Rename Ship"):
                new_name = discord.ui.TextInput(
                    label="New Ship Name",
                    placeholder=ship_name,
                    max_length=64,
                    default=ship_name
                )

                async def on_submit(self, modal_inter):
                    rename_ship(ship_id, self.new_name.value)
                    await modal_inter.response.edit_message(
                        content=f"✅ Ship renamed to **{self.new_name.value}**!",
                        view=None
                    )

            await inter.response.send_modal(RenameModal())

        @ui.button(label="🗑️ Delete Ship", style=discord.ButtonStyle.danger)
        async def delete_this_ship(self, inter, button):
            class ConfirmDeleteShipView(ui.View):
                def __init__(self):
                    super().__init__(timeout=15)

                @ui.button(label="Yes, Delete", style=discord.ButtonStyle.danger)
                async def confirm(self, conf_inter, btn):
                    delete_ship(ship_id)
                    await conf_inter.response.edit_message(
                        content=f"🗑️ Ship **{ship_name}** deleted.",
                        view=None
                    )

                @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
                async def cancel(self, conf_inter, btn):
                    await conf_inter.response.edit_message(
                        content="↩️ Cancelled — ship kept.",
                        view=None
                    )

            await inter.response.edit_message(
                content=f"⚠️ Really delete **{ship_name}**? This can't be undone!",
                view=ConfirmDeleteShipView()
            )

        @ui.button(label="↩️ Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, inter, button):
            await inter.response.edit_message(
                content="↩️ No changes made.",
                view=None
            )

    embed = discord.Embed(
        title=f"💞 Edit Ship: {ship_name}",
        description=f"**Characters:** {char_list}",
        color=discord.Color.from_rgb(255, 150, 200)
    )
    embed.set_footer(text="Choose an action below~")

    await interaction.response.send_message(
        embed=embed,
        view=EditShipView(),
        ephemeral=True
    )


# =====================================================
# /ships delete
# =====================================================

@ships_group.command(name="delete", description="Delete one of your ships")
@app_commands.describe(ship="Type to find your ship")
@app_commands.autocomplete(ship=user_ship_autocomplete)
async def ships_delete(interaction: discord.Interaction, ship: str):
    from database import get_ship_by_id, get_user_id, delete_ship

    add_user(str(interaction.user.id), interaction.user.name)

    try:
        ship_id = int(ship)
    except ValueError:
        await interaction.response.send_message(
            "❌ Please select a ship from autocomplete.",
            ephemeral=True,
            delete_after=6
        )
        return

    uid = get_user_id(str(interaction.user.id))
    ship_data = get_ship_by_id(ship_id)

    if not ship_data:
        await interaction.response.send_message("❌ Ship not found.", ephemeral=True)
        return

    if ship_data["user_id"] != uid:
        await interaction.response.send_message("❌ You don't own that ship.", ephemeral=True)
        return

    ship_name = ship_data["name"]
    char_list = ", ".join(c["name"] for c in ship_data["characters"])

    class ConfirmDeleteShipView(ui.View):
        def __init__(self):
            super().__init__(timeout=15)

        @ui.button(label="Yes, Delete", style=discord.ButtonStyle.danger)
        async def confirm(self, inter, button):
            # delete_ship cascades to ship_characters and fanart_ships automatically
            delete_ship(ship_id)
            await inter.response.edit_message(
                content=f"💀 Ship **{ship_name}** deleted and removed from all fanart.",
                view=None
            )
            await asyncio.sleep(4)
            try:
                await inter.delete_original_response()
            except Exception:
                pass

        @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, inter, button):
            await inter.response.edit_message(
                content="↩️ Cancelled — ship kept.",
                view=None
            )

    embed = discord.Embed(
        title=f"🗑️ Delete Ship: {ship_name}",
        description=f"**Characters:** {char_list}\n\nThis will remove the ship from all fanart it was tagged in.",
        color=discord.Color.from_rgb(255, 100, 100)
    )
    embed.set_footer(text="This cannot be undone.")

    await interaction.response.send_message(
        embed=embed,
        view=ConfirmDeleteShipView(),
        ephemeral=True
    )


@fanart_group.command(name="add", description="Upload a fanart piece")
async def addfanart(
    interaction: discord.Interaction,
    title: str,
    image: discord.Attachment
):

    # -------------------------------------------------
    # RESOLVE USER
    # -------------------------------------------------

    user_id = get_user_id(str(interaction.user.id))

    if not user_id:
        await interaction.response.send_message(
            "❌ User profile missing.",
            ephemeral=True
        )
        return

    # -------------------------------------------------
    # UNIQUE TITLE CHECK
    # -------------------------------------------------

    from database import fanart_title_exists_for_user
    if fanart_title_exists_for_user(user_id, title):
        await interaction.response.send_message(
            f'❌ You already have a fanart piece called **"{title}"**! '
            'Please choose a different name.',
            ephemeral=True,
            delete_after=5
        )
        return

    # -------------------------------------------------
    # REHOST IMAGE TO STORAGE CHANNEL (permanent URL)
    # -------------------------------------------------

    await interaction.response.defer(ephemeral=True)

    permanent_url = await rehost_attachment(image, interaction.guild, pad=True)
    if not permanent_url:
        await interaction.followup.send(
            "❌ Failed to store image. Make sure it's a PNG, JPG, WEBP, or GIF.",
            ephemeral=True
        )
        return

    # -------------------------------------------------
    # SAVE FANART (NO STORY LINK YET)
    # -------------------------------------------------

    fanart_id = add_fanart(
        user_id,
        title,
        "",  # description starts empty
        permanent_url,
        datetime.now(timezone.utc).isoformat(),
        story_id=None
    )

    # Store the title as a hidden searchable tag (not shown in Vibe Tags field)
    from utils.tag_parser import normalize_tags
    from database import update_fanart_tags
    title_tag = normalize_tags(title)
    if title_tag:
        update_fanart_tags(fanart_id, title_tag)

    from database import grant_fanart_credit
    credit_msg = ""
    granted, new_balance = grant_fanart_credit(user_id, fanart_id)
    if granted:
        credit_msg = f"\n-# 💎 +75 crystals earned  ·  {new_balance:,} total"

    msg = await interaction.followup.send(
        (
            f"🎨 Fanart **{title}** added!{credit_msg}\n\n"
            "✨ Use `/fanart build` to add characters, ships, tags, "
            "scene descriptions, or link a story."
        ),
        ephemeral=True
    )
    await asyncio.sleep(5)
    try:
        await msg.delete()
    except Exception:
        pass

@fanart_group.command(name="search", description="Search fanart by tags — or browse all if no tags given")
@app_commands.describe(
    tag="First tag to filter by",
    tag2="Second tag (optional)",
    tag3="Third tag (optional)"
)
@app_commands.autocomplete(
    tag=fanart_tag_autocomplete,
    tag2=fanart_tag_autocomplete,
    tag3=fanart_tag_autocomplete
)
async def fanartview(
    interaction: discord.Interaction,
    tag: str = None,
    tag2: str = None,
    tag3: str = None
):
    from database import search_fanart, get_random_fanart
    from features.fanart.views.fanart_search_view import FanartSearchRosterView

    add_user(str(interaction.user.id), interaction.user.name)

    tags = [t for t in [tag, tag2, tag3] if t and t != "__hint__"]

    if tags:
        results = search_fanart(tag=tags[0])
        if len(tags) > 1:
            ids2 = {f["id"] for f in search_fanart(tag=tags[1])}
            results = [f for f in results if f["id"] in ids2]
        if len(tags) > 2:
            ids3 = {f["id"] for f in search_fanart(tag=tags[2])}
            results = [f for f in results if f["id"] in ids3]
    else:
        results = get_random_fanart()

    if not results:
        await interaction.response.send_message(
            "✦ No fanart found matching your search — try different tags!",
            ephemeral=True,
            delete_after=3
        )
        return

    # Resolve server display names — discord_id now comes directly from the query
    for f in results:
        discord_id = f.get("discord_id")
        if discord_id:
            member = interaction.guild.get_member(int(discord_id))
            if not member:
                try:
                    member = await interaction.guild.fetch_member(int(discord_id))
                except Exception:
                    member = None
            if member:
                f["display_name"] = member.display_name

    view = FanartSearchRosterView(results, interaction.user, tags, guild=interaction.guild)
    await interaction.response.send_message(embed=view.build_embed(), view=view)

@fanart_group.command(name="build", description="Open the editor for your fanart")
@app_commands.autocomplete(fanart=fanart_autocomplete)
async def editfanart(
    interaction: discord.Interaction,
    fanart: str
):

    from database import get_fanart_by_discord_user
    from features.fanart.views.fanart_editor_view import (
        FanartEditorView
    )

    # -------------------------------------------------
    # Validate ID
    # -------------------------------------------------

    try:
        fanart_id = int(fanart)
    except ValueError:
        await interaction.response.send_message(
            "❌ Select fanart from autocomplete.",
            ephemeral=True
        )
        return

    # -------------------------------------------------
    # Get User's Fanart
    # -------------------------------------------------

    fanart_items = get_fanart_by_discord_user(
        interaction.user.id
    )

    selected = next(
        (f for f in fanart_items if f["id"] == fanart_id),
        None
    )

    if not selected:
        await interaction.response.send_message(
            "Fanart not found.",
            ephemeral=True
        )
        return

    # -------------------------------------------------
    # Open Editor
    # -------------------------------------------------

    view = FanartEditorView(
        fanart=selected,
        user=interaction.user,
        bot=bot
    )

    await interaction.response.send_message(
        embed=view.build_embed(),
        view=view,
        ephemeral=True
    )

    # ⭐ IMPORTANT
    view.builder_message = await interaction.original_response()

@fanart_group.command(name="myart", description="Browse your fanart gallery")
@app_commands.autocomplete(name=fanart_autocomplete)
async def fanart_myart(
    interaction: discord.Interaction,
    name: str = None
):
    from database import get_fanart_by_discord_user, get_fanart_by_id
    from features.fanart.views.my_fanart_view import MyFanartRosterView, MyFanartDetailView

    results = get_fanart_by_discord_user(str(interaction.user.id))

    if not results:
        await interaction.response.send_message(
            "You haven't uploaded any fanart yet! Use `/fanart add` to get started. 🎨",
            ephemeral=True,
            delete_after=6
        )
        return

    owner_name = interaction.user.display_name

    # ── Direct piece selected via autocomplete or typed name ──
    if name and name != "__hint__":
        # Try matching by id (autocomplete passes id as string)
        fanart = None
        try:
            fanart = get_fanart_by_id(int(name))
        except (ValueError, TypeError):
            pass

        # Fall back to title match
        if not fanart:
            name_lower = name.lower()
            for f in results:
                if f["title"].lower() == name_lower:
                    fanart = f
                    break

        if fanart:
            # Find index in the full list
            try:
                idx = next(i for i, f in enumerate(results) if f["id"] == fanart["id"])
            except StopIteration:
                idx = 0
            # Build a dummy roster so Return works
            roster = MyFanartRosterView(results, interaction.user, owner_name)
            roster.page = idx // 5
            detail = MyFanartDetailView(
                fanarts=results,
                index=idx,
                viewer=interaction.user,
                roster=roster,
                return_page=idx // 5
            )
            await interaction.response.send_message(
                embed=detail.build_embed(),
                view=detail
            )
            detail._message = await interaction.original_response()
            return

    # ── No name → open roster ──
    view = MyFanartRosterView(results, interaction.user, owner_name)
    await interaction.response.send_message(
        embed=view.build_embed(),
        view=view
    )


# =====================================================
# AUTOCOMPLETE — user's own fanart (for /removefanart)
# =====================================================

async def own_fanart_autocomplete(interaction: discord.Interaction, current: str):
    from database import get_user_fanart_for_autocomplete

    items = get_user_fanart_for_autocomplete(str(interaction.user.id))
    choices = []

    for f in items:
        title = f["title"]
        tags  = f["tags"] or ""
        story = f["story_title"] or ""

        tag_snippet = ""
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            if tag_list:
                tag_snippet = " ✦ " + " ".join(f"#{t}" for t in tag_list[:3])

        story_snippet = f" 📖 {story}" if story else ""

        label = f"🎨 {title}{story_snippet}{tag_snippet}"

        if current.lower() in label.lower():
            choices.append(
                app_commands.Choice(name=label[:100], value=str(f["id"]))
            )

    capped = choices[:4]
    if len(choices) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped


# =====================================================
# AUTOCOMPLETE — user's favorited characters only
# =====================================================

async def own_favs_autocomplete(interaction: discord.Interaction, current: str):
    from database import get_user_id, get_all_favorites_for_user

    uid = get_user_id(str(interaction.user.id))
    if not uid:
        return []

    favs = get_all_favorites_for_user(uid)
    choices = []

    for fav in favs:
        label = f"💫 {fav['character_name']}  ✦  📖 {fav['story_title']}"
        if current.lower() in label.lower():
            choices.append(
                app_commands.Choice(name=label[:100], value=str(fav["character_id"]))
            )

    capped = choices[:4]
    if len(choices) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped


# =====================================================
# AUTOCOMPLETE — story filter for /showfavs
# =====================================================

async def favs_story_autocomplete(interaction: discord.Interaction, current: str):
    from database import get_user_id, get_all_favorites_for_user

    uid = get_user_id(str(interaction.user.id))
    if not uid:
        return []

    favs = get_all_favorites_for_user(uid)
    seen = {}
    for fav in favs:
        seen[fav["story_id"]] = fav["story_title"]

    choices = []
    for sid, stitle in seen.items():
        if current.lower() in stitle.lower():
            choices.append(
                app_commands.Choice(name=f"📖 {stitle}"[:100], value=str(sid))
            )

    capped = choices[:4]
    if len(choices) > 4:
        capped.append(
            app_commands.Choice(
                name="✏️ Keep typing to narrow down results…",
                value="__hint__"
            )
        )
    return capped


# =====================================================
# /removefanart
# =====================================================

async def liked_fanart_autocomplete(interaction: discord.Interaction, current: str):
    from database import get_liked_fanart_by_user
    results = get_liked_fanart_by_user(str(interaction.user.id))
    choices = []
    for f in results:
        title = f["title"]
        if current.lower() in title.lower():
            choices.append(app_commands.Choice(name=title[:100], value=str(f["id"])))
    capped = choices[:4]
    if len(choices) > 4:
        capped.append(app_commands.Choice(
            name="✏️ Keep typing to narrow down results…",
            value="__hint__"
        ))
    return capped


@fanart_group.command(name="liked", description="Browse fanart pieces you've liked")
@app_commands.describe(name="Jump straight to a piece by name")
@app_commands.autocomplete(name=liked_fanart_autocomplete)
async def fanart_liked(interaction: discord.Interaction, name: str = None):
    from database import get_liked_fanart_by_user, get_fanart_by_id
    from features.fanart.views.fanart_liked_view import LikedFanartRosterView, LikedFanartDetailView

    add_user(str(interaction.user.id), interaction.user.name)

    results = get_liked_fanart_by_user(str(interaction.user.id))

    if not results:
        await interaction.response.send_message(
            "💔 You haven't liked any fanart yet! Browse with `/fanart search` and press 👍.",
            ephemeral=True,
            delete_after=6
        )
        return

    # Resolve display names
    for f in results:
        discord_id = f.get("discord_id")
        if discord_id:
            member = interaction.guild.get_member(int(discord_id))
            if not member:
                try:
                    member = await interaction.guild.fetch_member(int(discord_id))
                except Exception:
                    member = None
            if member:
                f["display_name"] = member.display_name

    # Direct piece selected
    if name and name != "__hint__":
        fanart = None
        try:
            fanart = get_fanart_by_id(int(name))
        except (ValueError, TypeError):
            pass
        if not fanart:
            name_lower = name.lower()
            for f in results:
                if f["title"].lower() == name_lower:
                    fanart = f
                    break
        if fanart:
            try:
                idx = next(i for i, f in enumerate(results) if f["id"] == fanart["id"])
            except StopIteration:
                idx = 0
            roster = LikedFanartRosterView(results, interaction.user)
            roster.page = idx // 5
            detail = LikedFanartDetailView(
                fanarts=results, index=idx,
                viewer=interaction.user, roster=roster,
                return_page=idx // 5
            )
            await interaction.response.send_message(embed=detail.build_embed(), view=detail)
            detail._message = await interaction.original_response()
            return

    view = LikedFanartRosterView(results, interaction.user)
    await interaction.response.send_message(embed=view.build_embed(), view=view)


@fanart_group.command(name="delete", description="Delete one of your fanart pieces")
@app_commands.describe(fanart="Start typing to find your fanart")
@app_commands.autocomplete(fanart=own_fanart_autocomplete)
async def removefanart(interaction: discord.Interaction, fanart: str):
    from database import get_fanart_by_id_owned, delete_fanart_full

    add_user(str(interaction.user.id), interaction.user.name)

    try:
        fanart_id = int(fanart)
    except ValueError:
        await interaction.response.send_message(
            "❌ Please select a fanart piece from autocomplete.",
            ephemeral=True,
            delete_after=6
        )
        return

    row = get_fanart_by_id_owned(fanart_id, str(interaction.user.id))

    if not row:
        await interaction.response.send_message(
            "❌ Fanart not found, or you don't own it.",
            ephemeral=True,
            delete_after=6
        )
        return

    title = row["title"]

    # ── Confirmation view ────────────────────────

    class ConfirmDeleteFanartView(ui.View):

        def __init__(self, fid, ftitle):
            super().__init__(timeout=15)
            self.fid    = fid
            self.ftitle = ftitle
            self._interaction = None

        async def on_timeout(self):
            if self._interaction:
                try:
                    await self._interaction.edit_original_response(
                        content="*Prompt expired — no changes made.*",
                        view=None
                    )
                    await asyncio.sleep(2)
                    await self._interaction.delete_original_response()
                except Exception:
                    pass

        @ui.button(label="Yes, Delete", style=discord.ButtonStyle.danger)
        async def confirm(self, inter, button):
            self._interaction = inter
            self.stop()
            delete_fanart_full(self.fid)
            await inter.response.edit_message(
                content=f"🗑️ **{self.ftitle}** deleted successfully.",
                view=None
            )
            await asyncio.sleep(4)
            try:
                await inter.delete_original_response()
            except Exception:
                pass

        @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, inter, button):
            self._interaction = inter
            self.stop()
            await inter.response.edit_message(
                content="↩️ Cancelled — no changes made.",
                view=None
            )
            await asyncio.sleep(3)
            try:
                await inter.delete_original_response()
            except Exception:
                pass

    confirm_view = ConfirmDeleteFanartView(fanart_id, title)

    await interaction.response.send_message(
        (
            f"⚠️ Delete fanart **\"{title}\"**?\n"
            f"This will remove all associated characters, ships, and tags too.\n\n"
            f"*Type* **Yes, Delete** *to confirm — expires in 15 seconds.*"
        ),
        view=confirm_view,
        ephemeral=True
    )
    confirm_view._interaction = interaction


# =====================================================
# /showfavs
# =====================================================

@character_group.command(name="favs", description="See your favorited characters")
@app_commands.describe(story="Optional: filter to a specific story")
@app_commands.autocomplete(story=favs_story_autocomplete)
async def showfavs(interaction: discord.Interaction, story: str = None):
    from database import get_user_id, get_all_favorites_for_user
    from features.characters.views.show_favs_view import ShowFavsView

    add_user(str(interaction.user.id), interaction.user.name)

    uid = get_user_id(str(interaction.user.id))
    if not uid:
        await interaction.response.send_message(
            "❌ You don't have a profile yet. Try `/library browse` first!",
            ephemeral=True
        )
        return

    raw_favs = get_all_favorites_for_user(uid)

    if not raw_favs:
        await interaction.response.send_message(
            "💔 You haven't favorited any characters yet!\n"
            "Browse characters in `/library browse` or `/character search` and press ✦ Favorite.",
            ephemeral=True,
            delete_after=5
        )
        return

    filter_id = None
    if story:
        try:
            filter_id = int(story)
        except ValueError:
            pass

    view = ShowFavsView(raw_favs, interaction.user, filter_story_id=filter_id)

    await interaction.response.send_message(
        embed=view.build_embed(),
        view=view
    )


# =====================================================
# /removefav
# =====================================================

@character_group.command(name="unfav", description="Remove a favorited character")
@app_commands.describe(character="Start typing a favorited character's name")
@app_commands.autocomplete(character=own_favs_autocomplete)
async def removefav(interaction: discord.Interaction, character: str):
    from database import get_user_id, get_character_by_id, remove_favorite_character, is_favorite_character

    add_user(str(interaction.user.id), interaction.user.name)

    try:
        char_id = int(character)
    except ValueError:
        await interaction.response.send_message(
            "❌ Please select a character from autocomplete.",
            ephemeral=True,
            delete_after=6
        )
        return

    uid = get_user_id(str(interaction.user.id))
    if not uid:
        await interaction.response.send_message(
            "❌ Profile not found.",
            ephemeral=True,
            delete_after=6
        )
        return

    if not is_favorite_character(uid, char_id):
        await interaction.response.send_message(
            "❌ That character isn't in your favorites.",
            ephemeral=True,
            delete_after=6
        )
        return

    char = get_character_by_id(char_id)
    char_name = char["name"] if char else f"Character #{char_id}"

    remove_favorite_character(uid, char_id)

    await interaction.response.send_message(
        f"💔 **{char_name}** removed from your favorites.",
        ephemeral=True,
        delete_after=5
    )



# =====================================================
# /story — Quick story access
# =====================================================

@story_group.command(name="open", description="Jump straight to any story's page")
@app_commands.describe(story="Start typing a story title")
@app_commands.autocomplete(story=global_story_autocomplete)
async def story_open(interaction: discord.Interaction, story: str):
    from features.stories.views.library_view import LibraryView, story_to_dict
    from database import get_all_stories_sorted

    if story == "__hint__":
        await interaction.response.send_message(
            "Keep typing to find your story!", ephemeral=True
        )
        return

    add_user(str(interaction.user.id), interaction.user.name)

    try:
        story_id = int(story)
    except ValueError:
        story_id = get_story_id_by_title(story)

    if not story_id:
        await interaction.response.send_message("❌ Story not found.", ephemeral=True)
        return

    # Load full library so the view can navigate, but open directly to this story
    stories = get_all_stories_sorted("alphabetical")
    if not stories:
        await interaction.response.send_message("Library is empty.", ephemeral=True)
        return

    view = LibraryView(stories, "📚 Global Library", interaction.user)

    # Find and select the story directly
    match = next((s for s in stories if story_to_dict(s)["id"] == story_id), None)
    if not match:
        await interaction.response.send_message("❌ Story not found in library.", ephemeral=True)
        return

    view.current_item = match
    view.mode = "story"
    view.refresh_ui()

    await interaction.response.send_message(
        embed=view.generate_detail_embed(match),
        view=view
    )
    view.message = await interaction.original_response()


async def _story_cast_char_autocomplete(
    interaction: discord.Interaction,
    current: str
):
    """Autocomplete for /story cast character — scoped to the chosen story only."""
    story_value = interaction.namespace.story
    if not story_value or story_value == "__hint__":
        return []
    try:
        story_id = int(story_value)
    except ValueError:
        story_id = get_story_id_by_title(story_value)
    if not story_id:
        return []

    from database import get_characters_by_story
    chars = get_characters_by_story(story_id)

    HINT = app_commands.Choice(name="✏️ Type to search characters...", value="__hint__")

    matched = [
        app_commands.Choice(name=c["name"][:100], value=str(c["id"]))
        for c in chars
        if current.lower() in c["name"].lower()
    ]

    choices = matched[:4]
    choices.append(HINT)
    return choices


@story_group.command(name="cast", description="Browse a story's character roster")
@app_commands.describe(
    story="Start typing a story title",
    character="Optional: jump straight to a specific character"
)
@app_commands.autocomplete(story=global_story_autocomplete,
                            character=_story_cast_char_autocomplete)
async def story_cast(interaction: discord.Interaction,
                     story: str,
                     character: str = None):
    from database import get_characters_by_story, get_story_by_id
    from features.characters.views.characters_view import (
        StoryCharactersView, StoryCastRosterView, build_cast_roster_embed, CAST_PAGE_SIZE
    )

    if story == "__hint__":
        await interaction.response.send_message("Keep typing!", ephemeral=True)
        return

    add_user(str(interaction.user.id), interaction.user.name)

    try:
        story_id = int(story)
    except ValueError:
        story_id = get_story_id_by_title(story)

    if not story_id:
        await interaction.response.send_message("❌ Story not found.", ephemeral=True)
        return

    story_data = get_story_by_id(story_id)
    if not story_data:
        await interaction.response.send_message("❌ Story not found.", ephemeral=True)
        return

    chars = get_characters_by_story(story_id)
    if not chars:
        await interaction.response.send_message(
            "This story has no characters yet.", ephemeral=True
        )
        return

    story_title = story_data["title"] if isinstance(story_data, dict) else story_data[2]
    chars = [dict(c) for c in chars]

    # Fetch author profile thumbnail (optional — silently skipped if missing)
    from database import get_discord_id_by_story, get_profile_by_discord_id
    author_discord_id  = get_discord_id_by_story(story_id)
    author_image_url   = None
    if author_discord_id:
        profile = get_profile_by_discord_id(author_discord_id)
        author_image_url = profile.get("image_url")

    # Build the roster (always needed as the return target)
    roster = StoryCastRosterView(chars, interaction.user, story_title=story_title,
                                 author_image_url=author_image_url)

    if character and character != "__hint__":
        try:
            char_id = int(character)
        except ValueError:
            char_id = None

        char_ids = [c["id"] for c in chars]
        if char_id not in char_ids:
            # Stale value from a previously selected story — just open the roster
            await interaction.response.send_message(
                embed=build_cast_roster_embed(chars, 0, roster.total_pages(), story_title, author_image_url),
                view=roster
            )
            return

        start_index = char_ids.index(char_id)
        return_page = start_index // CAST_PAGE_SIZE
        roster.page = return_page
        roster._rebuild_ui()

        detail_view = StoryCharactersView(
            chars,
            parent_view=roster,
            story_title=story_title,
            viewer=interaction.user,
            return_mode="cast_roster",
            start_index=start_index
        )
        await interaction.response.send_message(
            embed=detail_view.build_embed(),
            view=detail_view
        )
        return

    # Default: open the roster list
    total_pages = roster.total_pages()
    await interaction.response.send_message(
        embed=build_cast_roster_embed(chars, 0, total_pages, story_title, author_image_url),
        view=roster
    )


async def _story_fanart_autocomplete(
    interaction: discord.Interaction,
    current: str
):
    """Autocomplete for /story fanart piece — scoped to the chosen story only."""
    story_value = interaction.namespace.story
    if not story_value or story_value == "__hint__":
        return []
    try:
        story_id = int(story_value)
    except ValueError:
        story_id = get_story_id_by_title(story_value)
    if not story_id:
        return []

    from database import get_fanart_by_story
    fanarts = get_fanart_by_story(story_id)

    HINT = app_commands.Choice(name="✏️ Type to search fanart...", value="__hint__")

    matched = [
        app_commands.Choice(
            name=f"{f['title']} ✦ {f.get('story_title', '')}"[:100],
            value=str(f["id"])
        )
        for f in fanarts
        if current.lower() in f["title"].lower()
    ]

    choices = matched[:4]
    choices.append(HINT)
    return choices


@story_group.command(name="fanart", description="Browse all fanart for a specific story")
@app_commands.describe(
    story="Start typing a story title",
    piece="Optional: jump straight to a specific piece"
)
@app_commands.autocomplete(story=global_story_autocomplete,
                            piece=_story_fanart_autocomplete)
async def story_fanart(interaction: discord.Interaction,
                       story: str,
                       piece: str = None):
    from database import get_fanart_by_story, get_story_by_id
    from features.fanart.views.story_fanart_view import (
        StoryFanartRosterView, StoryFanartDetailView,
        build_story_fanart_list_embed, PAGE_SIZE as FANART_PAGE_SIZE
    )

    if story == "__hint__":
        await interaction.response.send_message("Keep typing!", ephemeral=True)
        return

    add_user(str(interaction.user.id), interaction.user.name)

    try:
        story_id = int(story)
    except ValueError:
        story_id = get_story_id_by_title(story)

    if not story_id:
        await interaction.response.send_message("❌ Story not found.", ephemeral=True)
        return

    story_data = get_story_by_id(story_id)
    if not story_data:
        await interaction.response.send_message("❌ Story not found.", ephemeral=True)
        return

    fanarts = get_fanart_by_story(story_id)
    if not fanarts:
        await interaction.response.send_message(
            "No fanart found for this story yet.", ephemeral=True
        )
        return

    story_title = story_data["title"] if isinstance(story_data, dict) else story_data[2]
    roster = StoryFanartRosterView(fanarts, interaction.user, story_title=story_title)

    if piece and piece != "__hint__":
        try:
            fanart_id = int(piece)
        except ValueError:
            fanart_id = None

        fanart_ids = [f["id"] for f in fanarts]
        if fanart_id not in fanart_ids:
            # Stale value from a previously selected story — just open the roster
            await interaction.response.send_message(
                embed=build_story_fanart_list_embed(fanarts, 0, roster.total_pages(), story_title),
                view=roster
            )
            return

        start_index = fanart_ids.index(fanart_id)
        return_page = start_index // FANART_PAGE_SIZE
        roster.page = return_page
        roster._rebuild_ui()

        detail = StoryFanartDetailView(
            fanarts, start_index,
            interaction.user, roster=roster, return_page=return_page
        )
        await interaction.response.send_message(embed=detail.build_embed(), view=detail)
        return

    # Default: open roster list
    await interaction.response.send_message(
        embed=build_story_fanart_list_embed(fanarts, 0, roster.total_pages(), story_title),
        view=roster
    )


@story_group.command(name="stats", description="See stats and activity for a story")
@app_commands.describe(story="Start typing a story title")
@app_commands.autocomplete(story=global_story_autocomplete)
async def story_stats(interaction: discord.Interaction, story: str):
    from database import (
        get_story_by_id, get_characters_by_story,
        get_fanart_by_story, get_all_comments_unified,
        get_chapters_full, get_chapter_id_by_number,
        add_comment, add_global_comment, get_user_id
    )
    from features.stories.views.story_extras_view import StoryExtrasView
    from embeds.story_notes_embed import build_story_notes_embed

    if story == "__hint__":
        await interaction.response.send_message("Keep typing!", ephemeral=True)
        return

    add_user(str(interaction.user.id), interaction.user.name)

    try:
        story_id = int(story)
    except ValueError:
        story_id = get_story_id_by_title(story)

    if not story_id:
        await interaction.response.send_message("❌ Story not found.", ephemeral=True)
        return

    story_data = get_story_by_id(story_id)
    if not story_data:
        await interaction.response.send_message("❌ Story not found.", ephemeral=True)
        return

    ch_count = story_data["chapter_count"] if isinstance(story_data, dict) else story_data[5]

    def gather_stats():
        chars    = get_characters_by_story(story_id)
        fanarts  = get_fanart_by_story(story_id)
        comments = get_all_comments_unified(story_id)
        chapters = get_chapters_full(story_id)
        chapters_built = sum(
            1 for c in chapters
            if c.get("chapter_summary") and c.get("chapter_image_url") and
               (c.get("chapter_wattpad_url") or c.get("chapter_ao3_url"))
        )
        commented_chapters   = len({c["chapter_number"] for c in comments if c.get("chapter_number")})
        global_comment_count = sum(1 for c in comments if c.get("chapter_number") is None)
        return {
            "chars":                len(chars),
            "fanarts":              len(fanarts),
            "comments":             len(comments),
            "ch_count":             ch_count,
            "chapters_built":       chapters_built,
            "commented_chapters":   commented_chapters,
            "global_comment_count": global_comment_count,
        }

    # ── Build the enriched extras view ───────────────────────────────

    # StoryExtrasView with library_view=self_ref so "Return to Story"
    # can refresh the embed. We pass a thin shim as library_view.
    class StatsExtrasView(StoryExtrasView):
        """
        StoryExtrasView subclass that:
        - Builds the embed with live stats injected
        - Adds 💬 comment button and 👁️ See Comments button on row 1
        - Refreshes in place when a comment is posted
        """

        def build_embed(self):
            return build_story_notes_embed(
                story_data,
                viewer=interaction.user,
                stats=gather_stats()
            )

    # Use library_view=shim so "Return to Story" inside StoryExtrasView
    # calls shim.generate_detail_embed(shim.current_item) → our build_embed
    class _Shim:
        def __init__(self, view):
            self._view = view
        @property
        def current_item(self):
            return story_data
        def generate_detail_embed(self, _=None):
            return self._view.build_embed()
        def refresh_ui(self):
            pass

    stats_extras = StatsExtrasView(
        story_id=story_id,
        viewer=interaction.user,
        stats_mode=True
    )
    shim = _Shim(stats_extras)
    stats_extras.library_view = shim

    # ── Add comment + see-comments buttons (row 1) ───────────────────

    COMMENTS_PER_PAGE = 7

    class StatsCommentsView(TimeoutMixin, ui.View):

        def __init__(self, guild, parent):
            super().__init__(timeout=300)
            self.guild    = guild
            self.parent   = parent
            self.viewer   = getattr(parent, 'viewer', None)
            self.page     = 0
            self.comments = get_all_comments_unified(story_id)
            self._rebuild()

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.message:
                self.message = interaction.message
            if self.viewer and interaction.user.id != self.viewer.id:
                await interaction.response.send_message(
                    "❌ This session belongs to someone else.",
                    ephemeral=True, delete_after=5
                )
                return False
            return True

        def _total_pages(self):
            return max(1, (len(self.comments) + COMMENTS_PER_PAGE - 1) // COMMENTS_PER_PAGE)

        def _rebuild(self):
            self.prev_page.disabled = self.page == 0
            self.next_page.disabled = self.page >= self._total_pages() - 1

        async def _resolve_names(self):
            start = self.page * COMMENTS_PER_PAGE
            chunk = self.comments[start:start + COMMENTS_PER_PAGE]
            if self.guild:
                for c in chunk:
                    try:
                        member = self.guild.get_member(int(c["discord_id"]))
                        if not member:
                            member = await self.guild.fetch_member(int(c["discord_id"]))
                        if member:
                            c["display_name"] = member.display_name
                    except Exception:
                        pass

        def build_embed(self):
            import datetime as _dt
            title_str = story_data["title"] if isinstance(story_data, dict) else story_data[2]
            start = self.page * COMMENTS_PER_PAGE
            chunk = self.comments[start:start + COMMENTS_PER_PAGE]
            embed = discord.Embed(
                title=f"💬  Comments  ·  {title_str}",
                color=discord.Color.blurple()
            )
            embed.description = f"-# Page {self.page + 1} of {self._total_pages()}  ·  {len(self.comments)} total"
            if not chunk:
                embed.add_field(name="No comments yet", value="Be the first!", inline=False)
                return embed
            for c in chunk:
                try:
                    dt   = _dt.datetime.fromisoformat(c["created_at"])
                    when = dt.strftime("%b %d, %Y")
                except Exception:
                    when = c.get("created_at", "")
                display  = c.get("display_name") or c["username"]
                ch_num   = c.get("chapter_number")
                ch_name  = c.get("chapter_title")
                context  = (f"📖 Chapter {ch_num}" + (f" — *{ch_name}*" if ch_name else "")) if ch_num else "🌐 Global"
                embed.add_field(
                    name=f"**{display}**  ·  {when}  ·  {context}",
                    value=f"> {c['content'][:300]}{'…' if len(c['content']) > 300 else ''}",
                    inline=False
                )
            return embed

        @ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, row=0)
        async def prev_page(self, interaction: discord.Interaction, _):
            self.page = max(0, self.page - 1)
            self._rebuild()
            await self._resolve_names()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

        @ui.button(label="📖 Back to Story Dex", style=discord.ButtonStyle.success, row=0)
        async def back_btn(self, interaction: discord.Interaction, _):
            await interaction.response.edit_message(
                embed=self.parent.build_embed(), view=self.parent
            )

        @ui.button(emoji="➡️", style=discord.ButtonStyle.secondary, row=0)
        async def next_page(self, interaction: discord.Interaction, _):
            self.page = min(self._total_pages() - 1, self.page + 1)
            self._rebuild()
            await self._resolve_names()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    class StoryCommentModal(discord.ui.Modal, title="Leave a Comment"):
        chapter_field = discord.ui.TextInput(
            label="Chapter number (optional)",
            placeholder="Leave blank for a global comment",
            required=False,
            max_length=4
        )
        comment_field = discord.ui.TextInput(
            label="Your comment",
            style=discord.TextStyle.paragraph,
            placeholder="Share your thoughts...",
            max_length=1000,
            required=True
        )

        def __init__(self, guild=None):
            super().__init__()
            self.guild = guild

        async def on_submit(self, interaction: discord.Interaction):
            uid = get_user_id(str(interaction.user.id))
            if not uid:
                await interaction.response.send_message("❌ Could not find your profile.", ephemeral=True)
                return
            ch_raw  = self.chapter_field.value.strip()
            content = self.comment_field.value.strip()
            if ch_raw:
                try:
                    ch_num = int(ch_raw)
                except ValueError:
                    return
                if ch_num < 1 or ch_num > ch_count:
                    return
                chapter_id = get_chapter_id_by_number(story_id, ch_num)
                if not chapter_id:
                    return
                add_comment(uid, story_id, chapter_id, content)
                await interaction.response.send_message(
                    f"💬 Comment posted on **Chapter {ch_num}**!", ephemeral=True, delete_after=5
                )
            else:
                add_global_comment(uid, story_id, content)
                await interaction.response.send_message(
                    "🌐 Global comment posted!", ephemeral=True, delete_after=5
                )
            # Refresh the stats embed immediately
            try:
                await stats_extras.message.edit(embed=stats_extras.build_embed(), view=stats_extras)
            except Exception:
                pass

    # Attach comment + see-comments to the extras view on row 1
    comment_btn = ui.Button(emoji="💬", style=discord.ButtonStyle.primary, row=1)
    async def _comment_cb(interaction: discord.Interaction):
        await interaction.response.send_modal(StoryCommentModal(guild=interaction.guild))
    comment_btn.callback = _comment_cb
    stats_extras.add_item(comment_btn)

    see_comments_btn = ui.Button(label="👁️ See Comments", style=discord.ButtonStyle.primary, row=1)
    async def _see_comments_cb(interaction: discord.Interaction):
        cv = StatsCommentsView(interaction.guild, stats_extras)
        await cv._resolve_names()
        await interaction.response.edit_message(embed=cv.build_embed(), view=cv)
    see_comments_btn.callback = _see_comments_cb
    stats_extras.add_item(see_comments_btn)

    msg = await interaction.response.send_message(
        embed=stats_extras.build_embed(),
        view=stats_extras
    )
    stats_extras.message = await interaction.original_response()



# ── Register all groups ────────────────────────────
bot.tree.add_command(fic_group)
bot.tree.add_command(profile_group)
bot.tree.add_command(ships_group)
bot.tree.add_command(fanart_group)
bot.tree.add_command(character_group)
bot.tree.add_command(ctc_group)
bot.tree.add_command(gem_group)
bot.tree.add_command(story_group)

admin_group = app_commands.Group(name="admin", description="Admin-only commands", guild_ids=[GUILD_ID])
bot.tree.add_command(admin_group)

from features.ctc.ctc_commands import register_ctc_commands
register_ctc_commands(ctc_group, GUILD_ID)

from features.gem.gem_commands import register_gem_commands
register_gem_commands(gem_group, GUILD_ID)

from features.admin.admin_commands import register_admin_commands
register_admin_commands(admin_group, GUILD_ID)

import ui as _ui_module

_orig_close = bot.close

async def _graceful_close():
    """Flip the shutdown flag so open views respond gracefully, then close normally."""
    _ui_module._shutting_down = True
    await _orig_close()

bot.close = _graceful_close

bot.run(TOKEN)