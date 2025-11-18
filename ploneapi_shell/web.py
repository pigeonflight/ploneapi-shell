"""
Streamlit web interface for Plone API Shell.
Provides a command interface similar to the REPL.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from ploneapi_shell import api

# Get path to logo
_logo_path = Path(__file__).parent.parent / "media" / "plone-logo.png"

# Page config
st.set_page_config(
    page_title="Plone API Shell",
    page_icon=str(_logo_path) if _logo_path.exists() else None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
if "current_path" not in st.session_state:
    st.session_state.current_path = ""
if "base_url" not in st.session_state:
    st.session_state.base_url = api.get_base_url()
if "command_history" not in st.session_state:
    st.session_state.command_history = []


def execute_command(cmd: str, args: List[str], base_url: str, current_path: str) -> Dict[str, Any]:
    """Execute a command and return result."""
    result = {"success": False, "output": None, "error": None, "new_path": current_path}
    
    try:
        if cmd == "pwd":
            result["output"] = current_path if current_path else "/"
            result["success"] = True
            
        elif cmd == "ls":
            url, data = api.fetch(current_path, base_url, {}, {}, no_auth=False)
            items = data.get("items", [])
            result["output"] = {
                "type": "items",
                "items": items,
                "url": url,
            }
            result["success"] = True
            
        elif cmd == "cd":
            if not args:
                result["new_path"] = ""
                result["output"] = "Changed to root"
                result["success"] = True
            elif args[0] == "..":
                if current_path:
                    parts = current_path.rstrip("/").split("/")
                    result["new_path"] = "/".join(parts[:-1]) if len(parts) > 1 else ""
                else:
                    result["output"] = "Already at root"
                result["success"] = True
            else:
                target = args[0].lstrip("/")
                test_path = f"{current_path}/{target}".strip("/") if current_path else target
                url, data = api.fetch(test_path, base_url, {}, {}, no_auth=False)
                result["new_path"] = test_path
                result["output"] = f"Changed to: {data.get('title', data.get('id', test_path))}"
                result["success"] = True
                
        elif cmd == "get":
            path = args[0] if args else current_path
            url, data = api.fetch(path, base_url, {}, {}, no_auth=False)
            result["output"] = {
                "type": "content",
                "data": data,
                "url": url,
            }
            result["success"] = True
            
        elif cmd == "items":
            path = args[0] if args else current_path
            url, data = api.fetch(path, base_url, {}, {}, no_auth=False)
            items = data.get("items")
            if not isinstance(items, list):
                result["error"] = "Response does not contain an 'items' array."
            else:
                result["output"] = {
                    "type": "items",
                    "items": items,
                    "url": url,
                }
                result["success"] = True
                
        elif cmd == "raw":
            path = args[0] if args else current_path
            url, data = api.fetch(path, base_url, {}, {}, no_auth=False)
            result["output"] = {
                "type": "raw",
                "data": data,
                "url": url,
            }
            result["success"] = True
            
        elif cmd == "components":
            url, data = api.fetch(None, base_url, {}, {}, no_auth=False)
            components = data.get("@components", {})
            result["output"] = {
                "type": "components",
                "components": components,
                "url": url,
            }
            result["success"] = True
            
        else:
            result["error"] = f"Unknown command: {cmd}. Type 'help' for available commands."
            
    except api.APIError as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = f"Error: {e}"
    
    return result


def render_output(output: Dict[str, Any]):
    """Render command output in Streamlit."""
    if output["type"] == "items":
        items = output.get("items", [])
        if items:
            # Create DataFrame for table display
            import pandas as pd
            df_data = []
            for item in items:
                df_data.append({
                    "Title": item.get("title", item.get("id", "—")),
                    "Type": item.get("@type", item.get("type_title", "—")),
                    "State": item.get("review_state", "—"),
                    "Modified": item.get("modified", item.get("effective", "—"))[:19] if item.get("modified") else "—",
                })
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No items found")
            
    elif output["type"] == "content":
        data = output.get("data", {})
        # Show summary
        col1, col2 = st.columns(2)
        with col1:
            st.write("**@id:**", data.get("@id", "—"))
            st.write("**@type:**", data.get("@type", "—"))
        with col2:
            st.write("**Title:**", data.get("title", "—"))
            st.write("**State:**", data.get("review_state", "—"))
        
        # Show items if present
        items = data.get("items") or data.get("results")
        if isinstance(items, list) and items:
            st.subheader("Items")
            import pandas as pd
            df_data = []
            for item in items[:20]:  # Limit to 20
                df_data.append({
                    "Title": item.get("title", "—"),
                    "Type": item.get("@type", "—"),
                    "URL": item.get("@id", "—"),
                })
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
    elif output["type"] == "raw":
        st.json(output.get("data", {}))
        
    elif output["type"] == "components":
        components = output.get("components", {})
        import pandas as pd
        df_data = []
        for name, meta in components.items():
            df_data.append({
                "Name": name,
                "Endpoint": meta.get("@id", "—"),
            })
        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)


# Sidebar for configuration
with st.sidebar:
    # Display Plone logo if available
    if _logo_path.exists():
        st.image(str(_logo_path), width=64)
    st.title("Plone API Shell")
    st.caption("Web interface for exploring Plone REST API")
    
    st.divider()
    
    # Base URL configuration
    st.subheader("Configuration")
    base_url_input = st.text_input(
        "API Base URL",
        value=st.session_state.base_url,
        help="Plone API base URL (e.g., https://demo.plone.org/++api++/)",
    )
    if base_url_input != st.session_state.base_url:
        st.session_state.base_url = base_url_input
    
    # Login form
    st.subheader("Authentication")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            try:
                api.login(st.session_state.base_url, username, password)
                st.success("Login successful!")
                st.rerun()
            except api.APIError as e:
                st.error(str(e))
    
    if api.load_config() and api.load_config().get("auth"):
        st.success("✓ Authenticated")
        if st.button("Logout"):
            api.delete_config()
            st.rerun()
    else:
        st.info("Not authenticated")
    
    st.divider()
    
    # Current path display
    st.subheader("Current Path")
    st.code(st.session_state.current_path if st.session_state.current_path else "/")
    
    # Help
    with st.expander("Commands"):
        st.markdown("""
        **Navigation:**
        - `ls` - List items
        - `cd <path>` - Change directory
        - `pwd` - Show current path
        
        **Content:**
        - `get [path]` - Fetch content
        - `items [path]` - List items array
        - `raw [path]` - Show raw JSON
        
        **Other:**
        - `components` - List available components
        - `help` - Show this help
        """)


# Main interface
st.title("Plone API Shell")
st.caption(f"Base URL: `{st.session_state.base_url}`")

# Command input
command_input = st.text_input(
    "Enter command",
    placeholder="ls, cd, get, items, raw, components, help...",
    key="command_input",
)

if command_input:
    # Parse command
    parts = shlex.split(command_input)
    if parts:
        cmd = parts[0].lower()
        args = parts[1:]
        
        if cmd == "help":
            st.info("""
            **Navigation:**
            - `ls` - List items in current directory
            - `cd <path>` - Change directory (use '..' to go up)
            - `pwd` - Show current path
            
            **Content:**
            - `get [path]` - Fetch and display content
            - `items [path]` - List items array
            - `raw [path]` - Show raw JSON
            
            **Other:**
            - `components` - List available components
            """)
        else:
            # Execute command
            result = execute_command(
                cmd,
                args,
                st.session_state.base_url,
                st.session_state.current_path,
            )
            
            # Update path if changed
            if result["new_path"] != st.session_state.current_path:
                st.session_state.current_path = result["new_path"]
            
            # Add to history
            st.session_state.command_history.append({
                "command": command_input,
                "result": result,
            })
            
            # Display result
            if result["success"]:
                if isinstance(result["output"], str):
                    st.success(result["output"])
                elif isinstance(result["output"], dict):
                    render_output(result["output"])
            else:
                st.error(result.get("error", "Unknown error"))
            
            # Show URL if available
            if isinstance(result["output"], dict) and "url" in result["output"]:
                st.caption(f"URL: `{result['output']['url']}`")

# Command history
if st.session_state.command_history:
    with st.expander("Command History", expanded=False):
        for i, entry in enumerate(reversed(st.session_state.command_history[-10:]), 1):
            st.code(entry["command"])
            if entry["result"].get("error"):
                st.error(entry["result"]["error"])

