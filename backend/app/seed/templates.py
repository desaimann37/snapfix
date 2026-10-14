"""Templates for synthetic historical tickets. Placeholders: {label}, {room}, {building}, {asset}."""

# category -> list of (title, reporter text, AI-style summary)
TICKET_TEMPLATES: dict[str, list[tuple[str, str, str]]] = {
    "leak_water": [
        ("Faucet dripping at {asset}", "the faucet in {room} keeps dripping even when it's off",
         "Faucet at {asset} in {label} drips continuously when closed. Water is pooling on the counter."),
        ("Leak under sink in {label}", "water leaking under the sink, cabinet floor is wet",
         "Reporter found water leaking beneath the sink in {label}; the cabinet base is wet."),
        ("Ceiling drip in {label}", "small drip from the ceiling near the door",
         "Slow drip from the ceiling near the entrance of {label}. Bucket placed by reporter."),
    ],
    "clogged_drain": [
        ("Slow drain at {asset}", "sink in {room} drains super slowly",
         "Sink at {asset} in {label} drains very slowly; standing water after use."),
        ("Clogged sink in {label}", "sink is completely clogged, water won't go down",
         "Sink in {label} is fully blocked and not draining."),
    ],
    "toilet_malfunction": [
        ("Toilet running constantly in {label}", "toilet won't stop running",
         "Toilet in {label} runs continuously after flushing."),
        ("Toilet clogged in {label}", "toilet in the second stall is clogged",
         "Toilet in {label} is clogged and unusable; stall closed by reporter."),
        ("Urinal not flushing in {label}", "urinal sensor isn't flushing",
         "Urinal flush sensor in {label} not activating."),
    ],
    "fountain_broken": [
        ("Bottle filler not working in {label}", "bottle filler isn't dispensing water",
         "Bottle-filling station in {label} does not dispense water."),
        ("Low pressure at drinking fountain in {label}", "water fountain barely trickles",
         "Drinking fountain in {label} has very low pressure."),
    ],
    "flooding": [
        ("Water spreading across floor in {label}", "there's water all over the floor coming from the wall",
         "Significant water spreading across the floor of {label} from the wall; source unknown."),
    ],
    "light_out": [
        ("Light out in {label}", "one of the ceiling lights is out in {room}",
         "One ceiling light fixture in {label} is out."),
        ("Flickering lights in {label}", "lights keep flickering, giving people headaches",
         "Ceiling lights in {label} flicker continuously."),
        ("Several lights out in {label}", "half the lights are dead in {room}",
         "Multiple light fixtures in {label} are not working; area is dim."),
    ],
    "exposed_wiring": [
        ("Exposed wires at {label}", "wires hanging out of the wall plate",
         "Exposed conductors visible where a wall plate is missing in {label}."),
    ],
    "power_outlet_dead": [
        ("Dead outlet in {label}", "outlet by the window doesn't work",
         "Wall outlet near the window in {label} has no power."),
        ("No power to bench outlets in {label}", "none of the bench outlets work",
         "Bench receptacles in {label} have no power; possibly a tripped GFCI."),
    ],
    "too_hot": [
        ("Room too hot in {label}", "it's way too hot in {room}, like 82 degrees",
         "Reporter says {label} is very warm (about 82 F); AC does not seem to be cooling."),
        ("No AC in {label}", "AC isn't working in here",
         "Air conditioning not cooling {label}; room is stuffy."),
    ],
    "too_cold": [
        ("Room too cold in {label}", "freezing in {room}, everyone has jackets on",
         "{label} is uncomfortably cold; occupants wearing jackets."),
        ("No heat in {label}", "heat doesn't seem to be on",
         "Heating does not appear to be working in {label}."),
    ],
    "hvac_noise": [
        ("Rattling vent in {label}", "loud rattling noise from the vent",
         "Supply vent in {label} rattles loudly during operation."),
        ("Banging noise from HVAC in {label}", "banging sound from the ceiling every few minutes",
         "Intermittent banging from the HVAC system above {label}."),
    ],
    "door_wont_close": [
        ("Door won't latch at {label}", "door doesn't close all the way",
         "Door to {label} does not latch; closer appears weak."),
        ("Door slams at {label}", "door slams really hard every time",
         "Door at {label} slams shut; closer needs adjustment."),
    ],
    "lock_broken": [
        ("Card reader not working at {label}", "my badge won't open the door",
         "Card reader at {label} does not unlock with valid badges."),
        ("Lock broken on {label}", "the lock is broken, door can't be locked",
         "Door lock at {label} will not engage; room cannot be secured."),
    ],
    "broken_furniture": [
        ("Broken chair in {label}", "chair in {room} has a broken leg",
         "Chair in {label} has a broken leg and is unsafe to sit on."),
        ("Wobbly table in {label}", "table wobbles a lot",
         "Table in {label} is unstable."),
    ],
    "broken_window": [
        ("Cracked window in {label}", "window has a big crack in it",
         "Window pane in {label} is cracked."),
        ("Window won't close in {label}", "window is stuck open",
         "Window in {label} is stuck open and will not close."),
    ],
    "spill": [
        ("Coffee spill in {label}", "someone spilled coffee all over the floor",
         "Coffee spilled on the floor in {label}; sticky walkway."),
        ("Spill near entrance of {label}", "big puddle of soda by the door",
         "Soda spill near the entrance of {label}."),
    ],
    "trash_overflow": [
        ("Trash overflowing in {label}", "trash cans are overflowing",
         "Trash bins in {label} are full and overflowing."),
        ("Recycling full in {label}", "recycling bins are packed",
         "Recycling bins in {label} are full."),
    ],
    "supplies_empty": [
        ("Out of soap in {label}", "no soap in the dispensers",
         "Soap dispensers in {label} are empty."),
        ("No paper towels in {label}", "paper towels are out",
         "Paper towel dispensers in {label} are empty."),
    ],
    "pest": [
        ("Mouse sighting in {label}", "saw a mouse run under the counter",
         "Reporter saw a mouse in {label} near the counter."),
        ("Ants in {label}", "ants all over the counter",
         "Ant trail on the counter in {label}."),
    ],
    "graffiti": [
        ("Graffiti in {label}", "someone wrote graffiti on the stall wall",
         "Graffiti on a wall in {label}."),
    ],
    "biohazard": [
        ("Vomit in {label}", "someone threw up near the sinks",
         "Vomit on the floor of {label}; needs biohazard cleanup."),
    ],
    "ceiling_tile_damage": [
        ("Stained ceiling tile in {label}", "ceiling tile has a brown stain",
         "Ceiling tile in {label} has a brown water stain."),
        ("Missing ceiling tile in {label}", "ceiling tile missing above the hallway",
         "A ceiling tile is missing in {label}."),
    ],
    "trip_hazard": [
        ("Loose carpet in {label}", "carpet is coming up, people keep catching their feet",
         "Loose carpet seam in {label} is catching feet."),
    ],
    "elevator_out": [
        ("Elevator out of service at {label}", "elevator isn't coming at all",
         "Elevator at {label} is not responding to calls."),
        ("Elevator doors not closing at {label}", "elevator doors keep reopening",
         "Elevator doors at {label} repeatedly reopen and will not close."),
    ],
    "projector_broken": [
        ("Projector not working in {label}", "projector won't turn on before my lecture",
         "Projector in {label} does not power on."),
        ("No HDMI signal in {label}", "projector says no signal with HDMI",
         "Projector in {label} shows no signal from the HDMI input."),
    ],
    "wifi_dead_zone": [
        ("Wi-Fi dead zone in {label}", "wifi keeps dropping in {room}",
         "Wi-Fi connection drops repeatedly in {label}."),
    ],
    "mold_suspected": [
        ("Possible mold in {label}", "black spots on the wall near the floor and it smells musty",
         "Dark spotting on the lower wall in {label} with a musty odor; possible mold."),
    ],
    "gas_smell": [
        ("Gas odor reported in {label}", "smells like gas near the back wall",
         "Reporter noticed a natural gas odor near the back wall of {label}."),
    ],
    "smoke_odor": [
        ("Burning smell in {label}", "burning smell coming from somewhere",
         "Burning odor reported in {label}; source unknown."),
    ],
    "chemical_spill": [
        ("Chemical spill in {label}", "small chemical spill on the bench",
         "Small chemical spill on a lab bench in {label}."),
    ],
    "tree_hazard": [
        ("Fallen branch at {label}", "big branch fell on the walkway after the storm",
         "Large branch down across the walkway at {label} after a storm."),
    ],
    "snow_ice": [
        ("Ice on steps at {label}", "steps are covered in ice",
         "Entrance steps at {label} are icy."),
    ],
    "other": [
        ("Bulletin board falling off wall in {label}", "bulletin board is hanging by one screw",
         "Bulletin board in {label} is loose and hanging by one fastener."),
    ],
}

