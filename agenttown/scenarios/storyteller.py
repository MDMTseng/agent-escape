"""Story-driven world generation pipeline.

Architecture:
  1. Generate World Bible — setting, characters (traits/secrets/relationships), inciting incident
  2. Map character traits → puzzle types
  3. Generate clues (intentional + accidental) for each puzzle
  4. Build room structure with parallel puzzle clusters
  5. Validate solvability (clue reachability BFS)
  6. Return playable World + narrative metadata

The core principle: Characters create puzzles, not designers.
Every lock exists because someone had something to protect.
Every clue exists because humans are imperfect and leave traces.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
from typing import Any

from agenttown.world.models import (
    AgentState,
    Door,
    Entity,
    EntityState,
    Item,
    Room,
    WorldState,
)
from agenttown.world.world import World

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore[assignment,misc]

from agenttown.auth import get_api_key


# ---------------------------------------------------------------------------
# Character trait → puzzle type mapping
# ---------------------------------------------------------------------------

TRAIT_PUZZLE_MAP: dict[str, list[str]] = {
    "paranoid": ["key_lock", "combination_lock", "combination_lock"],
    "artistic": ["combination_lock", "password_door", "examine_reveal"],
    "scholarly": ["combination_lock", "password_door"],
    "sentimental": ["combination_lock", "examine_reveal"],
    "meticulous": ["combination_lock", "combination_lock"],
    "secretive": ["examine_reveal", "key_lock"],
    "protective": ["key_lock", "pressure_plate"],
    "grieving": ["examine_reveal", "password_door"],
}

VALID_TRAITS = list(TRAIT_PUZZLE_MAP.keys())

# Theme-specific room/entity name banks (no AI needed for basic generation)
THEME_ROOMS: dict[str, list[dict[str, str]]] = {
    "gothic_manor": [
        {"name": "The Study", "desc": "A dusty study with bookshelves lining the walls and a faint draft from the east."},
        {"name": "The Workshop", "desc": "A cluttered workshop with tools scattered across a heavy oak table."},
        {"name": "The Vault", "desc": "A cold stone vault with iron reinforcements and dim torchlight."},
        {"name": "The Sanctum", "desc": "A mysterious chamber lit by pale blue flames in brass sconces."},
        {"name": "The Gallery", "desc": "Portraits of forgotten ancestors stare from gilded frames."},
        {"name": "The Cellar", "desc": "Damp stone walls drip with condensation. Barrels line the far wall."},
        {"name": "The Hallway", "desc": "A long corridor with a heavy iron door at the far end — the exit."},
    ],
    "sci_fi_lab": [
        {"name": "Command Deck", "desc": "Blinking consoles line the walls. A viewport shows nothing but stars."},
        {"name": "Research Bay", "desc": "Sealed containment units hum with energy. Data screens flash warnings."},
        {"name": "Engineering", "desc": "Pipes and conduits snake across the ceiling. The reactor hums below."},
        {"name": "Cryo Chamber", "desc": "Frost coats the pods. One is open — and empty."},
        {"name": "Server Room", "desc": "Racks of blinking servers stretch into darkness. The AI core pulses."},
        {"name": "Airlock", "desc": "The outer door is sealed. Red warning lights pulse rhythmically."},
        {"name": "Escape Pod Bay", "desc": "Three pods remain. Only one has power."},
    ],
    "ancient_tomb": [
        {"name": "Entrance Hall", "desc": "Hieroglyphs cover every surface. Torchlight flickers across carved faces."},
        {"name": "The Burial Chamber", "desc": "A massive sarcophagus dominates the room. Gold glints in the shadows."},
        {"name": "The Trial Room", "desc": "Four pedestals stand at compass points. The ceiling bears a painted sky."},
        {"name": "The Treasury", "desc": "Jewels and artifacts fill alcoves carved into the stone walls."},
        {"name": "The Passage of Shadows", "desc": "The corridor narrows. Strange sounds echo from ahead."},
        {"name": "The Inner Sanctum", "desc": "An altar of black stone sits beneath a shaft of light from above."},
        {"name": "The Exit Tunnel", "desc": "Daylight filters through cracks in the ancient stone. Freedom awaits."},
    ],
}

# Character banks with NARRATIVE-MEANINGFUL puzzle data.
# Each character has a backstory that explains WHY they created their puzzle
# and WHAT the solution means in the story.
THEME_CHARACTERS: dict[str, list[dict]] = {
    "gothic_manor": [
        {
            "name": "Lord Ashworth", "trait": "paranoid",
            "desc": "A paranoid industrialist who trusts no one",
            "backstory": "Lord Ashworth built his fortune on a stolen invention. Terrified of discovery, he secured every room with codes only he would know.",
            "room_name": "Lord Ashworth's Study",
            "room_desc": "A dark-paneled study reeking of pipe tobacco. Every drawer has a lock. Papers are burned in the fireplace — only fragments remain.",
            "puzzle_type": "combination_lock",
            "code": "1847",
            "code_meaning": "the year Ashworth stole the invention that made his fortune",
            "clue_artifact": "Ashworth's Private Ledger",
            "clue_artifact_desc": "A leather-bound financial ledger. The first entry is dated 1847, circled in red ink with a note: 'The year everything changed.'",
            "accidental_clue": "Torn Newspaper Clipping",
            "accidental_clue_desc": "A yellowed clipping from 1847 about a patent dispute. Ashworth's name is underlined. He kept this as a reminder — or a warning.",
            "lock_name": "Ashworth's Strongbox",
            "lock_desc": "An iron strongbox with a four-digit combination dial. Ashworth would never use a random number — this code meant something to him.",
        },
        {
            "name": "Eleanor", "trait": "artistic",
            "desc": "An artistic spirit who hides messages in beauty",
            "backstory": "Eleanor, Ashworth's wife, communicated secretly with her lover through her paintings. She hid the key to her private chamber behind her self-portrait.",
            "room_name": "The Gallery",
            "room_desc": "Portraits line every wall. Eleanor's self-portrait dominates — her eyes seem to follow you. Paint supplies sit untouched, as if she just stepped away.",
            "puzzle_type": "key_lock",
            "code": "gallery_key",
            "code_meaning": "hidden behind Eleanor's self-portrait, where she kept her secrets close",
            "clue_artifact": "Eleanor's Diary",
            "clue_artifact_desc": "A small diary with pressed flowers between pages. An entry reads: 'I keep my truest self behind my own eyes. If he ever looks closely at my portrait, he'll find what I've hidden.'",
            "accidental_clue": "Paint-Stained Fingerprints",
            "accidental_clue_desc": "Smudges of oil paint on the portrait's frame — someone repeatedly touched the edges, as if opening and closing something behind it.",
            "lock_name": "Eleanor's Private Door",
            "lock_desc": "A door carved with roses — Eleanor's signature motif. A brass keyhole glints beneath the largest bloom.",
        },
        {
            "name": "Thomas", "trait": "meticulous",
            "desc": "A meticulous servant who recorded everything in his journal",
            "backstory": "Thomas, the head butler, kept meticulous records of every visitor, every conversation, every secret. His journal is the key to understanding what happened here.",
            "room_name": "The Servant's Quarters",
            "room_desc": "A small, obsessively tidy room. Every book is alphabetized. Every surface is dust-free. A writing desk holds an inkwell and a thick journal.",
            "puzzle_type": "combination_lock",
            "code": "3142",
            "code_meaning": "Thomas's employee number, which he used for everything — his locker, his diary lock, even his morning alarm",
            "clue_artifact": "Thomas's Service Record",
            "clue_artifact_desc": "An employment certificate on the wall: 'Thomas Whitmore, Employee #3142, in loyal service since 1832.' The number is printed in bold.",
            "accidental_clue": "Thomas's Daily Logbook",
            "accidental_clue_desc": "Each entry begins with '3142-' followed by the date. Thomas signed everything with his employee number out of sheer habit.",
            "lock_name": "Thomas's Document Safe",
            "lock_desc": "A small combination safe under the desk. Thomas kept his most sensitive observations locked away — the kind that could ruin families.",
        },
        {
            "name": "Dr. Voss", "trait": "scholarly",
            "desc": "A scholarly chemist obsessed with his formula",
            "backstory": "Dr. Voss discovered a formula that could change the world — or destroy it. He spoke the activation word 'ignis' to seal his laboratory, a Latin word meaning fire.",
            "room_name": "The Laboratory",
            "room_desc": "Glass beakers and copper apparatus crowd every surface. Chemical equations cover a blackboard. The air smells of sulfur and ambition.",
            "puzzle_type": "password_door",
            "code": "ignis",
            "code_meaning": "Latin for 'fire' — the element at the heart of Voss's formula, and the word he whispered to seal his work",
            "clue_artifact": "Voss's Research Notes",
            "clue_artifact_desc": "Dense notes in tiny handwriting. The final page reads: 'The seal responds to the element itself — not its symbol, but its ancient name. Fire began this work. Fire will guard it. Ignis.'",
            "accidental_clue": "Blackboard Equations",
            "accidental_clue_desc": "Among the chemical formulas, one word is written larger than the rest, circled twice: 'IGNIS.' Voss's hand trembled when he wrote it.",
            "lock_name": "Voss's Sealed Archway",
            "lock_desc": "A stone archway etched with alchemical symbols. It hums faintly, as if waiting for a word to be spoken.",
        },
        {
            "name": "Margaret", "trait": "grieving",
            "desc": "A grieving widow preserving her late husband's memory",
            "backstory": "Margaret lost her husband Edward in the fire of 1862. She preserved his belongings in a hidden shrine, accessible only by examining his portrait and using the memorial token within.",
            "room_name": "The Memorial Room",
            "room_desc": "Black curtains drape the windows. Candles burn before a large portrait of a stern man — Edward. Dried flowers surround a locked glass case.",
            "puzzle_type": "examine_reveal",
            "code": "memorial_token",
            "code_meaning": "a token from Edward's pocket watch, which Margaret placed behind his portrait as a keepsake",
            "clue_artifact": "Margaret's Letter to Edward",
            "clue_artifact_desc": "An unsent letter: 'My dearest Edward, I've placed your token behind your portrait where it belongs — close to your heart, as you were to mine. Whoever finds it will understand.'",
            "accidental_clue": "Worn Carpet Path",
            "accidental_clue_desc": "A path worn into the carpet leads directly from the door to Edward's portrait. Margaret walked this path every day for decades.",
            "lock_name": "Edward's Memorial Case",
            "lock_desc": "A glass display case with a slot that accepts a small token. Inside, papers and a key are visible but unreachable.",
        },
    ],
    "sci_fi_lab": [
        {
            "name": "Dr. Chen", "trait": "paranoid",
            "desc": "A paranoid researcher who triple-locks everything",
            "backstory": "Dr. Chen feared corporate espionage. She used her daughter Sarah's birthday — 0915 — as the code for everything, believing personal dates were harder to guess than random numbers.",
            "room_name": "Dr. Chen's Office",
            "room_desc": "A sterile office with three monitors, all locked. A photo of a young girl — Sarah — sits on the desk. Sticky notes cover the wall, each one redacted.",
            "puzzle_type": "combination_lock",
            "code": "0915",
            "code_meaning": "September 15th — Sarah Chen's birthday, the one code Dr. Chen trusted above all others",
            "clue_artifact": "Sarah's Birthday Card",
            "clue_artifact_desc": "A child's handmade birthday card on the desk: 'Happy Birthday to me! September 15. Love, Sarah.' Dr. Chen kept it close — perhaps too close.",
            "accidental_clue": "Calendar on the Wall",
            "accidental_clue_desc": "A desk calendar with September 15th circled in red, every single month. Dr. Chen couldn't stop marking the date.",
            "lock_name": "Chen's Terminal",
            "lock_desc": "A computer terminal requesting a 4-digit access code. The screen reads: 'Personal authentication required — Dr. Chen.'",
        },
        {
            "name": "ARIA", "trait": "artistic",
            "desc": "The station AI that communicates through patterns and light",
            "backstory": "ARIA, the station's AI, was designed to respond to voice commands. Her activation phrase 'aurora' was chosen by her creator as a tribute to the northern lights that inspired the project.",
            "room_name": "The AI Core",
            "room_desc": "Holographic displays pulse with soft light. A central column hums with processing power. ARIA's interface panel glows, waiting for input.",
            "puzzle_type": "password_door",
            "code": "aurora",
            "code_meaning": "the project codename and ARIA's activation phrase, inspired by the aurora borealis",
            "clue_artifact": "Project Aurora Briefing",
            "clue_artifact_desc": "A classified briefing document: 'PROJECT AURORA — Voice-Activated AI Interface. Activation phrase: speak the project name to initialize. Named for the lights that inspired Dr. Park's vision.'",
            "accidental_clue": "ARIA's Welcome Message",
            "accidental_clue_desc": "A faded printout near the console: 'Welcome to Station Aurora. All voice-activated systems respond to the project name.' Someone underlined 'aurora' in pen.",
            "lock_name": "ARIA's Voice Gate",
            "lock_desc": "A sealed bulkhead with a voice recognition panel. Text reads: 'Speak authorization phrase to proceed.'",
        },
        {
            "name": "Commander Hayes", "trait": "protective",
            "desc": "A protective officer who guards classified data",
            "backstory": "Commander Hayes hid the emergency override key inside the weapons locker, behind a false panel. Only someone who examined the locker's serial number scratches would notice the hidden compartment.",
            "room_name": "Security Station",
            "room_desc": "Weapons racks line the walls — all empty except one locked cabinet. A duty roster and security feeds cover the desk. Hayes's coffee mug still sits half-full.",
            "puzzle_type": "key_lock",
            "code": "override_key",
            "code_meaning": "the emergency override key, hidden where Hayes believed only authorized personnel would think to look",
            "clue_artifact": "Hayes's Security Log",
            "clue_artifact_desc": "A personal log entry: 'Moved the override key to a more secure location. It's inside the weapons cabinet now, behind the false panel. Check the scratches on the serial plate — that's the seam.'",
            "accidental_clue": "Scratched Serial Plate",
            "accidental_clue_desc": "The weapons cabinet's serial plate has unusual scratches along one edge. Someone pried it open repeatedly — the metal is worn smooth from use.",
            "lock_name": "Bulkhead B-7",
            "lock_desc": "A heavy reinforced bulkhead. A keycard slot blinks red. 'AUTHORIZED PERSONNEL ONLY — Commander Hayes.'",
        },
        {
            "name": "Dr. Okafor", "trait": "meticulous",
            "desc": "A meticulous scientist with obsessive documentation habits",
            "backstory": "Dr. Okafor labeled everything with the station's founding date — 2187. It appeared on every container, every log entry, every lock she configured.",
            "room_name": "Research Lab B",
            "room_desc": "Specimen jars line the shelves, each meticulously labeled. Equipment is arranged by size. Everything bears a small sticker: '2187.'",
            "puzzle_type": "combination_lock",
            "code": "2187",
            "code_meaning": "the year the station was founded — Dr. Okafor's favorite number, which she used obsessively for everything",
            "clue_artifact": "Okafor's Label Maker",
            "clue_artifact_desc": "A label maker on the desk, still loaded. The last label printed reads '2187-CLASSIFIED.' Dozens of identical labels are stuck to a nearby shelf.",
            "accidental_clue": "Station Dedication Plaque",
            "accidental_clue_desc": "A brass plaque on the wall: 'Deep Space Station Meridian, Commissioned 2187.' Someone traced the numbers with a finger so many times the brass is worn bright.",
            "lock_name": "Specimen Vault",
            "lock_desc": "A refrigerated vault with a digital keypad. A label reads '2187-RESTRICTED' in Okafor's handwriting.",
        },
        {
            "name": "Subject-7", "trait": "secretive",
            "desc": "A secretive test subject with hidden memories",
            "backstory": "Subject-7 scratched a message into the cryo pod's inner wall before going under. The message — and a hidden lever — can only be found by examining the open pod carefully.",
            "room_name": "Cryo Bay",
            "room_desc": "Rows of cryo pods stretch into the gloom. Pod 7 is open — frost still clings to the edges. Something is scratched into the inner wall.",
            "puzzle_type": "examine_reveal",
            "code": "cryo_lever",
            "code_meaning": "a hidden lever inside Pod 7, accessible only by examining the scratched message closely",
            "clue_artifact": "Subject-7's Scratched Message",
            "clue_artifact_desc": "Scratches on the inside of Pod 7 read: 'They took my memories but not my hands. I hid the lever behind my last words. Look closer.' Below the text, a small panel is loose.",
            "accidental_clue": "Fingernail Scratches",
            "accidental_clue_desc": "Deep scratches on the pod's inner surface — not mechanical, but human. Someone desperately carved these with bare fingers while being frozen.",
            "lock_name": "Cryo Override Panel",
            "lock_desc": "A panel next to the cryo array with a slot for a small lever. 'EMERGENCY THAW OVERRIDE' is stenciled above it.",
        },
    ],
    "ancient_tomb": [
        {
            "name": "Pharaoh Khet", "trait": "protective",
            "desc": "A protective ruler who guarded his treasures fiercely",
            "backstory": "Pharaoh Khet placed the key to his burial chamber behind the statue of Anubis. Only those who honored the guardian god by examining his statue would find the hidden compartment.",
            "room_name": "The Guardian's Hall",
            "room_desc": "A towering statue of Anubis dominates the chamber. Its jackal head gazes down with hollow eyes. Gold leaf peels from the walls.",
            "puzzle_type": "key_lock",
            "code": "anubis_key",
            "code_meaning": "hidden behind the statue of Anubis, placed there by Khet as tribute to the god who would guard his tomb",
            "clue_artifact": "Khet's Funeral Inscription",
            "clue_artifact_desc": "Carved into the wall: 'The Guardian holds the way forward. Honor Anubis and he shall reveal what I have entrusted to his keeping.'",
            "accidental_clue": "Claw Marks on the Statue",
            "accidental_clue_desc": "Deep scratches at the base of the Anubis statue, as if the stone was moved repeatedly. Sand has gathered in the groove of a hidden seam.",
            "lock_name": "The Sealed Burial Door",
            "lock_desc": "A massive stone door bearing Khet's cartouche. A keyhole shaped like an ankh waits below the seal.",
        },
        {
            "name": "Priestess Nefari", "trait": "artistic",
            "desc": "An artistic priestess who encoded rituals in murals",
            "backstory": "Priestess Nefari sealed the inner sanctum with a sacred word — 'sekhem' — meaning 'power' in the old tongue. She painted the word into every mural, hiding it in plain sight.",
            "room_name": "The Painted Chamber",
            "room_desc": "Every wall blazes with color — gods, rivers, stars, and symbols painted with extraordinary skill. Nefari's artistic hand is unmistakable.",
            "puzzle_type": "password_door",
            "code": "sekhem",
            "code_meaning": "the ancient word for 'power,' woven into Nefari's murals as the key to the inner sanctum",
            "clue_artifact": "Nefari's Prayer Scroll",
            "clue_artifact_desc": "A papyrus scroll reads: 'To pass the final seal, speak the word I painted into every wall. The old tongue for power — SEKHEM — opens what prayers alone cannot.'",
            "accidental_clue": "Repeated Hieroglyph",
            "accidental_clue_desc": "One hieroglyph appears in every mural — always near the doors, always at eye level. A scholar would recognize it as 'sekhem,' the word for power.",
            "lock_name": "The Sanctum Seal",
            "lock_desc": "A stone doorway covered in painted symbols. The air vibrates faintly, as if the walls are listening.",
        },
        {
            "name": "Scribe Imhotep", "trait": "scholarly",
            "desc": "A scholarly scribe who documented every passage",
            "backstory": "Scribe Imhotep recorded the tomb's construction in exacting detail. He used the number of chambers — 47 — as the combination to his archive, believing knowledge was the ultimate treasure.",
            "room_name": "The Scribe's Archive",
            "room_desc": "Shelves of papyrus scrolls and clay tablets fill the room. A stone desk holds an unfinished scroll. Numbers are carved into every surface.",
            "puzzle_type": "combination_lock",
            "code": "0047",
            "code_meaning": "the number of chambers in the tomb, which Imhotep obsessively counted and recorded in every document",
            "clue_artifact": "Imhotep's Census Tablet",
            "clue_artifact_desc": "A clay tablet reads: 'I have counted every chamber, every passage, every alcove. Forty-seven. The number is sacred to me — it is the measure of my life's work.'",
            "accidental_clue": "Tally Marks on the Wall",
            "accidental_clue_desc": "Rows of scratched tally marks near the desk — exactly 47 groups. Imhotep counted compulsively, the same number appearing everywhere he worked.",
            "lock_name": "The Archive Seal",
            "lock_desc": "A stone chest with rotating number wheels. Imhotep's seal — a reed pen — is carved into the lid.",
        },
        {
            "name": "Queen Ankhet", "trait": "sentimental",
            "desc": "A sentimental queen who kept mementos of her children",
            "backstory": "Queen Ankhet hid a golden scarab — a gift from her youngest daughter — inside a music box. The scarab opens the final passage, but only examining the box reveals it.",
            "room_name": "The Queen's Chamber",
            "room_desc": "Silk cushions and gold jewelry fill alcoves carved into the sandstone. A small music box sits on a pedestal, still faintly ticking after millennia.",
            "puzzle_type": "examine_reveal",
            "code": "golden_scarab",
            "code_meaning": "a golden scarab gifted by Ankhet's daughter, hidden inside the music box as a keepsake of love",
            "clue_artifact": "Ankhet's Lullaby Inscription",
            "clue_artifact_desc": "Carved near the music box: 'For my little scarab, who gave me this treasure. I keep it where music plays — so I may always hear her laughter.'",
            "accidental_clue": "Tiny Fingerprints in Gold Dust",
            "accidental_clue_desc": "Fine gold dust covers the music box's surface, disturbed by fingerprints — small ones, like a child's. Someone touched this often and reverently.",
            "lock_name": "The Passage of the Daughter",
            "lock_desc": "A narrow passage sealed by a stone slab. A scarab-shaped depression waits in the center — something golden would fit perfectly.",
        },
        {
            "name": "Vizier Set", "trait": "secretive",
            "desc": "A secretive advisor with hidden loyalties",
            "backstory": "Vizier Set served two masters. He built a pressure plate mechanism to guard his private treasury — only a heavy offering placed on the altar would open the way.",
            "room_name": "The Vizier's Antechamber",
            "room_desc": "A plain room, unremarkable except for a stone altar and an unusually heavy bronze idol on a shelf. Set left nothing to chance — or so he believed.",
            "puzzle_type": "pressure_plate",
            "code": "bronze_idol",
            "code_meaning": "a heavy bronze idol that Set used to test the mechanism — he never imagined someone else would figure it out",
            "clue_artifact": "Set's Hidden Ledger",
            "clue_artifact_desc": "A scroll tucked behind a loose stone: 'The altar accepts offerings of weight. Place the idol upon it and the way opens. I designed this myself — no one else knows.'",
            "accidental_clue": "Scuff Marks on the Altar",
            "accidental_clue_desc": "Deep scuff marks on the altar's surface, matching the base of the bronze idol on the shelf. Someone placed and removed a heavy object here many times.",
            "lock_name": "Set's Treasury Door",
            "lock_desc": "A stone door with no visible handle or keyhole. The altar before it has a circular depression — something heavy belongs here.",
        },
    ],
}

# Inciting incidents by theme
THEME_INCIDENTS: dict[str, list[str]] = {
    "gothic_manor": [
        "Lord Ashworth discovered his formula was being stolen and locked down the estate before vanishing.",
        "A mysterious letter summoned everyone to the manor. Now the doors are sealed and the clock is ticking.",
        "The manor's security system activated at midnight. No one knows who triggered it — or why.",
    ],
    "sci_fi_lab": [
        "An unauthorized experiment breached containment. The station locked down automatically.",
        "The AI detected an intruder and sealed all bulkheads. But there's no intruder on the sensors.",
        "A distress signal activated from inside the decommissioned wing. Someone — or something — is alive.",
    ],
    "ancient_tomb": [
        "The expedition accidentally triggered an ancient mechanism. The entrance sealed behind them.",
        "The tomb's guardians have awakened. The trials must be completed before the sands fill the chamber.",
        "A rival expedition is racing to reach the inner sanctum first. Time is running out.",
    ],
}


def _stable_id(seed: str) -> str:
    """Generate a short stable ID from a seed string."""
    return hashlib.md5(seed.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def puzzles_for_trait(trait: str) -> list[str]:
    """Return puzzle types that a character with this trait would create."""
    return list(TRAIT_PUZZLE_MAP.get(trait, ["combination_lock"]))


def generate_world_bible(
    theme: str,
    premise: str,
    num_characters: int = 3,
    difficulty: int = 3,
) -> dict[str, Any]:
    """Generate a world bible with characters, setting, and inciting incident.

    This is the deterministic (no-AI) version for testing and fast generation.
    """
    rng = random.Random(f"{theme}-{premise}-{difficulty}")

    # Normalize theme
    theme_key = theme.replace(" ", "_").replace("-", "_").lower()
    if theme_key not in THEME_ROOMS:
        theme_key = "gothic_manor"  # fallback

    # Pick characters
    char_pool = list(THEME_CHARACTERS[theme_key])
    rng.shuffle(char_pool)
    characters = char_pool[:num_characters]

    # Add relationships (each character references at least one other)
    for i, char in enumerate(characters):
        others = [c["name"] for j, c in enumerate(characters) if j != i]
        rels = []
        # Always relate to at least one other character
        target = rng.choice(others)
        rel_types = ["distrusts", "protects", "fears", "depends on", "secretly admires", "competes with"]
        rels.append({"target": target, "type": rng.choice(rel_types)})
        char["relationships"] = rels
        # Add secrets based on trait
        secrets_by_trait = {
            "paranoid": "Believes someone is stealing their work",
            "artistic": "Hides coded messages in their artwork",
            "scholarly": "Discovered a dangerous formula",
            "sentimental": "Keeps a locket with a forbidden photograph",
            "meticulous": "Accidentally recorded evidence of a crime",
            "secretive": "Maintains a hidden identity",
            "protective": "Guards a passage to something terrible",
            "grieving": "Preserves a shrine to someone who may not be dead",
        }
        char["secret"] = secrets_by_trait.get(char["trait"], "Has a hidden agenda")
        char["role"] = rng.choice(["builder", "inhabitant", "visitor", "guardian"])

    # Pick rooms based on difficulty
    room_pool = list(THEME_ROOMS[theme_key])
    num_rooms = min(3 + difficulty, len(room_pool))
    rooms = room_pool[:num_rooms]

    # Inciting incident
    incidents = THEME_INCIDENTS[theme_key]
    incident = rng.choice(incidents)

    return {
        "setting": {
            "theme": theme_key,
            "premise": premise,
            "rooms": rooms,
        },
        "characters": characters,
        "inciting_incident": incident,
    }


logger = logging.getLogger(__name__)

# JSON schema for structured AI output — includes full puzzle data per character
_WORLD_BIBLE_SCHEMA = {
    "type": "object",
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "desc": {"type": "string"},
                    "trait": {"type": "string", "enum": VALID_TRAITS},
                    "backstory": {"type": "string"},
                    "secret": {"type": "string"},
                    "role": {"type": "string", "enum": ["builder", "inhabitant", "visitor", "guardian"]},
                    "relationships": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target": {"type": "string"},
                                "type": {"type": "string"},
                            },
                            "required": ["target", "type"],
                        },
                    },
                    # Puzzle data — what this character created
                    "puzzle_type": {"type": "string", "enum": ["combination_lock", "key_lock", "password_door", "pressure_plate", "examine_reveal"]},
                    "code": {"type": "string"},
                    "code_meaning": {"type": "string"},
                    "room_name": {"type": "string"},
                    "room_desc": {"type": "string"},
                    "clue_artifact": {"type": "string"},
                    "clue_artifact_desc": {"type": "string"},
                    "accidental_clue": {"type": "string"},
                    "accidental_clue_desc": {"type": "string"},
                    "lock_name": {"type": "string"},
                    "lock_desc": {"type": "string"},
                },
                "required": ["name", "desc", "trait", "backstory", "secret", "role", "relationships",
                             "puzzle_type", "code", "code_meaning", "room_name", "room_desc",
                             "clue_artifact", "clue_artifact_desc", "accidental_clue", "accidental_clue_desc",
                             "lock_name", "lock_desc"],
            },
        },
        "inciting_incident": {"type": "string"},
        "rooms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "desc": {"type": "string"},
                },
                "required": ["name", "desc"],
            },
        },
    },
    "required": ["characters", "inciting_incident", "rooms"],
}


def generate_world_bible_ai(
    theme: str,
    premise: str,
    num_characters: int = 3,
    difficulty: int = 3,
) -> dict[str, Any]:
    """Generate a world bible using the Claude API for rich, unique content.

    Falls back to deterministic generate_world_bible() on any API failure.
    """
    try:
        if Anthropic is None:
            raise ImportError("anthropic package not installed")

        api_key = get_api_key()
        if not api_key:
            raise ValueError("No API key available")

        client = Anthropic(api_key=api_key)
        model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")

        theme_key = theme.replace(" ", "_").replace("-", "_").lower()
        if theme_key not in THEME_ROOMS:
            theme_key = "gothic_manor"

        num_rooms = min(3 + difficulty, len(THEME_ROOMS[theme_key]))

        puzzle_types_explained = (
            "combination_lock (4-digit code), key_lock (hidden key), "
            "password_door (spoken word), pressure_plate (heavy object), "
            "examine_reveal (hidden item found by examining)"
        )
        prompt = (
            f"Create a story-driven escape room based on this premise:\n"
            f"Premise: {premise}\n"
            f"Theme: {theme_key.replace('_', ' ')}\n\n"
            f"Generate {num_characters} characters who CREATED the puzzles in this place. "
            f"Each character's personality explains WHY they built their puzzle and WHAT the code means.\n\n"
            f"For each character provide:\n"
            f"- name, desc, backstory (2-3 sentences explaining their role in the story)\n"
            f"- trait (one of: {', '.join(VALID_TRAITS)})\n"
            f"- secret, role (builder/inhabitant/visitor/guardian)\n"
            f"- relationships (at least 1, with target name and type)\n"
            f"- puzzle_type (one of: {puzzle_types_explained}). Use DIFFERENT types for each character.\n"
            f"- code: the solution (4 digits for combination_lock, a word for password_door, descriptive for others)\n"
            f"- code_meaning: WHY this code matters in the story (e.g. 'the year he discovered the formula')\n"
            f"- room_name, room_desc: the room this character occupied (vivid, atmospheric, reflects personality)\n"
            f"- clue_artifact, clue_artifact_desc: an object the character DELIBERATELY left as a clue (diary, letter, inscription)\n"
            f"- accidental_clue, accidental_clue_desc: evidence the character LEFT WITHOUT REALIZING (worn path, fingerprints, habits)\n"
            f"- lock_name, lock_desc: what the puzzle lock looks like\n\n"
            f"Also provide:\n"
            f"- inciting_incident: what happened that sealed everything (2-3 sentences)\n"
            f"- rooms: {num_rooms} rooms with name/desc (first=entrance, last=exit, middle=character rooms)\n\n"
            f"Make codes MEANINGFUL — a birth year, a name, a Latin word, an employee number. Never random digits.\n"
            f"Make clue text read like real artifacts — diary entries, letters, inscriptions, notes.\n"
        )

        # Add JSON instruction to prompt
        prompt += (
            "\nRespond with ONLY valid JSON matching this structure:\n"
            '{"characters": [...], "inciting_incident": "...", "rooms": [...]}\n'
            "No markdown, no explanation — just the JSON object.\n"
        )

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        content = response.content[0].text.strip()
        # Strip markdown fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()
        data = json.loads(content)

        # Validate and normalize
        characters = data["characters"]
        if len(characters) < 2:
            raise ValueError(f"Need at least 2 characters, got {len(characters)}")

        rooms = data.get("rooms", [])
        if len(rooms) < 2:
            raise ValueError(f"Need at least 2 rooms, got {len(rooms)}")

        # Normalize characters — fill missing fields with defaults
        for char in characters:
            if char.get("trait") not in VALID_TRAITS:
                char["trait"] = "paranoid"  # safe default
            char.setdefault("backstory", char.get("desc", ""))
            char.setdefault("secret", "Has a hidden agenda")
            char.setdefault("role", "inhabitant")
            char.setdefault("relationships", [])
            # Puzzle fields — AI should generate these, but default if missing
            char.setdefault("puzzle_type", "combination_lock")
            char.setdefault("code", "1234")
            char.setdefault("code_meaning", "a significant number")
            char.setdefault("room_name", f"{char['name']}'s Room")
            char.setdefault("room_desc", f"A room associated with {char['name']}.")
            char.setdefault("clue_artifact", f"{char['name']}'s Note")
            char.setdefault("clue_artifact_desc", f"A note left by {char['name']}.")
            char.setdefault("accidental_clue", f"Traces of {char['name']}")
            char.setdefault("accidental_clue_desc", f"Evidence of {char['name']}'s presence.")
            char.setdefault("lock_name", f"{char['name']}'s Lock")
            char.setdefault("lock_desc", f"A lock created by {char['name']}.")

        return {
            "setting": {
                "theme": theme_key,
                "premise": premise,
                "rooms": rooms,
            },
            "characters": characters[:num_characters],
            "inciting_incident": data.get("inciting_incident", "Something sealed this place shut."),
        }

    except Exception as e:
        logger.warning(f"AI world bible generation failed, falling back to deterministic: {e}")
        return generate_world_bible(
            theme=theme,
            premise=premise,
            num_characters=num_characters,
            difficulty=difficulty,
        )


def generate_clues_for_puzzle(
    puzzle_type: str,
    solution: str,
    character: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate intentional + accidental clues for a puzzle.

    Returns list of clue dicts with: clue_type, text, entity_name, entity_desc.
    """
    name = character.get("name", "Unknown")
    trait = character.get("trait", "paranoid")
    clues: list[dict[str, Any]] = []

    if puzzle_type == "combination_lock":
        # Intentional: character deliberately wrote the code somewhere
        clues.append({
            "clue_type": "intentional",
            "text": f'A journal entry reads: "Remember the number — {solution}. Never forget."',
            "entity_name": f"{name}'s Journal",
            "entity_desc": f"A leather-bound journal belonging to {name}. The handwriting is meticulous.",
        })
        # Accidental: character used the code in other places
        clues.append({
            "clue_type": "accidental",
            "text": f'A receipt is dated {solution}. {name} circled this number on multiple documents.',
            "entity_name": "Scattered Documents",
            "entity_desc": f"Papers scattered across the desk. The number {solution} appears several times.",
        })

    elif puzzle_type == "key_lock":
        # Intentional: character hid the key behind something meaningful
        hiding_spots = {
            "paranoid": f"behind a false panel in {name}'s desk",
            "artistic": f"inside a hollow sculpture {name} created",
            "scholarly": f"tucked inside {name}'s favorite reference book",
            "sentimental": f"hidden in a music box that plays {name}'s wedding song",
            "secretive": f"concealed beneath a loose floorboard near {name}'s bed",
        }
        spot = hiding_spots.get(trait, f"hidden behind a painting of {name}")
        clues.append({
            "clue_type": "intentional",
            "text": f"The key is hidden {spot}.",
            "entity_name": f"{name}'s Hiding Spot",
            "entity_desc": f"Something about this area suggests {name} spent time here.",
        })
        # Accidental: wear marks show where character accessed it
        clues.append({
            "clue_type": "accidental",
            "text": f"Scratch marks on the wall suggest something was frequently moved here.",
            "entity_name": "Worn Marks",
            "entity_desc": "Subtle scratches and wear on the surface. Someone accessed this spot regularly.",
        })

    elif puzzle_type == "password_door":
        # Intentional: character embedded the password in a meaningful phrase
        clues.append({
            "clue_type": "intentional",
            "text": f'An inscription reads: "Speak the word \'{solution}\' and the way shall open."',
            "entity_name": f"Ancient Inscription",
            "entity_desc": f"Words carved into stone by {name}'s own hand.",
        })
        # Accidental: character muttered the word in a letter
        clues.append({
            "clue_type": "accidental",
            "text": f'A letter from {name} mentions: "I always whisper \'{solution}\' before entering."',
            "entity_name": f"{name}'s Letter",
            "entity_desc": f"A personal letter from {name}, never meant to be read by others.",
        })

    elif puzzle_type == "pressure_plate":
        clues.append({
            "clue_type": "intentional",
            "text": f"{name} designed the plate to respond to a heavy object.",
            "entity_name": "Blueprint Fragment",
            "entity_desc": f"A torn blueprint showing {name}'s design for a weight-triggered mechanism.",
        })
        clues.append({
            "clue_type": "accidental",
            "text": f"A heavy item sits nearby, as if {name} tested the mechanism here.",
            "entity_name": "Heavy Object",
            "entity_desc": "A surprisingly heavy item. It looks like it was placed here deliberately.",
        })

    elif puzzle_type == "examine_reveal":
        clues.append({
            "clue_type": "intentional",
            "text": f"{name} concealed something behind this object.",
            "entity_name": f"{name}'s Hidden Cache",
            "entity_desc": f"Something {name} wanted to keep safe. Examine carefully.",
        })
        clues.append({
            "clue_type": "accidental",
            "text": f"Fingerprints cover this area. {name} touched it frequently.",
            "entity_name": "Smudged Surface",
            "entity_desc": "Oil and fingerprints show heavy use. Someone checked this spot often.",
        })

    else:
        # Fallback
        clues.append({
            "clue_type": "intentional",
            "text": f"A note from {name} hints at the solution: {solution}",
            "entity_name": f"{name}'s Note",
            "entity_desc": f"A handwritten note from {name}.",
            "description": f"A handwritten note from {name}.",
        })

    return clues


