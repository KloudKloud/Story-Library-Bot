"""
pvp/engine.py
Game engine — pure Python, no Discord dependency.
All tunable constants live at the top.
"""

import random
import copy

# ── Tunable constants ──────────────────────────────────────────────────────────
MAX_HP          = 10      # starting HP per player
MANA_PER_TURN   = 3       # mana each player gets at turn start
MAX_HAND_SIZE   = 7       # hand cap (can't draw above this)
STARTING_HAND   = 5       # cards dealt at game start
DECK_SIZE       = 30      # personal deck size (drawn with affinity bias)
AFFINITY_CHANCE = 0.70    # probability that a deal gives the preferred element
CHARACTER_CHOICES = 3     # how many character cards to choose from

from pvp.cards import ALL_CARDS, BY_ELEMENT, FIRE_CARDS, ICE_CARDS, LIGHTNING_CARDS


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fresh_player(name: str, affinity: str) -> dict:
    return {
        "name":        name,
        "affinity":    affinity,
        "hp":          MAX_HP,
        "max_hp":      MAX_HP,
        "mana":        MANA_PER_TURN,
        "max_mana":    MANA_PER_TURN,
        "hand":        [],          # list of card ids
        "deck":        [],          # remaining deck
        "discard":     [],          # discard pile
        "shield":      0,
        "burn_value":  0,           # damage taken at start of turn
        "burn_turns":  0,
        "freeze_turns":0,           # turns where card play is locked
        "stun_mana":   0,           # mana stolen next turn start
        "character":   None,        # character dict (cosmetic)
        "char_choices":None,        # 3 options shown during setup
        "drew_this_turn":   False,
        "discarded_this_turn": False,
        "played_this_turn":  [],
    }


def _build_deck(affinity: str) -> list:
    """Build a DECK_SIZE personal deck with AFFINITY_CHANCE bias toward the chosen element."""
    elements = ["fire", "ice", "lightning"]
    other    = [e for e in elements if e != affinity]
    deck     = []
    for _ in range(DECK_SIZE):
        if random.random() < AFFINITY_CHANCE:
            pool = BY_ELEMENT[affinity]
        else:
            pool = BY_ELEMENT[random.choice(other)]
        deck.append(random.choice(pool)["id"])
    random.shuffle(deck)
    return deck


def _load_characters() -> list:
    """Load characters from the SapheroBot DB. Falls back to placeholders."""
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from database import get_all_characters, get_character_by_id
        all_chars = get_all_characters()
        if len(all_chars) >= CHARACTER_CHOICES:
            sample = random.sample(all_chars, CHARACTER_CHOICES)
            return [get_character_by_id(c["id"]) or c for c in sample]
    except Exception:
        pass
    # Placeholder fallback
    placeholders = ["Arion","Sylvara","Dusk","Ember","Zephyr","Nova","Riven","Cass"]
    chosen = random.sample(placeholders, CHARACTER_CHOICES)
    return [{"id": i, "name": n, "personality": "A mysterious fighter.",
              "image_url": None, "gender": "Unknown", "lore": None}
            for i, n in enumerate(chosen)]


# ── Main engine ────────────────────────────────────────────────────────────────