# Short paraphrases used for extra (merged) reports on the same ticket.
EXTRA_REPORT_TEXTS: dict[str, list[str]] = {
    "leak_water": ["still dripping", "water leaking here", "leak getting worse"],
    "toilet_malfunction": ["toilet still running", "same toilet problem", "toilet broken"],
    "light_out": ["lights still out", "it's really dark in here", "light flickering"],
    "too_hot": ["still too hot", "it's really warm in here", "can someone fix the AC"],
    "too_cold": ["still freezing", "so cold in here", "no heat"],
    "trash_overflow": ["trash still overflowing", "bins full"],
    "supplies_empty": ["no soap", "still no paper towels"],
    "spill": ["spill still there", "floor is sticky"],
    "projector_broken": ["projector still broken", "can't present, projector dead"],
    "elevator_out": ["elevator still down", "elevator not working"],
}

RESOLUTION_NOTES: dict[str, list[str]] = {
    "leak_water": ["Replaced faucet cartridge.", "Tightened supply line compression nut.", "Replaced P-trap washer."],
    "clogged_drain": ["Cleared trap and augered line.", "Removed hair clog from stopper."],
    "toilet_malfunction": ["Replaced flush valve diaphragm.", "Cleared blockage with closet auger.",
                           "Adjusted sensor flush valve."],
    "fountain_broken": ["Replaced filter cartridge.", "Cleared clogged strainer."],
    "flooding": ["Isolated broken supply line and replaced fitting; area dried."],
    "light_out": ["Replaced LED driver.", "Replaced lamps.", "Reset tripped lighting breaker."],
    "exposed_wiring": ["Installed blank cover plate and terminated conductors."],
    "power_outlet_dead": ["Reset upstream GFCI.", "Replaced failed GFCI receptacle."],
    "too_hot": ["Replaced clogged filter; adjusted VAV damper.", "Recalibrated thermostat."],
    "too_cold": ["Reset heating valve actuator.", "Thermostat schedule corrected."],
    "hvac_noise": ["Tightened diffuser and damper linkage.", "Replaced worn fan belt."],
    "door_wont_close": ["Adjusted closer latch speed.", "Realigned strike plate."],
    "lock_broken": ["Reprogrammed card reader.", "Replaced lock cylinder."],
    "broken_furniture": ["Removed broken chair and replaced from stock.", "Tightened table legs."],
    "broken_window": ["Boarded and replaced glass pane.", "Repaired window operator."],
    "spill": ["Area cleaned and dried."],
    "trash_overflow": ["Bins emptied; added to evening route."],
    "supplies_empty": ["Dispensers refilled."],
    "pest": ["Traps placed; contractor treated area.", "Sealed entry gap under door."],
    "graffiti": ["Graffiti removed."],
    "biohazard": ["Biohazard cleanup completed by custodial lead."],
    "ceiling_tile_damage": ["Replaced stained tile after confirming no active leak."],
    "trip_hazard": ["Re-stretched and secured carpet seam."],
    "elevator_out": ["Contractor replaced door operator relay.", "Contractor reset controller."],
    "projector_broken": ["Replaced HDMI cable.", "Replaced projector lamp module."],
    "wifi_dead_zone": ["Rebooted access point; added to coverage survey."],
    "mold_suspected": ["Cleaned affected area; condensate leak repaired."],
    "gas_smell": ["Utility found loose fitting at water heater; repaired and tested."],
    "smoke_odor": ["Burnt-out fan motor replaced."],
    "chemical_spill": ["EHS cleaned spill; lab retrained."],
    "tree_hazard": ["Branch removed and walkway cleared."],
    "snow_ice": ["Steps salted and cleared."],
    "other": ["Re-secured to wall."],
}