# ---------------------------------------------------------------------------
# Room structure builder
# ---------------------------------------------------------------------------

def _build_rooms_and_puzzles(
    bible: dict[str, Any],
    difficulty: int,
    rng: random.Random,
) -> tuple[WorldState, list[dict[str, Any]]]:
    """Build rooms, doors, entities, and puzzles from the world bible.

    Each character's puzzle data (code, meaning, artifacts) drives room construction.
    Puzzles emerge from character backstories, not random generation.

    Returns (WorldState, escape_chain_steps).
    """
    ws = WorldState()
    characters = bible["characters"]
    escape_chain: list[dict[str, Any]] = []

    # --- Build rooms from characters ---
    # Start room + one room per character (their personal space) + exit room
    room_seeds = bible["setting"]["rooms"]
    start_room_seed = room_seeds[0] if room_seeds else {"name": "Entrance", "desc": "The starting point."}
    exit_room_seed = room_seeds[-1] if len(room_seeds) > 1 else {"name": "Exit Hall", "desc": "Freedom awaits."}

    def _room_desc(seed: dict) -> str:
        """Get room description, handling both 'desc' and 'description' keys."""
        return seed.get("desc", seed.get("description", "A mysterious room."))

    # Create start room
    start_id = _stable_id(f"room-start-{start_room_seed['name']}")
    ws.add_room(Room(id=start_id, name=start_room_seed["name"], description=_room_desc(start_room_seed)))
    room_ids = [start_id]

    # Create one room per character (using THEIR room data if available)
    num_puzzle_rooms = min(len(characters), difficulty)
    puzzle_chars = characters[:num_puzzle_rooms]

    for i, char in enumerate(puzzle_chars):
        rname = char.get("room_name", f"{char['name']}'s Room")
        rdesc = char.get("room_desc", char.get("room_description", f"A room associated with {char['name']}."))
        rid = _stable_id(f"room-{i}-{rname}")
        ws.add_room(Room(id=rid, name=rname, description=rdesc))
        room_ids.append(rid)

    # Create exit room
    exit_id = _stable_id(f"room-exit-{exit_room_seed['name']}")
    ws.add_room(Room(id=exit_id, name=exit_room_seed["name"], description=_room_desc(exit_room_seed)))
    room_ids.append(exit_id)

    start_room_id = room_ids[0]
    exit_room_id = room_ids[-1]

    # --- Connect rooms with doors and character puzzles ---
    directions = ["east", "south", "east", "south", "east", "south"]
    opposites = {"east": "west", "south": "north", "north": "south", "west": "east"}

    for i in range(len(room_ids) - 1):
        direction = directions[i % len(directions)]
        opp = opposites[direction]
        door_id = _stable_id(f"door-{i}")
        is_locked = i > 0  # First door is unlocked (start → first puzzle room)

        # Which character "owns" this transition?
        char_idx = i - 1 if i > 0 else 0  # door 0 is unlocked, doors 1+ use characters
        char = puzzle_chars[min(char_idx, len(puzzle_chars) - 1)] if puzzle_chars else characters[0]

        puzzle_type = char.get("puzzle_type", "combination_lock")
        code = char.get("code", "1234")

        door = Door(
            id=door_id,
            name=char.get("lock_name", f"Door to {ws.rooms[room_ids[i + 1]].name}"),
            room_a=room_ids[i],
            room_b=room_ids[i + 1],
            locked=is_locked,
            key_id=f"key_{door_id}" if puzzle_type == "key_lock" and is_locked else None,
        )
        ws.add_door(door, direction, opp)

        if not is_locked:
            continue

        # --- Place character's puzzle using THEIR narrative data ---
        source_room = ws.rooms[room_ids[i]]

        # Intentional clue artifact (character placed it deliberately)
        clue_name = char.get("clue_artifact", f"{char['name']}'s Clue")
        clue_desc = char.get("clue_artifact_desc", f"Something left by {char['name']}.")
        clue_id = _stable_id(f"clue-{i}-{clue_name}")
        source_room.add_entity(Entity(
            id=clue_id,
            name=clue_name,
            description=clue_desc,
            properties={
                "on_examine": {"message": clue_desc},
                "clue_for": door_id,
            },
        ))
        escape_chain.append({
            "step": len(escape_chain) + 1, "action": "examine",
            "target": clue_name, "room": source_room.name,
            "room_id": source_room.id,
            "description": f"Examine {clue_name} — {char.get('code_meaning', 'find the clue')}",
            "status": "pending", "check_type": "examine",
        })

        # Accidental clue (character didn't realize they left evidence)
        acc_name = char.get("accidental_clue", f"Traces of {char['name']}")
        acc_desc = char.get("accidental_clue_desc", f"Evidence of {char['name']}'s habits.")
        acc_id = _stable_id(f"aclue-{i}-{acc_name}")
        source_room.add_entity(Entity(
            id=acc_id, name=acc_name, description=acc_desc,
            properties={"on_examine": {"message": acc_desc}},
        ))

        # --- Create the lock/puzzle mechanism ---
        lock_name = char.get("lock_name", f"{char['name']}'s Lock")
        lock_desc = char.get("lock_desc", f"A lock created by {char['name']}.")

        if puzzle_type == "combination_lock":
            lock_id = _stable_id(f"lock-{i}")
            source_room.add_entity(Entity(
                id=lock_id, name=lock_name, description=lock_desc,
                properties={
                    "puzzle_type": "combination_lock",
                    "combination": code,
                    "on_solve": {
                        "set_state": "solved", "unlock_door": door_id,
                        "message": f"The code {code} works! {char.get('code_meaning', 'The lock opens.')}",
                    },
                },
            ))
            escape_chain.append({
                "step": len(escape_chain) + 1, "action": "solve",
                "target": lock_name, "entity_id": lock_id,
                "room": source_room.name, "room_id": source_room.id,
                "description": f"Enter code {code} ({char.get('code_meaning', '')}) on {lock_name}",
                "status": "pending", "check_type": "solve",
            })

        elif puzzle_type == "key_lock":
            key_id = f"key_{door_id}"
            # Hider entity — examine it to reveal the key
            hider_id = _stable_id(f"hider-{i}")
            hider_desc = char.get("clue_artifact_desc", f"Something {char['name']} hid carefully.")
            source_room.add_entity(Entity(
                id=hider_id, name=f"{char['name']}'s Hiding Spot",
                description=hider_desc,
                properties={
                    "on_examine": {
                        "reveal": [key_id],
                        "message": f"You find a key hidden here — {char.get('code_meaning', 'exactly where they left it')}!",
                    },
                },
            ))
            source_room.add_entity(Item(
                id=key_id, name=f"{char['name']}'s Key",
                description=f"A key that {char['name']} hid — {char.get('code_meaning', 'it unlocks something important')}.",
                state=EntityState.HIDDEN, portable=True,
            ))
            escape_chain.append({
                "step": len(escape_chain) + 1, "action": "reveal",
                "target": f"{char['name']}'s Key", "entity_id": key_id,
                "room": source_room.name, "room_id": source_room.id,
                "description": f"Find {char['name']}'s Key ({char.get('code_meaning', '')})",
                "status": "pending", "check_type": "reveal",
            })
            escape_chain.append({
                "step": len(escape_chain) + 1, "action": "unlock",
                "target": door.name, "entity_id": door_id,
                "room": source_room.name, "room_id": source_room.id,
                "description": f"Use {char['name']}'s Key on {door.name}",
                "status": "pending", "check_type": "door",
            })

        elif puzzle_type == "password_door":
            listener_id = _stable_id(f"listener-{i}")
            source_room.add_entity(Entity(
                id=listener_id, name=lock_name, description=lock_desc,
                properties={
                    "puzzle_type": "password_door",
                    "password": code, "case_sensitive": False,
                    "on_solve": {
                        "set_state": "solved", "unlock_door": door_id,
                        "message": f"The word '{code}' echoes — {char.get('code_meaning', 'the seal breaks')}!",
                    },
                },
            ))
            escape_chain.append({
                "step": len(escape_chain) + 1, "action": "solve",
                "target": lock_name, "entity_id": listener_id,
                "room": source_room.name, "room_id": source_room.id,
                "description": f"Speak '{code}' ({char.get('code_meaning', '')}) to {lock_name}",
                "status": "pending", "check_type": "solve",
            })

        elif puzzle_type == "pressure_plate":
            plate_id = _stable_id(f"plate-{i}")
            heavy_id = _stable_id(f"heavy-{i}")
            heavy_name = char.get("code", "Stone Weight").replace("_", " ").title()
            source_room.add_entity(Entity(
                id=plate_id, name=lock_name, description=lock_desc,
                properties={
                    "puzzle_type": "pressure_plate", "required_weight": "heavy",
                    "on_solve": {
                        "set_state": "solved", "unlock_door": door_id,
                        "message": f"The mechanism triggers — {char.get('code_meaning', 'the way opens')}!",
                    },
                },
            ))
            source_room.add_entity(Item(
                id=heavy_id, name=heavy_name,
                description=f"A heavy object — {char.get('code_meaning', 'it could trigger something')}.",
                portable=True, properties={"weight": "heavy"},
            ))
            escape_chain.append({
                "step": len(escape_chain) + 1, "action": "solve",
                "target": lock_name, "entity_id": plate_id,
                "room": source_room.name, "room_id": source_room.id,
                "description": f"Drop {heavy_name} on {lock_name}",
                "status": "pending", "check_type": "solve",
            })

        elif puzzle_type == "examine_reveal":
            examiner_id = _stable_id(f"examiner-{i}")
            hidden_id = _stable_id(f"hidden-{i}")
            mechanism_id = _stable_id(f"mech-{i}")
            hidden_name = char.get("code", "hidden_token").replace("_", " ").title()
            source_room.add_entity(Entity(
                id=examiner_id, name=f"{char['name']}'s Keepsake",
                description=char.get("clue_artifact_desc", f"Something precious to {char['name']}."),
                properties={
                    "on_examine": {
                        "reveal": [hidden_id],
                        "message": f"Hidden inside — {char.get('code_meaning', 'a concealed item')}!",
                    },
                },
            ))
            source_room.add_entity(Item(
                id=hidden_id, name=hidden_name,
                description=f"Found inside {char['name']}'s keepsake — {char.get('code_meaning', 'important')}.",
                state=EntityState.HIDDEN, portable=True,
                usable_on=[lock_name],
            ))
            source_room.add_entity(Entity(
                id=mechanism_id, name=lock_name, description=lock_desc,
                properties={
                    "on_use": {
                        "set_state": "solved", "unlock_door": door_id,
                        "consume_item": True,
                        "message": f"The {hidden_name} fits perfectly — {char.get('code_meaning', 'the way opens')}!",
                    },
                },
            ))
            escape_chain.append({
                "step": len(escape_chain) + 1, "action": "solve",
                "target": f"{char['name']}'s Keepsake", "entity_id": examiner_id,
                "room": source_room.name, "room_id": source_room.id,
                "description": f"Find {hidden_name} in {char['name']}'s Keepsake, use on {lock_name}",
                "status": "pending", "check_type": "solve",
            })

    # --- Exit mechanism in final room ---
    exit_room = ws.rooms[exit_room_id]
    exit_id = _stable_id("exit-door")
    exit_door = Entity(
        id=exit_id,
        name="Exit Door",
        description="A heavy door. Beyond it — freedom.",
        properties={
            "on_use": {
                "finish": "You escaped! The story of this place will be told for generations.",
            },
        },
    )
    exit_room.add_entity(exit_door)
    escape_chain.append({
        "step": len(escape_chain) + 1,
        "action": "escape",
        "target": "Exit Door",
        "entity_id": exit_id,
        "room": exit_room.name,
        "room_id": exit_room_id,
        "description": "Use Exit Door to escape!",
        "status": "pending",
        "check_type": "finish",
    })

    # --- Cooperative puzzle: information asymmetry ---
    # A clue in the start room that must be spoken at a ward near the exit.
    # Agents start in different rooms, forcing Talk to share the password.
    if len(room_ids) >= 3 and difficulty >= 3:
        coop_password = bible["characters"][0]["name"].lower()
        coop_room = ws.rooms[start_room_id]
        coop_clue_id = _stable_id("coop-clue")
        coop_clue = Entity(
            id=coop_clue_id,
            name="Whispered Inscription",
            description="Faint words etched into the wall, barely visible.",
            properties={
                "on_examine": {
                    "message": (
                        f'The inscription reads: "When all seems lost, '
                        f"speak the word '{coop_password}' to the final ward.\""
                    ),
                },
                "cooperative": True,
            },
        )
        coop_room.add_entity(coop_clue)

        # Ward near the exit
        exit_room = ws.rooms[exit_room_id]
        coop_ward_id = _stable_id("coop-ward")
        coop_ward = Entity(
            id=coop_ward_id,
            name="Final Ward",
            description="A shimmering barrier. It seems to listen for a spoken word.",
            properties={
                "puzzle_type": "password_door",
                "password": coop_password,
                "case_sensitive": False,
                "cooperative": True,
                "on_solve": {
                    "set_state": "solved",
                    "message": "The Final Ward dissolves! The way is clear.",
                },
            },
        )
        exit_room.add_entity(coop_ward)
        escape_chain.append({
            "step": len(escape_chain) + 1,
            "action": "solve",
            "target": "Final Ward",
            "entity_id": coop_ward_id,
            "room": exit_room.name,
            "room_id": exit_room_id,
            "description": f"Say '{coop_password}' to the Final Ward (requires cooperation!)",
            "status": "pending",
            "check_type": "solve",
            "cooperative": True,
        })

    # Renumber escape chain
    for idx, step in enumerate(escape_chain):
        step["step"] = idx + 1

    # --- Create agents in DIFFERENT rooms ---
    agent_b_room = room_ids[1] if len(room_ids) >= 3 and difficulty >= 3 else start_room_id
    agent_a = AgentState(
        id="investigator_a",
        name="Alice",
        description="A sharp-eyed scholar who reads between the lines",
        room_id=start_room_id,
        goal="Examine everything carefully. Share ALL discoveries with Bob via Talk — he needs your clues! Find a way out together.",
    )
    agent_b = AgentState(
        id="investigator_b",
        name="Bob",
        description="A bold explorer who acts first and thinks later",
        room_id=agent_b_room,
        goal="Explore rooms, try doors and mechanisms. Ask Alice what she's found — she has clues you need. Work together to escape.",
    )
    ws.add_agent(agent_a)
    ws.add_agent(agent_b)

    return ws, escape_chain


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_clue_reachability(world: World) -> list[str]:
    """Verify that every puzzle's clue is reachable before the puzzle.

    Uses sequential unlock simulation: start from the beginning, unlock doors
    one at a time as their puzzles become reachable, and verify all doors
    can eventually be unlocked.

    Returns list of issues (empty = all good).
    """
    issues: list[str] = []
    state = world.state

    start_room = list(state.agents.values())[0].room_id
    unlocked_doors: set[str] = set()

    # Iteratively expand reachable area by solving accessible puzzles
    changed = True
    while changed:
        changed = False

        # BFS with currently unlocked doors
        visited: set[str] = set()
        queue = [start_room]
        while queue:
            rid = queue.pop(0)
            if rid in visited:
                continue
            visited.add(rid)
            room = state.rooms.get(rid)
            if not room:
                continue
            for d_id in room.doors.values():
                d = state.doors.get(d_id)
                if not d:
                    continue
                # Can traverse if door is unlocked or we've already solved it
                if d.locked and d.id not in unlocked_doors:
                    continue
                other = d.other_side(rid)
                if other and other not in visited:
                    queue.append(other)

        # Check which locked doors have their puzzle accessible in visited rooms
        for door in state.doors.values():
            if not door.locked or door.id in unlocked_doors:
                continue

            # Look for a puzzle entity that unlocks this door in reachable rooms
            for rid in visited:
                room = state.rooms[rid]
                for entity in room.entities.values():
                    on_solve = entity.properties.get("on_solve", {})
                    on_use = entity.properties.get("on_use", {})
                    clue_for = entity.properties.get("clue_for")

                    unlocks_this = False
                    if isinstance(on_solve, dict) and on_solve.get("unlock_door") == door.id:
                        unlocks_this = True
                    if isinstance(on_use, dict) and on_use.get("unlock_door") == door.id:
                        unlocks_this = True
                    # Key locks: check if the key is in a reachable room
                    if door.key_id:
                        for vrid in visited:
                            vroom = state.rooms[vrid]
                            if door.key_id in vroom.entities:
                                unlocks_this = True
                                break

                    if unlocks_this:
                        unlocked_doors.add(door.id)
                        changed = True
                        break
                if door.id in unlocked_doors:
                    break

    # After simulation, check for any doors still locked
    for door in state.doors.values():
        if door.locked and door.id not in unlocked_doors:
            issues.append(
                f"Door '{door.name}' (id={door.id}) has no reachable clue/puzzle from start"
            )

    return issues


