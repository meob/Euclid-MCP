EARLY_GAME = """
# Cluedo - Early Game (Turn 3)
# ============================
# Scarlett has 4 cards, 2 suggestions made
# Limited information: many possibilities remain

# Domain: all possible cards
suspect(scarlett)
suspect(plum)
suspect(peacock)
suspect(green)
suspect(mustard)
suspect(white)

weapon(candlestick)
weapon(knife)
weapon(lead_pipe)
weapon(revolver)
weapon(rope)
weapon(wrench)

room(kitchen)
room(ballroom)
room(conservatory)
room(billiard_room)
room(library)
room(study)
room(hall)
room(lounge)
room(dining_room)

# Players in this game
player(scarlett)
player(plum)
player(peacock)
player(mustard)

# Cards in Scarlett's hand (4 cards)
hand(scarlett, plum)
hand(scarlett, knife)
hand(scarlett, library)
hand(scarlett, mustard)

# Turn 1: Scarlett suggests Plum + Candlestick + Kitchen
# Peacock shows a card (unknown which one)
showed(peacock, candlestick, scarlett)

# Turn 2: Plum suggests Mustard + Rope + Hall
# Scarlett shows Plum (which she holds)
showed(scarlett, plum, plum)
"""

LATE_GAME = """
# Cluedo - Late Game (Turn 12)
# ============================
# Much more information gathered through 12 turns
# Most cards are now accounted for

# Domain: all possible cards
suspect(scarlett)
suspect(plum)
suspect(peacock)
suspect(green)
suspect(mustard)
suspect(white)

weapon(candlestick)
weapon(knife)
weapon(lead_pipe)
weapon(revolver)
weapon(rope)
weapon(wrench)

room(kitchen)
room(ballroom)
room(conservatory)
room(billiard_room)
room(library)
room(study)
room(hall)
room(lounge)
room(dining_room)

# Players
player(scarlett)
player(plum)
player(peacock)
player(mustard)

# Scarlett's hand (5 cards)
hand(scarlett, plum)
hand(scarlett, knife)
hand(scarlett, library)
hand(scarlett, mustard)
hand(scarlett, candlestick)

# Cards shown during suggestions
showed(peacock, candlestick, scarlett)
showed(scarlett, plum, plum)
showed(mustard, peacock, plum)
showed(peacock, hall, mustard)
showed(plum, rope, peacock)
showed(scarlett, dining_room, plum)
showed(mustard, wrench, peacock)
showed(peacock, green, scarlett)
"""

RESOLVED_GAME = """
# Cluedo - Resolved Game
# ======================
# Every card except the envelope has been seen in someone's hand.
# Exactly one suspect, one weapon and one room remain: the case is solvable.
#
# Envelope (hidden): green + lead_pipe + ballroom

# Domain: all possible cards
suspect(scarlett)
suspect(plum)
suspect(peacock)
suspect(green)
suspect(mustard)
suspect(white)

weapon(candlestick)
weapon(knife)
weapon(lead_pipe)
weapon(revolver)
weapon(rope)
weapon(wrench)

room(kitchen)
room(ballroom)
room(conservatory)
room(billiard_room)
room(library)
room(study)
room(hall)
room(lounge)
room(dining_room)

# Players
player(scarlett)
player(plum)
player(peacock)
player(mustard)

# Cards in each player's hand (every card except the envelope)
hand(scarlett, mustard)
hand(scarlett, white)
hand(scarlett, candlestick)
hand(scarlett, knife)
hand(scarlett, kitchen)
hand(scarlett, study)

hand(peacock, plum)
hand(peacock, library)
hand(peacock, lounge)

hand(mustard, peacock)
hand(mustard, wrench)
hand(mustard, billiard_room)
hand(mustard, dining_room)

hand(plum, rope)
hand(plum, conservatory)
hand(plum, hall)

# Cards revealed during suggestions
showed(plum, scarlett, peacock)
showed(mustard, revolver, plum)
"""
