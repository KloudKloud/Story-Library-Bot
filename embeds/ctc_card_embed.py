"""
ctc_card_embed.py
─────────────────────────────────────────────────────────────────────────────
CTC trading-card embed  —  Pokémon-card inspired layout.

Public API:
    build_ctc_card_embed(char, viewer_uid, *, ...) → (embed, view)
    build_ctc_collection_view(cards, viewer_uid, ...) → (embed, view)
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import datetime
import random
from typing import Optional

import discord
from discord import ui

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

CRYSTAL = "💎"

def _get_placeholder() -> str:
    """Read the placeholder URL lazily so it's always the padded version after startup."""
    try:
        from pad_placeholder import PADDED_PLACEHOLDER_URL
        return PADDED_PLACEHOLDER_URL
    except ImportError:
        return (
            "https://cdn.discordapp.com/attachments/1478560442723864737/1484845369644028036/"
            "no-image-vector-symbol-missing-available-icon-no-gallery-for-this-moment-placeholder.png"
            "?ex=69bfb583&is=69be6403&hm=dba7a6a9b8c853041ef330d0d4a8f0dde08b7909656244ff4f2ea657a8a74aad&"
        )

# 50-color palette — strictly no gold, no amber, no orange, no yellow
# All entries are clearly purple/blue/teal/pink/green/red toned
_PALETTE = [
    (186, 104, 200), (149, 117, 205), (121, 134, 203), (100, 181, 246),
    ( 77, 182, 172), (129, 199, 132), (244, 143, 177), (179, 157, 219),
    (140, 158, 255), (240,  98, 146), ( 66, 165, 245), ( 38, 166, 154),
    (171,  71, 188), ( 80, 200, 230), (160, 120, 255), (100, 220, 180),
    (220, 100, 180), ( 90, 180, 255), (130, 220, 120), (200,  80, 130),
    (255,  80, 200), ( 80, 160, 255), (170,  60, 210), ( 60, 200, 210),
    (120, 220, 120), ( 80, 210,  90), ( 50, 190, 255), (120,  80, 255),
    (200, 150, 255), ( 70, 220, 150), (150, 100, 255), (100, 255, 200),
    (255,  90, 150), ( 90, 200, 100), (100, 150, 255), (160, 255, 180),
    (210, 100, 255), ( 80, 230, 200), (180, 100, 255), ( 60, 170, 240),
    (255, 120, 180), (100, 200, 255), ( 80, 255, 180), (200,  80, 200),
    (120, 255, 210), ( 60, 140, 255), (255, 100, 200), (140, 255, 160),
    (190,  80, 255), ( 70, 210, 190),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _char_color(char_id: int, shiny: bool) -> discord.Color:
    if shiny:
        return discord.Color.gold()
    _local_rng = random.Random(char_id)
    r, g, b = _local_rng.choice(_PALETTE)
    return discord.Color.from_rgb(r, g, b)


def _div() -> str:
    return "── ✦ ──────────────────── ✦ ──"


def _via_label(via: str | None, at: str | None) -> str | None:
    via_map = {
        "roll": "🎲 Spin", "free_roll": "🎲 Free Spin",
        "direct_buy": "🛒 Direct Buy", "trade": "🤝 Trade",
        "gift": "🎁 Gift", "event": "🌟 Event", "upgrade": "✨ Upgraded",
    }
    label = via_map.get(via or "", via) if via else None
    if label and at:
        try:
            # Mark as UTC so .timestamp() converts correctly regardless of server timezone
            dt = datetime.datetime.fromisoformat(at).replace(
                tzinfo=datetime.timezone.utc
            )
            ts = int(dt.timestamp())
            label += f" · <t:{ts}:f>"
        except Exception:
            pass
    return label


def _progress_bar(owned: int, total: int, steps: int = 10) -> str:
    pct    = min(owned / total, 1.0)
    filled = int(pct * steps)
    if filled >= steps:
        return "✦ " * steps + "✨"
    if filled == 0:
        return "· " * steps
    return "✦ " * filled + "✨ " + "· " * (steps - filled)


def _cover_fallback(char_id: int) -> str | None:
    try:
        from database import get_story_by_character
        story = get_story_by_character(char_id)
        if story:
            url = story["cover_url"]
            if url and url.startswith("http"):
                return url
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Core embed builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_core_embed(
    char:         dict,
    *,
    shiny:        bool       = False,
    obtained_via: str | None = None,
    obtained_at:  str | None = None,
    index:        int        = 1,
    total:        int        = 1,
    owned_count:  int | None = None,
    total_chars:  int | None = None,
) -> discord.Embed:

    char_id   = char.get("id", 0)
    name      = char.get("name") or "Unknown Character"
    story     = char.get("story_title") or char.get("story") or "Unknown Story"
    author    = char.get("author") or char.get("username") or "Unknown Author"
    image_url = char.get("image_url") or _get_placeholder()
    # If this is a shiny render and the author provided a dedicated shiny image, use it
    if shiny:
        shiny_img = char.get("shiny_image_url")
        if shiny_img and shiny_img.startswith("http"):
            image_url = shiny_img
    cover_url = char.get("cover_url") or char.get("story_cover")
    quote     = char.get("quote")
    gender    = char.get("gender") or "Unknown"
    species   = char.get("species") or "Unknown"
    age       = char.get("age") or "Unknown"
    height    = char.get("height") or "Unknown"
    physical  = char.get("physical_features")
    relations = char.get("relationships")
    music_url = char.get("music_url")
    biography = char.get("personality")
    lore      = char.get("lore")

    try:
        from database import get_card_owner_count
        owner_cnt = get_card_owner_count(char_id)
    except Exception:
        owner_cnt = 0

    if not (cover_url and cover_url.startswith("http")):
        cover_url = _cover_fallback(char_id)

    color = _char_color(char_id, shiny)
    div   = _div()

    title = f"✨ ★  {name.upper()}  ★ ✨" if shiny else f"✧･ﾟ: ✦  {name.upper()}  ✦ :･ﾟ✧"

    desc_lines = []
    if shiny:
        desc_lines.append("⋆｡‧˚ʚ ✨ ɞ˚‧｡⋆  **✦ SHINY CARD ✦**  ⋆｡‧˚ʚ ✨ ɞ˚‧｡⋆")
    desc_lines.append(f"⭐ **{story}**  ·  *by {author}* ⭐")
    desc_lines.append(div)

    embed = discord.Embed(title=title, description="\n".join(desc_lines), color=color)

    if cover_url:
        embed.set_thumbnail(url=cover_url)

    # ── Inline row 1: Gender · Age · Height ──────────────────────────────────
    embed.add_field(name="⚧️ Gender", value=gender, inline=True)
    embed.add_field(name="🎂 Age",    value=str(age),    inline=True)
    embed.add_field(name="📏 Height", value=str(height), inline=True)

    # ── Inline row 2: Species · Looks · Bonds ────────────────────────────────
    looks_val = "Unknown"
    if physical:
        first = physical.splitlines()[0].strip()
        if first:
            looks_val = first

    bonds_val = "Unknown"
    if relations:
        first = relations.splitlines()[0].strip()
        if first:
            bonds_val = first

    embed.add_field(name="🧬 Species", value=species,   inline=True)
    embed.add_field(name="👁️ Looks",   value=looks_val, inline=True)
    embed.add_field(name="💞 Bonds",   value=bonds_val, inline=True)

    # ── Lore ─────────────────────────────────────────────────────────────────
    embed.add_field(name="\u200b", value=div, inline=False)
    if lore:
        lore_text = (lore[:320] + "…") if len(lore) > 320 else lore
        lore_display = f"*{lore_text}*"
    else:
        lore_display = f"*No lore has been written for {name} yet. Their story is still unfolding…*"
    embed.add_field(name="❋ ❋ ❋  𝐋𝐎𝐑𝐄", value=lore_display, inline=False)

    # ── Biography ─────────────────────────────────────────────────────────────
    embed.add_field(name="\u200b", value=div, inline=False)
    if biography:
        preview = (biography[:400] + "…") if len(biography) > 400 else biography
        bio_display = "\n".join(
            f"> {line}" if line.strip() else ">" for line in preview.splitlines()
        )
    else:
        bio_display = (
            f"> *{name} is featured in **{story}** and has yet to have a bio "
            f"written for them. Check back soon!*"
        )
    embed.add_field(name="❋ ❋  𝐁𝐈𝐎𝐆𝐑𝐀𝐏𝐇𝐘", value=bio_display, inline=False)

    # ── Shiny badge ───────────────────────────────────────────────────────────
    if shiny:
        shiny_at   = char.get("shiny_at")
        shiny_date = ""
        if shiny_at:
            try:
                try:
                    dt = datetime.datetime.fromisoformat(shiny_at).replace(
                        tzinfo=datetime.timezone.utc
                    )
                    ts = int(dt.timestamp())
                    shiny_date = f" · obtained <t:{ts}:f>"
                except Exception:
                    shiny_date = ""
            except Exception:
                pass
        embed.add_field(
            name="✨ 𝐒𝐇𝐈𝐍𝐘 𝐂𝐀𝐑𝐃",
            value=f"-# 🌟 One of a kind{shiny_date}\n-# 💎 Ultra Rare",
            inline=False,
        )

    # ── Outro strip ───────────────────────────────────────────────────────────
    embed.add_field(name="\u200b", value=div, inline=False)

    via_label = _via_label(obtained_via, obtained_at)

    embed.add_field(
        name="🎵 𝐓𝐇𝐄𝐌𝐄 𝐒𝐎𝐍𝐆",
        value=f"[♪ Listen Here]({music_url})" if music_url else "-# *No theme set*",
        inline=True,
    )

    # Shiny collector count
    try:
        from database import get_connection as _gc
        _conn = _gc()
        _row  = _conn.execute(
            "SELECT COUNT(*) AS cnt FROM ctc_collection WHERE character_id=? AND is_shiny=1",
            (char_id,)
        ).fetchone()
        _conn.close()
        shiny_cnt = _row["cnt"] if _row else 0
    except Exception:
        shiny_cnt = 0

    ctc_lines = [
        f"🃏 **{owner_cnt}** collector{'s' if owner_cnt != 1 else ''}"
        if owner_cnt else "🃏 Be the first collector!",
        f"✨ **{shiny_cnt}** shiny collector{'s' if shiny_cnt != 1 else ''}",
    ]
    embed.add_field(
        name="💎 𝐂𝐓𝐂 𝐂𝐀𝐑𝐃",
        value="\n".join(f"-# {l}" for l in ctc_lines),
        inline=True,
    )
    embed.add_field(
        name="🗂️ 𝐎𝐁𝐓𝐀𝐈𝐍𝐄𝐃",
        value=f"-# {via_label}" if via_label else "-# *Not yet collected*",
        inline=True,
    )

    # ── Collection progress bar ────────────────────────────────────────────────
    if owned_count is not None and total_chars and total_chars > 0:
        try:
            from database import MILESTONE_INTERVAL, MILESTONE_BONUS
        except Exception:
            MILESTONE_INTERVAL, MILESTONE_BONUS = 10, 500
        bar     = _progress_bar(owned_count, total_chars).strip()
        pct     = f"{int(min(owned_count / total_chars, 1.0) * 100)}%"
        next_ms = ((owned_count // MILESTONE_INTERVAL) + 1) * MILESTONE_INTERVAL
        to_next = next_ms - owned_count
        embed.add_field(
            name="✨  𝐂𝐎𝐋𝐋𝐄𝐂𝐓𝐈𝐎𝐍 𝐏𝐑𝐎𝐆𝐑𝐄𝐒𝐒",
            value=(
                f"{bar}  **{pct}**\n"
                f"-# {owned_count} / {total_chars} cards  ·  "
                f"{CRYSTAL} +{MILESTONE_BONUS} in **{to_next}** more "
                f"card{'s' if to_next != 1 else ''}"
            ),
            inline=False,
        )

    # ── Hero image (always shown) ──────────────────────────────────────────────
    if not (image_url and image_url.startswith("http")):
        image_url = _get_placeholder()
    embed.set_image(url=image_url)

    # ── Footer ────────────────────────────────────────────────────────────────
    footer_parts = []
    if quote:
        footer_parts.append(quote)
    footer_parts.append(f"✦ ✦  Card {index} of {total}  ·  CTC Collection  ✦ ✦")
    embed.set_footer(text="  ·  ".join(footer_parts))

    return embed


# ─────────────────────────────────────────────────────────────────────────────
# "Behind the Scenes..." dropdown
# ─────────────────────────────────────────────────────────────────────────────

def _full_refresh(view: "CTCCardView"):
    """
    Rebuild a CTCCardView (or ShopCardView subclass) completely.
    Calls _refresh() for the base buttons, then _rebuild_shop_buttons()
    if the view is a ShopCardView so row-1 buy/return buttons come back too.
    """
    view._refresh()
    if hasattr(view, "_rebuild_shop_buttons"):
        view._rebuild_shop_buttons()


class _BehindTheScenesSelect(ui.Select):
    """
    Dropdown with up to 4 options:
      1. View [Story Title]
      2. See [Author]'s profile
      3. Explore [Name]'s character card
      4. Browse [Name] Fanart (N)   — only if fanart exists
    """

    def __init__(self, char: dict, viewer: discord.Member, ctc_view: "CTCCardView", row: int):
        self._char     = char
        self._viewer   = viewer
        self._ctc_view = ctc_view

        name     = char.get("name") or "this character"
        story    = char.get("story_title") or char.get("story") or "the story"
        author   = char.get("author") or char.get("username") or "the author"
        char_id  = char.get("id", 0)
        story_id = char.get("story_id")

        fanart_count = 0
        try:
            from database import get_fanart_by_character
            fanart_count = len(get_fanart_by_character(char_id))
        except Exception:
            pass

        options = []

        if story_id:
            options.append(discord.SelectOption(
                label=f"View {story}"[:100], emoji="📖", value=f"story:{story_id}",
            ))
            options.append(discord.SelectOption(
                label=f"See {author}'s profile"[:100], emoji="✍️", value=f"author:{story_id}",
            ))

        options.append(discord.SelectOption(
            label=f"Explore {name}'s character card"[:100], emoji="🧬", value=f"char:{char_id}",
        ))

        if fanart_count > 0:
            options.append(discord.SelectOption(
                label=f"Browse {name} Fanart ({fanart_count})"[:100],
                emoji="🎨", value=f"fanart:{char_id}",
            ))

        super().__init__(placeholder="🎬 Behind the Scenes...", options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        value    = self.values[0]
        ctc_view = self._ctc_view

        # ── Story ─────────────────────────────────────────────────────────────
        if value.startswith("story:"):
            story_id = int(value.split(":")[1])
            from features.fanart.views.fanart_search_view import SearchStoryView

            ctc_ref = ctc_view

            class _ReturnStoryView(SearchStoryView):
                def __init__(sv, sid, viewer):
                    super().__init__(story_id=sid, viewer=viewer, back_detail=None)
                    sv.clear_items()
                    eb = ui.Button(label="✨ Extras", style=discord.ButtonStyle.primary, row=0)
                    eb.callback = sv._extras
                    sv.add_item(eb)
                    rb = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=0)
                    async def _back(i):
                        _full_refresh(ctc_ref)
                        await i.response.edit_message(embed=ctc_ref._build_embed(), view=ctc_ref)
                    rb.callback = _back
                    sv.add_item(rb)

            view  = _ReturnStoryView(story_id, interaction.user)
            embed = view.build_story_embed()
            if not embed:
                await interaction.response.send_message("Story not found.", ephemeral=True, delete_after=4)
                return
            await interaction.response.edit_message(embed=embed, view=view)
            return

        # ── Author profile ─────────────────────────────────────────────────────
        if value.startswith("author:"):
            story_id   = int(value.split(":")[1])
            from database import get_discord_id_by_story, get_stories_by_discord_user
            discord_id = get_discord_id_by_story(story_id)
            if not discord_id:
                await interaction.response.send_message("Author not found.", ephemeral=True, delete_after=4)
                return
            target = interaction.guild.get_member(int(discord_id))
            if not target:
                try:
                    target = await interaction.guild.fetch_member(int(discord_id))
                except Exception:
                    pass
            if not target:
                await interaction.response.send_message("Author not in server.", ephemeral=True, delete_after=4)
                return

            stories  = get_stories_by_discord_user(discord_id)
            ctc_ref  = ctc_view

            from features.stories.views.showcase_view import ShowcaseView

            class _ReturnAuthorView(ShowcaseView):
                def __init__(sv, stories, viewer, target):
                    # Override refresh_ui before super().__init__ calls it,
                    # so no auto-buttons get added at all
                    sv._ctc_return_ref = ctc_ref
                    super().__init__(stories, viewer, target, source="showcase")

                def refresh_ui(sv):
                    # Only show our single Return button — nothing else
                    sv.clear_items()
                    rb = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=0)
                    async def _back(i):
                        _full_refresh(sv._ctc_return_ref)
                        await i.response.edit_message(
                            embed=sv._ctc_return_ref._build_embed(), view=sv._ctc_return_ref
                        )
                    rb.callback = _back
                    sv.add_item(rb)

            view = _ReturnAuthorView(stories, interaction.user, target)
            await interaction.response.edit_message(embed=view.generate_bio_embed(), view=view)
            return

        # ── Character card ─────────────────────────────────────────────────────
        if value.startswith("char:"):
            char_id  = int(value.split(":")[1])
            ctc_ref  = ctc_view
            char_ref = self._char

            from database import get_character_by_id, is_favorite_character, get_user_id
            full = get_character_by_id(char_id)
            if not full:
                await interaction.response.send_message("Character not found.", ephemeral=True, delete_after=4)
                return
            full = dict(full)
            full.setdefault("story_title", char_ref.get("story_title"))
            full.setdefault("story_id",    char_ref.get("story_id"))
            full.setdefault("author",      char_ref.get("author"))

            from features.characters.views.char_search_view import CharSearchDetailView
            from features.characters.views.favorite_helpers import handle_fav_toggle
            from embeds.character_embeds import build_character_card

            class _CtcCharView(ui.View):
                """Minimal character detail: fav button + Return."""
                def __init__(cv, char, viewer):
                    super().__init__(timeout=300)
                    cv._char   = char
                    cv._viewer = viewer
                    cv._rebuild()

                async def interaction_check(cv, interaction: discord.Interaction) -> bool:
                    if interaction.user.id != cv._viewer.id:
                        await interaction.response.send_message(
                            "❌ This session belongs to someone else.",
                            ephemeral=True, delete_after=5
                        )
                        return False
                    return True

                def _rebuild(cv):
                    cv.clear_items()
                    uid   = get_user_id(str(cv._viewer.id))
                    faved = is_favorite_character(uid, cv._char["id"]) if uid else False

                    fav_btn = ui.Button(
                        label="✦ Unstar" if faved else "✦ Favorite",
                        style=discord.ButtonStyle.primary, row=0
                    )
                    async def _fav(i):
                        async def _refresh(ii):
                            cv._rebuild()
                            await ii.response.edit_message(
                                content=None,
                                embed=build_character_card(cv._char, viewer=cv._viewer),
                                view=cv
                            )
                        await handle_fav_toggle(i, cv._char, _refresh)
                    fav_btn.callback = _fav
                    cv.add_item(fav_btn)

                    ret = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=0)
                    async def _back(i):
                        _full_refresh(ctc_ref)
                        await i.response.edit_message(embed=ctc_ref._build_embed(), view=ctc_ref)
                    ret.callback = _back
                    cv.add_item(ret)

            view = _CtcCharView(full, interaction.user)
            embed = build_character_card(full, viewer=interaction.user)
            await interaction.response.edit_message(embed=embed, view=view)
            return

        # ── Fanart gallery ─────────────────────────────────────────────────────
        if value.startswith("fanart:"):
            char_id = int(value.split(":")[1])
            ctc_ref = ctc_view

            from database import get_fanart_by_character, get_fanart_comment_count
            from features.fanart.views.fanart_search_view import (
                SearchFanartDetailView, FanartSearchRosterView
            )

            fanarts = get_fanart_by_character(char_id)
            if not fanarts:
                await interaction.response.send_message("No fanart found.", ephemeral=True, delete_after=4)
                return

            dummy_roster = FanartSearchRosterView(
                fanarts=fanarts, viewer=interaction.user, tags=[], guild=interaction.guild
            )

            class _CtcFanartView(SearchFanartDetailView):
                def __init__(fv, fanarts, viewer):
                    super().__init__(
                        fanarts=fanarts, index=0, viewer=viewer,
                        roster=dummy_roster, return_page=0
                    )

                def _rebuild_ui(fv):
                    # Call parent to get the standard row-0 buttons (⬅️ 👍 💬 ➡️)
                    # but we need to intercept before it adds its own Return + dropdown.
                    # Easiest: build from scratch keeping only nav/like/comment buttons.
                    from database import get_user_id, user_has_liked_fanart

                    fv.clear_items()
                    f     = fv.current()
                    total = len(fv.fanarts)
                    uid   = get_user_id(str(fv.viewer.id))
                    liked = user_has_liked_fanart(uid, f["id"]) if uid else False

                    # ── Row 0: nav + like + comment + Return ─────────────────
                    prev_btn = ui.Button(
                        emoji="⬅️", style=discord.ButtonStyle.secondary,
                        row=0, disabled=(fv.index == 0)
                    )
                    prev_btn.callback = fv._prev
                    fv.add_item(prev_btn)

                    like_btn = ui.Button(
                        emoji="👍",
                        style=discord.ButtonStyle.success if liked else discord.ButtonStyle.secondary,
                        row=0
                    )
                    like_btn.callback = fv._like
                    fv.add_item(like_btn)

                    comment_btn = ui.Button(emoji="💬", style=discord.ButtonStyle.primary, row=0)
                    comment_btn.callback = fv._comment
                    fv.add_item(comment_btn)

                    ret = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=0)
                    async def _back(i):
                        _full_refresh(ctc_ref)
                        await i.response.edit_message(embed=ctc_ref._build_embed(), view=ctc_ref)
                    ret.callback = _back
                    fv.add_item(ret)

                    next_btn = ui.Button(
                        emoji="➡️", style=discord.ButtonStyle.secondary,
                        row=0, disabled=(fv.index >= total - 1)
                    )
                    next_btn.callback = fv._next
                    fv.add_item(next_btn)

                    # ── Row 1: comments-only dropdown ────────────────────────
                    n = get_fanart_comment_count(f["id"])
                    sel = ui.Select(
                        placeholder="💬 View Comments...",
                        options=[discord.SelectOption(
                            label=f"View Comments ({n})", emoji="💬", value="comments"
                        )],
                        row=1
                    )
                    async def _sel_cb(i):
                        from features.fanart.views.my_fanart_view import FanartCommentsView
                        nc = get_fanart_comment_count(fv.current()["id"])
                        if nc == 0:
                            await i.response.send_message("No comments yet!", ephemeral=True, delete_after=3)
                            return
                        cv = FanartCommentsView(fv.current(), fv, guild=i.guild)
                        await i.response.edit_message(embed=await cv.build_embed(), view=cv)
                    sel.callback = _sel_cb
                    fv.add_item(sel)

            view = _CtcFanartView(fanarts, interaction.user)
            await interaction.response.edit_message(embed=view.build_embed(), view=view)
            return


