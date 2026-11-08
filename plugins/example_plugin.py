"""Example plugin. Drop .py files in this folder (or ~/.jarvis/plugins) and Jarvis loads them at startup.
Any function decorated with @tool becomes something you can ask for by voice."""
import random

from jarvis.registry import tool


@tool("Roll a die with a given number of sides.", {"sides": ("integer", "Number of sides, default 6")}, required=[])
def roll_die(sides=6):
    return f"Rolled {random.randint(1, max(2, int(sides)))}."