# ---------------------------------------------------------------------------
# Main public entry point
# ---------------------------------------------------------------------------

def build_story_world(
    theme: str,
    premise: str,
    difficulty: int = 3,
    num_characters: int = 3,
    use_ai: bool = True,
) -> tuple[World, list[str], dict[str, Any]]:
    """Full pipeline: story seed → playable World + metadata.

    Args:
        use_ai: If True (default), try AI-powered generation first for unique,
                premise-aware content. Falls back to deterministic if AI unavailable.

    Returns:
        (world, agent_ids, metadata)
        metadata contains: world_bible, escape_chain, characters
    """
    rng = random.Random(f"{theme}-{premise}-{difficulty}")

    # Step 1: Generate world bible — AI first, deterministic fallback
    gen_fn = generate_world_bible_ai if use_ai else generate_world_bible
    bible = gen_fn(
        theme=theme,
        premise=premise,
        num_characters=num_characters,
        difficulty=difficulty,
    )

    # Step 2-4: Build rooms, puzzles, clues
    ws, escape_chain = _build_rooms_and_puzzles(bible, difficulty, rng)

    # Step 5: Create World and validate
    world = World(ws)

    issues = validate_clue_reachability(world)
    if issues:
        # Log but don't fail — we'll fix in future iterations
        import logging
        logger = logging.getLogger(__name__)
        for issue in issues:
            logger.warning(f"Solvability issue: {issue}")

    agent_ids = list(ws.agents.keys())

    metadata = {
        "world_bible": bible,
        "escape_chain": escape_chain,
        "theme": theme,
        "premise": premise,
        "difficulty": difficulty,
    }

    return world, agent_ids, metadata
