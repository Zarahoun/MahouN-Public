import os
import re
from pathlib import Path

def get_ultra_files(root_dir):
    ultra_files = []
    for root, dirs, files in os.walk(root_dir):
        if 'archive' in root: continue
        for file in files:
            if file.startswith('ultra_') and file.endswith('.py'):
                ultra_files.append(Path(root) / file)
    return ultra_files

def check_usage(file_path, root_dir):
    filename = file_path.name
    module_name = file_path.stem
    
    # Try to find class name (Simple heuristic: UltraThing -> UltraThing)
    content = file_path.read_text()
    class_match = re.search(r'class\s+(Ultra\w+)', content)
    class_name = class_match.group(1) if class_match else None
    
    usage_count = 0
    used_by = []
    
    for root, dirs, files in os.walk(root_dir):
        if 'archive' in root: continue
        for f in files:
            if not f.endswith('.py'): continue
            current_file = Path(root) / f
            if current_file.resolve() == file_path.resolve(): continue
            
            try:
                f_content = current_file.read_text()
                # Check for filename import (e.g. from x.ultra_thing import)
                if module_name in f_content:
                    usage_count += 1
                    used_by.append(str(current_file))
                # Check for class usage if known
                elif class_name and class_name in f_content:
                    usage_count += 1
                    used_by.append(str(current_file))
            except Exception:
                continue
                
    return usage_count, used_by

def main():
    root = Path('mahoun')
    ultra_files = get_ultra_files(root)
    
    print(f"Found {len(ultra_files)} ultra files.")
    print("-" * 50)
    
    unused = []
    for f in ultra_files:
        count, users = check_usage(f, root)
        if count == 0:
            print(f"[UNUSED] {f}")
            unused.append(f)
        else:
            print(f"[USED]   {f} (by {len(users)} files)")

if __name__ == '__main__':
    main()
