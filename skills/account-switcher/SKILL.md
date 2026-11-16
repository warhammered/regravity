---
name: account-switcher
description: Manage and switch between multiple Antigravity Google accounts and profiles. Supports instant in-place session hot-swapping without restarting Antigravity, isolated parallel profiles, direct OAuth authentication, session inspection, and smart detection.
---

# Paragravity Account Switcher

Native Multi-Account & Isolated Parallel Profile Manager for Google Antigravity.
100% Zero-Proxy, 100% Google Terms of Service Compliant.

## Quick Actions

- **List Accounts**:
  ```powershell
  python ~/.gemini/config/plugins/paragravity/session_swap.py --list
  ```

- **Hot-Swap In-Place (Current Window)**:
  ```powershell
  python ~/.gemini/config/plugins/paragravity/session_swap.py <email_or_name>
  ```

- **Launch Parallel Isolated Window**:
  ```powershell
  python ~/.gemini/config/plugins/paragravity/session_swap.py --launch <email_or_name>
  ```

- **Connect / Authenticate New Google Account**:
  ```powershell
  python ~/.gemini/config/plugins/paragravity/session_swap.py --auth [email_hint]
  ```

- **Import Active Host Session**:
  ```powershell
  python ~/.gemini/config/plugins/paragravity/session_swap.py --import-active
  ```

- **Inspect Session Data & Quotas**:
  ```powershell
  python ~/.gemini/config/plugins/paragravity/session_swap.py --inspect <email_or_name>
  ```

- **Smart Detect Accounts across System**:
  ```powershell
  python ~/.gemini/config/plugins/paragravity/session_swap.py --detect
  ```

- **Reset Profile Sandbox Data**:
  ```powershell
  python ~/.gemini/config/plugins/paragravity/session_swap.py --reset <email_or_name>
  ```

- **Remove Account & Profile**:
  ```powershell
  python ~/.gemini/config/plugins/paragravity/session_swap.py --remove <email_or_name>
  ```

## Engineering Invariants
1. **Zero-Proxy Architecture**: Interacts directly with Google's official endpoints (`oauth2.googleapis.com`) using standard OAuth refresh tokens. Never proxies, modifies, or intercepts LLM traffic.
2. **Stateless UI**: Rendered directly in Electron In-DOM without any background Node HTTP servers, child process sandboxing issues, or open ports.
3. **Onboarding & Terms Modal Suppression**: Injects `app_storage.json`, `antigravity_state.pbtxt`, and workspace references into isolated sandboxes so newly opened windows launch directly into the IDE without introductory prompts.
4. **Conversation Inheritance**: Links conversations via Windows directory junctions (`mklink /J`) for instant multi-window access with zero disk overhead.
5. **Headless MCP Isolation**: Disables interactive remote MCP servers in profile sandboxes to eliminate unwanted automatic browser popups.
