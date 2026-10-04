import os
import glob

def replace_in_file(filepath, old_text, new_text):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if old_text in content:
        content = content.replace(old_text, new_text)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")

for root, _, files in os.walk('.'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            replace_in_file(filepath, 'opspilot_persistence.repositories', 'opspilot_persistence.repositories')
            replace_in_file(filepath, 'opspilot_persistence.db', 'opspilot_persistence.db')