# ─────────────────────────────────────────────────────────────────────────────
# Shiny toggle
# ─────────────────────────────────────────────────────────────────────────────

class _ShinyToggleButton(ui.Button):
    def __init__(self, currently_shiny: bool, row: int):
        super().__init__(
            label="✦ View Normal" if currently_shiny else "✨ View Shiny",
            emoji="🌟", style=discord.ButtonStyle.primary, row=row,
        )
        self.currently_shiny = currently_shiny

    async def callback(self, interaction: discord.Interaction):
        view: CTCCardView = self.view  # type: ignore
        view._shiny_override = not self.currently_shiny
        view._refresh()
        await interaction.response.edit_message(embed=view._build_embed(), view=view)


# ─────────────────────────────────────────────────────────────────────────────
# Page nav
# ─────────────────────────────────────────────────────────────────────────────

class _PageButton(ui.Button):
    def __init__(self, emoji: str, direction: int, row: int):
        super().__init__(emoji=emoji, style=discord.ButtonStyle.secondary, row=row)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        view: CTCCardView = self.view  # type: ignore
        view.index = max(0, min(view.index + self.direction, len(view.cards) - 1))
        view._shiny_override = None
        view._refresh()
        await interaction.response.edit_message(embed=view._build_embed(), view=view)


class _PageCounter(ui.Button):
    def __init__(self, label: str, row: int):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, disabled=True, row=row)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