class GameEngine:

    def __init__(self):
        self.state: dict | None = None

    # ── Setup ─────────────────────────────────────────────────────────────────

    def new_game(self, p1_name: str, p1_affinity: str,
                       p2_name: str, p2_affinity: str) -> dict:
        p0 = _fresh_player(p1_name, p1_affinity)
        p1 = _fresh_player(p2_name, p2_affinity)

        # Build personal decks
        p0["deck"] = _build_deck(p1_affinity)  # NOTE: intentionally cross — makes
        p1["deck"] = _build_deck(p2_affinity)  # each player feel the other's element
        p0["deck"] = _build_deck(p1_affinity)
        p0["deck"] = _build_deck(p0["affinity"])
        p1["deck"] = _build_deck(p1["affinity"])

        # Character choices
        p0["char_choices"] = _load_characters()
        p1["char_choices"] = _load_characters()

        self.state = {
            "phase":          "char_select",   # char_select → battle → end
            "char_select_turn": 0,             # which player is picking
            "players":        [p0, p1],
            "current_turn":   0,               # 0 or 1
            "turn_number":    1,
            "log":            ["⚔️  A new battle begins!",
                               f"🔥/❄️/⚡  {p1_name} chose {p1_affinity}.",
                               f"🔥/❄️/⚡  {p2_name} chose {p2_affinity}."],
            "winner":         None,
        }
        return self.get_state()

    def select_character(self, player_idx: int, char_index: int) -> dict:
        """Player picks one of the three character choices."""
        s = self.state
        p = s["players"][player_idx]
        choices = p["char_choices"]
        if char_index < 0 or char_index >= len(choices):
            return self._err("Invalid character index.")
        p["character"] = choices[char_index]
        p["char_choices"] = None
        self._log(f"⚔️  {p['name']} chose their character!")

        # Advance character-select phase
        if s["char_select_turn"] == 0:
            s["char_select_turn"] = 1
        else:
            # Both players picked — start battle
            self._start_battle()
        return self.get_state()

    def _start_battle(self):
        s = self.state
        s["phase"] = "battle"
        for p in s["players"]:
            for _ in range(STARTING_HAND):
                self._draw_one(p)
        self._log("🃏  Opening hands dealt. Battle begins!")
        self._begin_turn()

    # ── Turn flow ─────────────────────────────────────────────────────────────

    def _begin_turn(self):
        s = self.state
        p = s["players"][s["current_turn"]]
        msgs = []

        # Apply burn damage
        if p["burn_turns"] > 0:
            dmg = p["burn_value"]
            self._deal_damage_to(p, dmg)
            p["burn_turns"] -= 1
            if p["burn_turns"] == 0:
                p["burn_value"] = 0
            msgs.append(f"🔥 {p['name']} takes {dmg} burn damage!")

        # Apply stun (lose mana)
        base_mana = MANA_PER_TURN
        stolen    = p["stun_mana"]
        p["stun_mana"] = 0
        p["mana"] = max(0, base_mana - stolen)
        if stolen:
            msgs.append(f"⚡ {p['name']} is stunned — loses {stolen} mana!")
        else:
            p["mana"] = base_mana

        # Reset per-turn flags
        p["drew_this_turn"]      = False
        p["discarded_this_turn"] = False
        p["played_this_turn"]    = []

        for m in msgs:
            self._log(m)

        self._check_death()

    def end_turn(self, player_idx: int) -> dict:
        s = self.state
        if s["phase"] != "battle":
            return self._err("Not in battle phase.")
        if player_idx != s["current_turn"]:
            return self._err("Not your turn.")

        p = s["players"][player_idx]

        # Tick down freeze
        if p["freeze_turns"] > 0:
            p["freeze_turns"] -= 1

        self._log(f"🔄  {p['name']} ends their turn.")
        s["current_turn"] = 1 - player_idx
        s["turn_number"]  += 1
        self._begin_turn()
        return self.get_state()

    # ── Player actions ────────────────────────────────────────────────────────

    def draw_card(self, player_idx: int) -> dict:
        s = self.state
        if s["phase"] != "battle":
            return self._err("Not in battle.")
        if player_idx != s["current_turn"]:
            return self._err("Not your turn.")
        p = s["players"][player_idx]
        if p["drew_this_turn"]:
            return self._err("Already drew this turn.")
        if len(p["hand"]) >= MAX_HAND_SIZE:
            return self._err(f"Hand is full ({MAX_HAND_SIZE} cards max).")
        self._draw_one(p)
        p["drew_this_turn"] = True
        self._log(f"🃏  {p['name']} draws a card.")
        return self.get_state()

    def discard_card(self, player_idx: int, card_id: str) -> dict:
        s = self.state
        if s["phase"] != "battle":
            return self._err("Not in battle.")
        if player_idx != s["current_turn"]:
            return self._err("Not your turn.")
        p = s["players"][player_idx]
        if p["discarded_this_turn"]:
            return self._err("Already discarded this turn.")
        if card_id not in p["hand"]:
            return self._err("Card not in hand.")
        p["hand"].remove(card_id)
        p["discard"].append(card_id)
        p["discarded_this_turn"] = True
        cname = ALL_CARDS.get(card_id, {}).get("name", card_id)
        self._log(f"🗑️  {p['name']} discards {cname}.")
        return self.get_state()

    def play_card(self, player_idx: int, card_id: str) -> dict:
        s = self.state
        if s["phase"] != "battle":
            return self._err("Not in battle.")
        if player_idx != s["current_turn"]:
            return self._err("Not your turn.")
        p   = s["players"][player_idx]
        opp = s["players"][1 - player_idx]

        if card_id not in p["hand"]:
            return self._err("Card not in hand.")

        if p["freeze_turns"] > 0:
            return self._err(f"You are frozen for {p['freeze_turns']} more turn(s)!")

        card = ALL_CARDS.get(card_id)
        if not card:
            return self._err("Unknown card.")

        cost = card["cost"]
        if p["mana"] < cost:
            return self._err(f"Not enough mana. Need {cost}, have {p['mana']}.")

        # Pay cost
        p["mana"] -= cost
        p["hand"].remove(card_id)
        p["discard"].append(card_id)
        p["played_this_turn"].append(card_id)

        self._log(f"▶️  {p['name']} plays **{card['name']}** ({card['element']}, {cost} mana)")

        # Apply effects
        msgs = self._apply_effects(p, opp, card["effects"])
        for m in msgs:
            self._log(f"   {m}")

        self._check_death()
        return self.get_state()

    # ── Effect resolution ─────────────────────────────────────────────────────

    def _apply_effects(self, actor: dict, opp: dict, effects: list) -> list[str]:
        msgs = []
        for eff in effects:
            t = eff["type"]

            if t == "damage":
                dmg  = eff["value"]
                real = self._deal_damage_to(opp, dmg)
                if real < dmg:
                    msgs.append(f"💥 {dmg} damage → {opp['name']} ({real} after shield). {opp['name']}: {opp['hp']} HP")
                else:
                    msgs.append(f"💥 {dmg} damage to {opp['name']}. {opp['name']}: {opp['hp']} HP")

            elif t == "heal":
                v = eff["value"]
                before = actor["hp"]
                actor["hp"] = min(actor["max_hp"], actor["hp"] + v)
                healed = actor["hp"] - before
                msgs.append(f"💚 Healed {healed} HP. {actor['name']}: {actor['hp']} HP")

            elif t == "shield":
                v = eff["value"]
                actor["shield"] += v
                msgs.append(f"🛡️ Gained {v} shield. Total: {actor['shield']}")

            elif t == "burn":
                v = eff["value"]
                d = eff.get("duration", 2)
                opp["burn_value"]  = max(opp["burn_value"], v)
                opp["burn_turns"] += d
                msgs.append(f"🔥 {opp['name']} is burning! {v} dmg/turn for {d} turns.")

            elif t == "freeze":
                d = eff.get("duration", 1)
                opp["freeze_turns"] = max(opp["freeze_turns"], d)
                msgs.append(f"❄️  {opp['name']} is frozen for {d} turn(s)! Can't play cards.")

            elif t == "stun":
                v = eff["value"]
                opp["stun_mana"] += v
                msgs.append(f"⚡ {opp['name']} will lose {v} mana next turn!")

            elif t == "draw_cards":
                v = eff["value"]
                drawn = 0
                for _ in range(v):
                    if len(actor["hand"]) < MAX_HAND_SIZE:
                        self._draw_one(actor)
                        drawn += 1
                msgs.append(f"🃏 Drew {drawn} card(s).")

            elif t == "discard_opponent":
                v = eff["value"]
                discarded = 0
                for _ in range(v):
                    if opp["hand"]:
                        cid = random.choice(opp["hand"])
                        opp["hand"].remove(cid)
                        opp["discard"].append(cid)
                        discarded += 1
                msgs.append(f"🗑️  {opp['name']} discards {discarded} card(s) at random!")

            elif t == "energize":
                v = eff["value"]
                actor["mana"] += v
                msgs.append(f"⚡ Gained {v} bonus mana! ({actor['mana']} total)")

            elif t == "drain":
                v   = eff["value"]
                real = self._deal_damage_to(opp, v)
                heal = max(1, real // 2)
                actor["hp"] = min(actor["max_hp"], actor["hp"] + heal)
                msgs.append(f"🩸 Drained {real} from {opp['name']}, healed {heal}. You: {actor['hp']} HP")

        return msgs

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _deal_damage_to(self, target: dict, amount: int) -> int:
        """Apply damage through shield. Returns actual HP damage dealt."""
        if target["shield"] > 0:
            blocked = min(target["shield"], amount)
            target["shield"] -= blocked
            amount -= blocked
        if amount > 0:
            target["hp"] -= amount
        return amount

    def _draw_one(self, p: dict):
        if not p["deck"]:
            # Shuffle discard back in
            if p["discard"]:
                p["deck"] = p["discard"][:]
                random.shuffle(p["deck"])
                p["discard"] = []
            else:
                return  # totally empty
        if p["deck"]:
            cid = p["deck"].pop()
            p["hand"].append(cid)

    def _check_death(self):
        s = self.state
        for i, p in enumerate(s["players"]):
            if p["hp"] <= 0:
                p["hp"] = 0
                opp = s["players"][1 - i]
                s["phase"]  = "end"
                s["winner"] = 1 - i
                self._log(f"💀 {p['name']} has fallen!")
                self._log(f"🏆 {opp['name']} wins!")

    def _log(self, msg: str):
        self.state["log"].append(msg)
        # Keep log manageable
        if len(self.state["log"]) > 60:
            self.state["log"] = self.state["log"][-60:]

    def _err(self, msg: str) -> dict:
        return {"error": msg, "state": self.get_state()}

    # ── State serialisation ───────────────────────────────────────────────────

    def get_state(self) -> dict:
        """Return a JSON-safe snapshot of the game state."""
        if not self.state:
            return {"phase": "idle"}
        s = copy.deepcopy(self.state)
        # Hydrate hand card IDs → full card dicts for the frontend
        for p in s["players"]:
            p["hand_cards"] = [ALL_CARDS[cid] for cid in p["hand"] if cid in ALL_CARDS]
        return s
