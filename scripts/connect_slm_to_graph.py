"""
Auto-fixed: Removed hardcoded path hacks.
Run with: pip install -e . (to install mahoun as editable package)
"""
import sys
from pathlib import Path

# Portable repo-root discovery (only if needed for non-installed runs)
if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