# ─────────────────────────────────────────────────────────────────────────────
# CTCCardView — base class shared by all card display contexts
# ─────────────────────────────────────────────────────────────────────────────

class CTCCardView(ui.View):

    def __init__(
        self,
        cards:        list[dict],
        viewer_uid:   int,
        *,
        viewer:       discord.Member | None = None,
        fav_ids:      set[int]   = None,   # back-compat, not used for shiny
        obtained_via: str | None = None,
        obtained_at:  str | None = None,
        index:        int        = 1,
        total:        int        = None,
        owned_count:  int | None = None,
        total_chars:  int | None = None,
        timeout:      int        = 300,
    ):
        super().__init__(timeout=timeout)
        self.cards           = cards
        self.viewer_uid      = viewer_uid
        self.viewer          = viewer
        self.obtained_via    = obtained_via
        self.obtained_at     = obtained_at
        self.index           = 0
        self.total           = total or len(cards)
        self.owned_count     = owned_count
        self.total_chars     = total_chars
        self._gallery        = len(cards) > 1
        self._shiny_override: bool | None = None
        self._refresh()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer_uid:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    def _is_shiny(self) -> bool:
        if self._shiny_override is not None:
            return self._shiny_override
        return bool(self.cards[self.index].get("is_shiny", 0))

    def _has_both(self) -> bool:
        return bool(self.cards[self.index].get("has_shiny_upgrade"))

    def _build_embed(self) -> discord.Embed:
        card = self.cards[self.index]
        via  = card.get("obtained_via", self.obtained_via)
        at   = card.get("obtained_at",  self.obtained_at)
        return _build_core_embed(
            char         = card,
            shiny        = self._is_shiny(),
            obtained_via = via,
            obtained_at  = at,
            index        = self.index + 1,
            total        = self.total,
            owned_count  = self.owned_count,
            total_chars  = self.total_chars,
        )

    def _refresh(self):
        self.clear_items()
        card   = self.cards[self.index]
        shiny  = self._is_shiny()
        viewer = self.viewer

        # Row 0: Behind the Scenes dropdown (needs a viewer member object)
        if viewer:
            self.add_item(_BehindTheScenesSelect(char=card, viewer=viewer, ctc_view=self, row=0))

        if self._has_both():
            self.add_item(_ShinyToggleButton(currently_shiny=shiny, row=0))

        # Row 1: gallery navigation
        if self._gallery:
            prev = _PageButton("⬅️", -1, row=1)
            prev.disabled = self.index == 0
            self.add_item(prev)
            self.add_item(_PageCounter(f"{self.index + 1} / {self.total}", row=1))
            nxt = _PageButton("➡️", +1, row=1)
            nxt.disabled = self.index >= len(self.cards) - 1
            self.add_item(nxt)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_ctc_card_embed(
    char:         dict,
    viewer_uid:   int,
    *,
    viewer:       discord.Member | None = None,
    shiny:        bool        = False,
    obtained_via: str | None  = None,
    obtained_at:  str | None  = None,
    index:        int         = 1,
    total:        int         = 1,
    owned_count:  int | None  = None,
    total_chars:  int | None  = None,
) -> tuple[discord.Embed, CTCCardView]:
    # Build a working copy so we don't mutate the caller's dict.
    # The `shiny` kwarg is the authoritative signal — it overrides is_shiny
    # in the char dict so the embed and toggle both reflect the same state.
    char_copy = {**char, "is_shiny": int(shiny)}
    view = CTCCardView(
        cards=[char_copy], viewer_uid=viewer_uid, viewer=viewer,
        obtained_via=obtained_via, obtained_at=obtained_at,
        index=index, total=total, owned_count=owned_count, total_chars=total_chars,
    )
    embed = _build_core_embed(
        char=char_copy, shiny=shiny,
        obtained_via=obtained_via, obtained_at=obtained_at,
        index=index, total=total, owned_count=owned_count, total_chars=total_chars,
    )
    return embed, view


def build_ctc_collection_view(
    cards:       list[dict],
    viewer_uid:  int,
    viewer:      discord.Member | None = None,
    fav_ids:     set[int]   = None,
    owned_count: int | None = None,
    total_chars: int | None = None,
) -> tuple[discord.Embed, CTCCardView]:
    view = CTCCardView(
        cards=cards, viewer_uid=viewer_uid, viewer=viewer,
        owned_count=owned_count, total_chars=total_chars, total=len(cards),
    )
    return view._build_embed(), view