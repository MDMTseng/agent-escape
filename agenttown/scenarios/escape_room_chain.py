"""Pre-built escape chain for the default escape room scenario."""

DEFAULT_ESCAPE_CHAIN = [
    {"step": 1, "action": "examine", "target": "Crumpled Note", "entity_id": "note", "room": "The Study", "room_id": "start", "description": "Read the note for painting clue", "status": "pending", "check_type": "examine"},
    {"step": 2, "action": "examine", "target": "Old Book", "entity_id": "book", "room": "The Study", "room_id": "start", "description": "Read the book — code 1847 & password LUMINA", "status": "pending", "check_type": "examine"},
    {"step": 3, "action": "reveal", "target": "Brass Key", "entity_id": "brass_key", "room": "The Workshop", "room_id": "workshop", "description": "Find Brass Key behind the Painting", "status": "pending", "check_type": "reveal"},
    {"step": 4, "action": "solve", "target": "Puzzle Box", "entity_id": "puzzle_box", "room": "The Workshop", "room_id": "workshop", "description": "Enter code 1847 on Puzzle Box", "status": "pending", "check_type": "solve"},
    {"step": 5, "action": "unlock", "target": "Steel Door", "entity_id": "door_workshop_vault", "room": "Workshop → Vault", "room_id": "workshop", "description": "Use Brass Key on Steel Door", "status": "pending", "check_type": "door"},
    {"step": 6, "action": "solve", "target": "Stone Floor Plate", "entity_id": "pressure_plate", "room": "The Vault", "room_id": "vault", "description": "Drop Stone Bust on Pressure Plate", "status": "pending", "check_type": "solve"},
    {"step": 7, "action": "unlock", "target": "Hidden Panel", "entity_id": "door_workshop_sanctum", "room": "Workshop → Sanctum", "room_id": "workshop", "description": "Pressure plate opens Hidden Panel", "status": "pending", "check_type": "door"},
    {"step": 8, "action": "solve", "target": "Lever Mechanism", "entity_id": "lever_controller", "room": "The Vault", "room_id": "vault", "description": "Pull levers: Red → Green → Blue", "status": "pending", "check_type": "solve"},
    {"step": 9, "action": "unlock", "target": "Rising Gate", "entity_id": "door_vault_hallway_secret", "room": "Vault → Hallway", "room_id": "vault", "description": "Levers open the Rising Gate", "status": "pending", "check_type": "door"},
    {"step": 10, "action": "solve", "target": "Enchanted Archway", "entity_id": "archway", "room": "The Sanctum", "room_id": "sanctum", "description": "Say LUMINA to open Archway", "status": "pending", "check_type": "solve"},
    {"step": 11, "action": "unlock", "target": "Archway Passage", "entity_id": "door_sanctum_hallway", "room": "Sanctum → Hallway", "room_id": "sanctum", "description": "Password opens Archway Passage", "status": "pending", "check_type": "door"},
    {"step": 12, "action": "escape", "target": "Iron Door", "entity_id": "exit_door", "room": "The Hallway", "room_id": "hallway", "description": "Push Iron Door to escape!", "status": "pending", "check_type": "finish"},
]
