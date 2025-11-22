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
                target = args[0]
                # Handle full URLs
                if target.startswith(("http://", "https://")):
                    # Extract path from full URL
                    from urllib.parse import urlparse
                    parsed = urlparse(target)
                    # Remove the base URL portion to get relative path
                    if base_url.rstrip("/") in target:
                        target = target.replace(base_url.rstrip("/"), "").lstrip("/")
                    else:
                        # If it's a different domain, extract just the path
                        target = parsed.path.lstrip("/")
                        # Remove ++api++ if present
                        if target.startswith("++api++/"):
                            target = target[8:]
                
                target = target.lstrip("/")
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
            
        elif cmd == "tags":
            path = args[0] if args else current_path
            try:
                tag_counts = api.get_all_tags(base_url, path, no_auth=False)
                result["output"] = {
                    "type": "tags",
                    "tags": tag_counts,
                }
                result["success"] = True
            except api.APIError as e:
                result["error"] = str(e)
            except Exception as e:
                result["error"] = f"Error: {e}"
                
        elif cmd == "merge-tags":
            if len(args) < 2:
                result["error"] = "merge-tags requires two arguments: old_tag new_tag"
            else:
                old_tag, new_tag = args[0], args[1]
                try:
                    items = api.search_by_subject(base_url, old_tag, current_path, no_auth=False)
                    if not items:
                        result["output"] = f"No items found with tag '{old_tag}'."
                        result["success"] = True
                    else:
                        result["output"] = {
                            "type": "merge_preview",
                            "old_tag": old_tag,
                            "new_tag": new_tag,
                            "items": items,
                            "count": len(items),
                        }
                        result["success"] = True
                except Exception as e:
                    result["error"] = f"Error: {e}"
                    
        elif cmd == "rename-tag":
            if len(args) < 2:
                result["error"] = "rename-tag requires two arguments: old_tag new_tag"
            else:
                # Same as merge-tags for now
                old_tag, new_tag = args[0], args[1]
                try:
                    items = api.search_by_subject(base_url, old_tag, current_path, no_auth=False)
                    if not items:
                        result["output"] = f"No items found with tag '{old_tag}'."
                        result["success"] = True
                    else:
                        result["output"] = {
                            "type": "rename_preview",
                            "old_tag": old_tag,
                            "new_tag": new_tag,
                            "items": items,
                            "count": len(items),
                        }
                        result["success"] = True
                except Exception as e:
                    result["error"] = f"Error: {e}"
                    
        elif cmd == "remove-tag":
            if not args:
                result["error"] = "remove-tag requires a tag name"
            else:
                tag = args[0]
                try:
                    items = api.search_by_subject(base_url, tag, current_path, no_auth=False)
                    if not items:
                        result["output"] = f"No items found with tag '{tag}'."
                        result["success"] = True
                    else:
                        result["output"] = {
                            "type": "remove_preview",
                            "tag": tag,
                            "items": items,
                            "count": len(items),
                        }
                        result["success"] = True
                except Exception as e:
                    result["error"] = f"Error: {e}"
            
        else:
            result["error"] = f"Unknown command: {cmd}. Type 'help' for available commands."
            
    except api.APIError as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = f"Error: {e}"
    
    return result


def render_output(output: Dict[str, Any]):
    """Render command output in Streamlit."""
    if output.get("type") == "help":
        st.info(output.get("content", ""))
    elif output["type"] == "items":
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
        
    elif output["type"] == "tags":
        tags = output.get("tags", {})
        if not tags:
            st.info("No tags found")
        else:
            import pandas as pd
            sorted_tags = sorted(tags.items(), key=lambda x: (-x[1], x[0].lower()))
            df_data = [{"Tag": tag, "Count": count} for tag, count in sorted_tags]
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
    elif output["type"] in ("merge_preview", "rename_preview", "remove_preview"):
        items = output.get("items", [])
        count = output.get("count", 0)
        if output["type"] == "merge_preview":
            st.warning(f"Found {count} item(s) with tag '{output['old_tag']}'. Use the form below to merge into '{output['new_tag']}'.")
        elif output["type"] == "rename_preview":
            st.warning(f"Found {count} item(s) with tag '{output['old_tag']}'. Use the form below to rename to '{output['new_tag']}'.")
        else:
            st.warning(f"Found {count} item(s) with tag '{output['tag']}'. Use the form below to remove it.")
        
        # Show preview of items
        if items:
            import pandas as pd
            df_data = []
            for item in items[:20]:
                df_data.append({
                    "Title": item.get("title", item.get("id", "—")),
                    "Type": item.get("@type", "—"),
                    "Current Tags": ", ".join(item.get("subjects", [])),
                })
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            if len(items) > 20:
                st.caption(f"... and {len(items) - 20} more items")