# category -> which asset types it applies to (seed picks a location that has one)
CATEGORY_ASSET_TYPES: dict[str, list[str]] = {
    "leak_water": ["sink"],
    "clogged_drain": ["sink"],
    "toilet_malfunction": ["toilet"],
    "fountain_broken": ["water fountain"],
    "light_out": ["light fixture"],
    "power_outlet_dead": ["outlet"],
    "too_hot": ["thermostat"],
    "too_cold": ["thermostat"],
    "hvac_noise": ["thermostat", "HVAC unit"],
    "door_wont_close": ["door closer"],
    "projector_broken": ["projector"],
    "wifi_dead_zone": ["wifi access point"],
    "elevator_out": ["elevator"],
}

# category -> room types where it plausibly happens (for categories without a specific asset)
CATEGORY_ROOM_TYPES: dict[str, list[str]] = {
    "supplies_empty": ["restroom"],
    "spill": ["lobby", "corridor", "kitchen", "study", "classroom"],
    "trash_overflow": ["lobby", "corridor", "kitchen", "lounge", "study", "exterior"],
    "pest": ["kitchen", "storage", "lounge", "office"],
    "graffiti": ["restroom", "corridor", "exterior"],
    "broken_window": ["office", "classroom", "lobby", "corridor", "study"],
    "ceiling_tile_damage": ["office", "classroom", "corridor", "study", "restroom", "lab"],
    "trip_hazard": ["corridor", "lobby", "exterior", "study"],
    "mold_suspected": ["restroom", "storage", "mechanical", "office"],
    "snow_ice": ["exterior"],
    "tree_hazard": ["exterior"],
    "broken_furniture": ["classroom", "study", "lounge", "conference", "office"],
    "lock_broken": ["office", "lab", "storage", "server", "conference"],
    "biohazard": ["restroom", "corridor", "lobby"],
    "chemical_spill": ["lab"],
    "gas_smell": ["lab", "kitchen", "mechanical"],
    "smoke_odor": ["kitchen", "mechanical", "corridor", "office"],
    "flooding": ["restroom", "mechanical", "kitchen"],
    "exposed_wiring": ["corridor", "office", "classroom", "mechanical"],
    "other": ["office", "classroom", "corridor", "lobby", "study"],
}

