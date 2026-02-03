# Setting Up n8n MCP Server in Cursor

## Overview

The n8n MCP (Model Context Protocol) server allows Cursor IDE to interact with n8n workflows, enabling AI to create, manage, and trigger n8n workflows directly from Cursor.

---

## Prerequisites

- ✅ Node.js (v14 or higher)
- ✅ Cursor IDE (v0.48 or higher)
- ✅ n8n Cloud account (or self-hosted n8n)
- ✅ n8n API Key

---

## Step 1: Get n8n API Key

1. **Go to n8n Cloud:** https://app.n8n.cloud/
2. **Navigate to Settings → API**
3. **Generate API Key:**
   - Click "Create API Key"
   - Copy the key (you'll need it)
4. **Note your n8n URL:**
   - For Cloud: `https://your-instance.app.n8n.cloud`
   - For Self-hosted: `http://localhost:5678`

---

## Step 2: Create MCP Configuration File

1. **Navigate to your project root:**
   ```powershell
   cd "c:\Users\dutta\Voice-first-AI-travel-planning-assistant-\travel-planner"
   ```

2. **Create `.cursor` directory** (if it doesn't exist):
   ```powershell
   mkdir .cursor
   ```

3. **Create or edit `.cursor/mcp.json`:**
   ```powershell
   notepad .cursor\mcp.json
   ```

---

## Step 3: Add n8n MCP Server Configuration

**Copy this configuration into `.cursor/mcp.json`:**

```json
{
  "mcpServers": {
    "n8n-workflow-builder": {
      "command": "npx",
      "args": [
        "-y",
        "@makafeli/n8n-workflow-builder"
      ],
      "env": {
        "N8N_API_URL": "${N8N_API_URL}",
        "N8N_API_KEY": "${N8N_API_KEY}"
      }
    }
  }
}
```

**Note:** This configuration uses environment variables for security. You'll need to set `N8N_API_URL` and `N8N_API_KEY` in your system environment or `.env` file.

**Alternative (hardcoded values - less secure):**
```json
{
  "mcpServers": {
    "n8n-workflow-builder": {
      "command": "npx",
      "args": [
        "-y",
        "@makafeli/n8n-workflow-builder"
      ],
      "env": {
        "N8N_API_URL": "https://your-instance.app.n8n.cloud",
        "N8N_API_KEY": "your-n8n-api-key-here"
      }
    }
  }
}
```

**Replace:**
- `https://your-instance.app.n8n.cloud` → Your n8n Cloud URL (or `http://localhost:5678` for self-hosted)
- `your-n8n-api-key-here` → Your actual API key

---

## Step 4: Save and Restart Cursor

1. **Save** `.cursor/mcp.json`
2. **Restart Cursor IDE completely:**
   - Close all Cursor windows
   - Reopen Cursor
3. **Wait for MCP server to initialize** (may take a few seconds)

---

## Step 5: Verify Setup

### Option A: Use Verification Script (Recommended)

Run the verification script to check your setup:

```powershell
python verify_n8n_mcp.py
```

This will check:
- ✅ MCP configuration file exists and is valid
- ✅ Node.js is installed
- ✅ Environment variables are set
- ✅ n8n API connectivity (optional)

### Option B: Manual Verification

1. **Open Cursor Chat** (`Ctrl+L` or `Cmd+L`)
2. **Check MCP Status:**
   - Look for n8n-related tools in the chat
   - Try asking: "What n8n workflows do I have?"
3. **Test MCP Commands:**
   - Ask: "List my n8n workflows"
   - Ask: "Create a new n8n workflow"

---

## Step 3.5: Set Environment Variables

Since the configuration uses environment variables, you need to set them. You have two options:

### Option A: Add to `.env` file (Recommended)

Add these lines to your `.env` file in the project root:

```env
N8N_API_URL=https://your-instance.app.n8n.cloud
N8N_API_KEY=your-n8n-api-key-here
```

**Note:** Cursor may not automatically load `.env` files for MCP servers. You may need to set system environment variables instead.

### Option B: Set System Environment Variables (Windows)

**Temporary (current session only):**
```powershell
$env:N8N_API_URL="https://your-instance.app.n8n.cloud"
$env:N8N_API_KEY="your-api-key"
```

**Permanent (system-wide):**
```powershell
[System.Environment]::SetEnvironmentVariable("N8N_API_URL", "https://your-instance.app.n8n.cloud", "User")
[System.Environment]::SetEnvironmentVariable("N8N_API_KEY", "your-api-key", "User")
```

After setting permanent variables, **restart Cursor** for them to take effect.

---

## What You Can Do with n8n MCP

Once set up, you can:

- ✅ **List workflows:** "Show me all my n8n workflows"
- ✅ **Create workflows:** "Create a workflow that sends email"
- ✅ **Update workflows:** "Update workflow X to add PDF generation"
- ✅ **Trigger workflows:** "Run my travel planner workflow"
- ✅ **Monitor executions:** "Show me recent workflow executions"

---

## Troubleshooting

### Issue 1: MCP Server Not Loading

**Solution:**
1. Check Node.js is installed: `node --version`
2. Verify `.cursor/mcp.json` syntax (valid JSON)
3. Check n8n API URL and key are correct
4. Restart Cursor completely

### Issue 2: "Cannot connect to n8n"

**Solution:**
1. Verify n8n API URL is accessible
2. Check API key is valid (regenerate if needed)
3. Ensure n8n instance is running
4. Check firewall/network settings

### Issue 3: MCP Tools Not Appearing

**Solution:**
1. Wait 10-15 seconds after restart
2. Check Cursor version (needs v0.48+)
3. Look in Cursor settings for MCP status
4. Try reloading window: `Ctrl+Shift+P` → "Reload Window"

---

## File Structure

After setup, your project should have:

```
travel-planner/
├── .cursor/
│   └── mcp.json          ← MCP configuration
├── app.py
├── src/
└── ...
```

---

## Quick Reference

**Configuration File:** `.cursor/mcp.json`

**Required:**
- `N8N_API_URL`: Your n8n instance URL
- `N8N_API_KEY`: Your n8n API key

**Package:** `@makafeli/n8n-workflow-builder` (installed via npx)

**GitHub:** https://github.com/makafeli/n8n-workflow-builder

**Features:**
- Create, update, delete workflows
- Activate/deactivate workflows
- List workflows and executions
- Trigger workflows via API
- Validate workflow specifications

**Restart Required:** Yes, after configuration

---

## Next Steps

1. ✅ Configure `.cursor/mcp.json`
2. ✅ Restart Cursor
3. ✅ Test MCP commands
4. ✅ Use AI to manage n8n workflows

---

**Note:** Your project already uses n8n via webhooks (`n8n_client.py`). The MCP server adds the ability to manage workflows from Cursor's AI chat, which is optional but useful for workflow management.
