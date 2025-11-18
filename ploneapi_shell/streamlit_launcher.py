#!/usr/bin/env python3
"""
Launcher script for the packaged Streamlit app.
This is used by PyInstaller to create a standalone executable.
"""

import sys
import os
from pathlib import Path

def main():
    """Launch the Streamlit web interface."""
    # Get the directory where the executable is located
    if getattr(sys, 'frozen', False):
        # Running as a PyInstaller bundle
        base_path = Path(sys._MEIPASS)
        # Try multiple possible locations
        possible_paths = [
            base_path / "ploneapi_shell" / "web.py",
            base_path / "web.py",
        ]
        web_file = None
        for path in possible_paths:
            if path.exists():
                web_file = path
                break
        
        if web_file is None:
            # Search for web.py in the bundle
            for root, dirs, files in os.walk(base_path):
                if "web.py" in files:
                    web_file = Path(root) / "web.py"
                    break
        
        if web_file is None:
            print(f"Error: Could not find web.py in bundle")
            print(f"Searched in: {base_path}")
            # List what's actually in the bundle for debugging
            print(f"\nContents of {base_path}:")
            try:
                for item in base_path.iterdir():
                    print(f"  {item.name} ({'dir' if item.is_dir() else 'file'})")
            except Exception as e:
                print(f"  Error listing: {e}")
            sys.exit(1)
    else:
        # Running as a normal Python script
        base_path = Path(__file__).parent
        web_file = base_path / "web.py"
    
    if not web_file.exists():
        print(f"Error: Could not find web.py at {web_file}")
        sys.exit(1)
    
    # Import and run streamlit programmatically
    # This is more reliable than subprocess for bundled apps
    try:
        import streamlit.web.cli as stcli
        
        # Set up streamlit configuration
        # Don't set headless - we want the browser to open
        os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'
        
        # Run streamlit - it will automatically open the browser
        sys.argv = ['streamlit', 'run', str(web_file)]
        stcli.main()
    except ImportError:
        # Fallback to subprocess if programmatic import fails
        import subprocess
        cmd = [
            sys.executable, "-m", "streamlit", "run",
            str(web_file),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ]
        
        if len(sys.argv) > 1:
            cmd.extend(sys.argv[1:])
        
        try:
            subprocess.run(cmd, check=True)
        except KeyboardInterrupt:
            print("\nShutting down...")
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            print(f"Error running Streamlit: {e}")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