# Sidebar for configuration
with st.sidebar:
    # Display Plone logo if available
    if _logo_path.exists():
        st.image(str(_logo_path), width=64)
    st.title("Plone API Shell")
    st.caption("Web interface for exploring Plone REST API")
    
    # Mention desktop alternative
    st.info("💡 **Prefer point-and-click?** Try [Ploa](https://ploa.incrementic.com) - a desktop application designed for graphical interfaces.")
    
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
        
        **Tags:**
        - `tags [path]` - List all tags with frequency
        - `merge-tags <old> <new>` - Merge two tags
        - `rename-tag <old> <new>` - Rename a tag
        - `remove-tag <tag>` - Remove a tag
        
        **Other:**
        - `components` - List available components
        - `help` - Show this help
        """)


# Add CSS for chat-like interface (like mobile chat apps)
st.markdown("""
<style>
    /* Hide Streamlit header/footer */
    header[data-testid="stHeader"] {
        display: none !important;
    }
    
    footer {
        display: none !important;
    }
    
    /* Prevent body scrolling */
    body, html, #root {
        overflow: hidden !important;
        height: 100vh !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    
    /* Main app container - full viewport */
    .main {
        height: 100vh !important;
        overflow: hidden !important;
        display: flex !important;
        flex-direction: column !important;
    }
    
    /* Block container - no padding, full height */
    .main .block-container {
        padding: 0 !important;
        max-width: 100% !important;
        height: 100vh !important;
        display: flex !important;
        flex-direction: column !important;
        overflow: hidden !important;
    }
    
    /* Title bar - fixed at top */
    .chat-title {
        padding: 1rem !important;
        background: white !important;
        border-bottom: 1px solid #e0e0e0 !important;
        flex-shrink: 0 !important;
        z-index: 100 !important;
    }
    
    /* Chat output area - scrollable, fills remaining space */
    .chat-output-area {
        flex: 1 1 auto !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        padding: 1rem !important;
        background: #fafafa !important;
        /* Reserve space for fixed input */
        padding-bottom: 90px !important;
        min-height: 0 !important;
    }
    
    /* Chat message styling */
    .chat-message {
        margin-bottom: 1rem !important;
        padding: 0.75rem 1rem !important;
        border-radius: 8px !important;
        background: white !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1) !important;
    }
    
    .chat-command {
        font-family: monospace !important;
        font-weight: bold !important;
        color: #1f77b4 !important;
        margin-bottom: 0.5rem !important;
    }
    
    /* Fixed input area - always at viewport bottom */
    .chat-input-area {
        position: fixed !important;
        bottom: 0 !important;
        left: 0 !important;
        right: 0 !important;
        background: white !important;
        padding: 1rem !important;
        border-top: 2px solid #e0e0e0 !important;
        z-index: 9999 !important;
        box-shadow: 0 -2px 10px rgba(0,0,0,0.1) !important;
        /* Remove from document flow */
        position: fixed !important;
    }
    
    /* Account for sidebar width */
    section[data-testid="stSidebar"] ~ .main .chat-input-area {
        left: var(--sidebar-width, 0px) !important;
    }
    
    /* Ensure Streamlit elements don't interfere */
    .element-container {
        position: relative !important;
    }
