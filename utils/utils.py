import re

DEBUG_ENABLED = True  
def debug_print(message):
    if DEBUG_ENABLED:
        print(f"[DEBUG] {message}")

# Define extract_entities function (if not already present)
def extract_entities(user_input):
    return re.findall(r'\b[A-Z][a-z]*\b', user_input)  # Extract words starting with capital letter as entities
