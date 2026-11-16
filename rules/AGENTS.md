# Account Switcher Operational Rules

## Autonomous Intent Routing
Whenever the user asks to switch accounts, launch another Antigravity profile, add/connect accounts, inspect session health, reset profiles, or list profiles:
1. Autonomously inspect accounts using `python ~/.gemini/config/plugins/paragravity/session_swap.py --list`.
2. To switch the active logged-in Google account in-place, execute `python ~/.gemini/config/plugins/paragravity/session_swap.py <email>` and reload the window.
3. If the user explicitly asks to run an isolated parallel window, execute `python ~/.gemini/config/plugins/paragravity/session_swap.py --launch <name>`.
4. If the user wants to authenticate, re-authenticate, or connect a Google account, execute `python ~/.gemini/config/plugins/paragravity/session_swap.py --auth [email_hint]`.
5. If the user wants to inspect session lifetime, tokens, quotas, or sandbox size, execute `python ~/.gemini/config/plugins/paragravity/session_swap.py --inspect <email>`.
6. If the user wants to scan for unmanaged accounts across Windows Credential Manager and system files, execute `python ~/.gemini/config/plugins/paragravity/session_swap.py --detect`.
7. Ensure all operations adhere strictly to the Zero-Proxy, 100% Google Terms of Service compliant protocol.