# Relative frequency over the last 60 days (mid-Aug to mid-Oct: cooling season, no snow).
CATEGORY_WEIGHTS: dict[str, float] = {
    "light_out": 12, "leak_water": 9, "too_hot": 9, "too_cold": 4, "toilet_malfunction": 8,
    "clogged_drain": 5, "door_wont_close": 5, "supplies_empty": 6, "trash_overflow": 5, "spill": 4,
    "projector_broken": 5, "power_outlet_dead": 4, "wifi_dead_zone": 4, "broken_furniture": 4,
    "hvac_noise": 3, "ceiling_tile_damage": 3, "lock_broken": 3, "pest": 2, "graffiti": 2,
    "elevator_out": 2, "broken_window": 1, "fountain_broken": 2, "mold_suspected": 1, "trip_hazard": 1,
    "tree_hazard": 0.8, "exposed_wiring": 0.4, "flooding": 0.4, "smoke_odor": 0.3, "gas_smell": 0.3,
    "chemical_spill": 0.3, "biohazard": 0.5, "other": 1.5, "snow_ice": 0,
}

TECHNICIANS: dict[str, list[str]] = {
    "Plumbing": ["tech:plumbing-1", "tech:plumbing-2"],
    "Electrical": ["tech:electrical-1", "tech:electrical-2"],
    "HVAC": ["tech:hvac-1", "tech:hvac-2"],
    "Carpentry/Doors & Locks": ["tech:carpentry-1"],
    "Custodial": ["tech:custodial-1", "tech:custodial-2", "tech:custodial-3"],
    "Grounds": ["tech:grounds-1"],
    "Elevator": ["vendor:elevator"],
    "IT/AV": ["tech:itav-1"],
    "Safety/Environmental": ["tech:ehs-1"],
    "General": ["tech:general-1"],
}