</style>
""", unsafe_allow_html=True)

# Chat-like interface
st.markdown(f'''
<div class="chat-title">
    <h1>Plone API Shell</h1>
    <p style="margin:0;color:#666;">Base URL: <code>{st.session_state.base_url}</code></p>
    <p style="margin:0.5rem 0 0 0;font-size:0.85em;color:#888;">
        💡 Prefer point-and-click? Try <a href="https://ploa.incrementic.com" target="_blank" style="color:#1f77b4;">Ploa</a> - a desktop application for graphical interfaces.
    </p>
</div>
''', unsafe_allow_html=True)

# Create scrollable chat output area
st.markdown('<div class="chat-output-area" id="chat-output">', unsafe_allow_html=True)

# Display command history in chronological order (oldest to newest, like chat)
if st.session_state.command_history:
    for entry in st.session_state.command_history:
        # Chat message container
        st.markdown('<div class="chat-message">', unsafe_allow_html=True)
        
        # Show command
        st.markdown(f'<div class="chat-command">$ {entry["command"]}</div>', unsafe_allow_html=True)
        
        # Show result
        result = entry["result"]
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
        
        st.markdown('</div>', unsafe_allow_html=True)
else:
    # Welcome message when no commands yet
    st.markdown('<div class="chat-message"><p style="color:#666;margin:0;">Type a command to get started. Try <code>ls</code> or <code>help</code></p></div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# Reset command input if flagged (must happen before widget instantiation)
if st.session_state.get("command_input_reset"):
    st.session_state.command_input = ""
    st.session_state.command_input_reset = False

# Create a placeholder for the input that will be moved by JavaScript
st.markdown('<div id="input-placeholder" style="height: 80px;"></div>', unsafe_allow_html=True)

# Command input (will be moved to fixed position by JavaScript)
command_input = st.text_input(
    "Enter command",
    placeholder="Type a command (e.g., ls, cd, get, help)...",
    key="command_input",
    label_visibility="collapsed",
)

# JavaScript to move input to fixed position and maintain chat interface
st.markdown("""
<script>
    (function() {
        function setupChatInterface() {
            // Find the text input widget
            const inputs = document.querySelectorAll('div[data-testid="stTextInput"]');
            let commandInput = null;
            
            inputs.forEach(input => {
                const label = input.querySelector('label');
                if (label && label.textContent.includes('Enter command')) {
                    commandInput = input;
                }
            });
            
            // If not found by label, use the last one
            if (!commandInput && inputs.length > 0) {
                commandInput = inputs[inputs.length - 1];
            }
            
            if (commandInput) {
                // Find the element-container parent
                let container = commandInput.closest('.element-container');
                if (!container) {
                    container = commandInput.parentElement;
                }
                
                if (container) {
                    // Create fixed input area if it doesn't exist
                    let fixedArea = document.getElementById('fixed-command-input');
                    if (!fixedArea) {
                        fixedArea = document.createElement('div');
                        fixedArea.id = 'fixed-command-input';
                        fixedArea.className = 'chat-input-area';
                        document.body.appendChild(fixedArea);
                    }
                    
                    // Move the input container to fixed area
                    if (container.parentElement !== fixedArea) {
                        fixedArea.innerHTML = '';
                        fixedArea.appendChild(container);
                    }
                    
                    // Ensure fixed positioning
                    fixedArea.style.position = 'fixed';
                    fixedArea.style.bottom = '0';
                    fixedArea.style.left = '0';
                    fixedArea.style.right = '0';
                    fixedArea.style.background = 'white';
                    fixedArea.style.padding = '1rem';
                    fixedArea.style.borderTop = '2px solid #e0e0e0';
                    fixedArea.style.zIndex = '9999';
                    fixedArea.style.boxShadow = '0 -2px 10px rgba(0,0,0,0.1)';
                    
                    // Adjust for sidebar
                    const sidebar = document.querySelector('section[data-testid="stSidebar"]');
                    if (sidebar) {
                        const sidebarWidth = sidebar.offsetWidth || 0;
                        fixedArea.style.left = sidebarWidth + 'px';
                    } else {
                        fixedArea.style.left = '0';
                    }
                }
            }
            
            // Auto-scroll output to bottom
            const chatOutput = document.getElementById('chat-output');
            if (chatOutput) {
                chatOutput.scrollTop = chatOutput.scrollHeight;
            }
        }
        
        // Run immediately and repeatedly
        setupChatInterface();
        setTimeout(setupChatInterface, 50);
        setTimeout(setupChatInterface, 100);
        setTimeout(setupChatInterface, 200);
        setTimeout(setupChatInterface, 500);
        setTimeout(setupChatInterface, 1000);
        
        // Watch for DOM changes
        const observer = new MutationObserver(() => {
            setTimeout(setupChatInterface, 50);
        });
        
        // Observe everything
        observer.observe(document.body, { 
            childList: true, 
            subtree: true,
            attributes: true
        });
        
        // Handle window resize
        window.addEventListener('resize', setupChatInterface);
        
        // Handle sidebar toggle
        const sidebar = document.querySelector('section[data-testid="stSidebar"]');
        if (sidebar) {
            const sidebarObserver = new MutationObserver(() => {
                setTimeout(setupChatInterface, 100);
            });
            sidebarObserver.observe(sidebar, { 
                attributes: true, 
                attributeFilter: ['class', 'style'],
                childList: true
            });
        }
    })();
</script>
""", unsafe_allow_html=True)

if command_input:
    # Parse command
    parts = shlex.split(command_input)
    if parts:
        cmd = parts[0].lower()
        args = parts[1:]
        
        if cmd == "help":
            help_output = {
                "type": "help",
                "content": """
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
                """
            }
            result = {
                "success": True,
                "output": help_output,
                "error": None,
                "new_path": st.session_state.current_path,
            }
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
        # Flag clearing of input on next rerun
        st.session_state.command_input_reset = True
        # Rerun to show the new command in history
        st.rerun()

