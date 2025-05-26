import sys
import os

# Add the 'backend' directory to sys.path explicitly
backend_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

print(f"sys.path for this test: {sys.path}\n")

# --- Test 1: Import 'backend' as a top-level package ---
try:
    import backend
    print("Test 1 SUCCESS: Successfully imported 'backend' as a package.")
except ImportError as e:
    print(f"Test 1 FAILURE: Could not import 'backend' itself: {e}")

print("-" * 30)

# --- Test 2: Import a module from within 'backend' package structure ---
try:
    from backend.utils import resume_parser
    print("Test 2 SUCCESS: Successfully imported 'backend.utils.resume_parser'.")
except ImportError as e:
    print(f"Test 2 FAILURE: Could not import backend.utils.resume_parser: {e}")

print("-" * 30)

# --- Test 3: Import a sub-package from the 'backend' package structure ---
try:
    from backend import routes
    print("Test 3 SUCCESS: Successfully imported 'backend.routes'.")
except ImportError as e:
    print(f"Test 3 FAILURE: Could not import backend.routes: {e}")