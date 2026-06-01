# Telegram Integration Testing Guide

## Current Status
✅ **Telegram is configured and running!**
- Configured: `true`
- Connected: `true`
- Polling: `true` (actively listening for messages)

---

## Prerequisites
1. Your Telegram bot token is already configured in `.env`
2. Bot token: `8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q`
3. Backend is running on `http://localhost:8000`

---

## Testing Steps

### Step 1: Find Your Telegram Bot

1. Open Telegram app (mobile or desktop)
2. Search for your bot using the bot username
   - You can find the username by visiting: https://t.me/botfather
   - Or search for the bot token in BotFather to get the username

3. Start a conversation with your bot by clicking **"Start"** or sending `/start`

### Step 2: Get Your Chat ID

When you send a message to your bot, you need to get your Chat ID. You can:

**Option A: Check backend logs**
```bash
docker-compose logs backend --tail=50 | findstr "telegram"
```

**Option B: Use Telegram API directly**
```bash
curl https://api.telegram.org/bot8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q/getUpdates
```

This will show recent messages and your `chat_id`.

### Step 3: Create an Agent (if you don't have one)

```bash
curl -X POST http://localhost:8000/agents ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"Telegram Test Agent\",\"model\":\"gpt-4o-mini\",\"system_prompt\":\"You are a helpful AI assistant.\",\"channels\":[\"telegram\"],\"guardrails\":{}}"
```

Note the `agent_id` from the response (e.g., `"id": 1`).

### Step 4: Connect Agent to Your Telegram Chat

Replace `AGENT_ID` and `YOUR_CHAT_ID` with actual values:

```bash
curl -X POST http://localhost:8000/api/channels/telegram/connect ^
  -H "Content-Type: application/json" ^
  -d "{\"agent_id\":1,\"chat_id\":\"YOUR_CHAT_ID\"}"
```

Example:
```bash
curl -X POST http://localhost:8000/api/channels/telegram/connect ^
  -H "Content-Type: application/json" ^
  -d "{\"agent_id\":1,\"chat_id\":\"123456789\"}"
```

### Step 5: Test the Bot

1. **Send a message** to your bot in Telegram
   - Example: "Hello, can you help me?"

2. **Check if the bot responds**
   - The agent should process your message and reply

3. **Monitor backend logs** to see the interaction:
```bash
docker-compose logs backend -f
```

---

## Testing Scenarios

### Test 1: Basic Conversation
1. Send: "Hello!"
2. Expected: Bot responds with a greeting

### Test 2: Task Execution
1. Send: "What's 25 * 4?"
2. Expected: Bot calculates and responds with "100"

### Test 3: Multi-turn Conversation
1. Send: "My name is John"
2. Send: "What's my name?"
3. Expected: Bot remembers and says "John"

### Test 4: Agent Execution via API
```bash
curl -X POST http://localhost:8000/api/agents/1/execute ^
  -H "Content-Type: application/json" ^
  -d "{\"task_description\":\"Send a greeting to the Telegram user\"}"
```

---

## Useful API Endpoints for Testing

### 1. Check Telegram Status
```bash
curl http://localhost:8000/api/channels/telegram/status
```

### 2. List All Agents
```bash
curl http://localhost:8000/api/agents
```

### 3. Get Agent Details
```bash
curl http://localhost:8000/agents/1
```

### 4. View Messages
```bash
curl http://localhost:8000/api/messages?channel=telegram
```

### 5. Send Message Directly (if endpoint exists)
```bash
curl -X POST http://localhost:8000/api/channels/telegram/send ^
  -H "Content-Type: application/json" ^
  -d "{\"chat_id\":\"YOUR_CHAT_ID\",\"text\":\"Test message from API\"}"
```

---

## Troubleshooting

### Bot doesn't respond?

1. **Check logs:**
```bash
docker-compose logs backend --tail=100
```

2. **Verify bot token:**
```bash
curl https://api.telegram.org/bot8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q/getMe
```

3. **Check if polling is active:**
```bash
curl http://localhost:8000/api/channels/telegram/status
```

4. **Restart containers:**
```bash
docker-compose restart backend
```

### Can't find Chat ID?

Use this command to see recent updates:
```bash
curl https://api.telegram.org/bot8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q/getUpdates
```

Look for `"chat":{"id":123456789}` in the response.

### Agent not connected?

Make sure you've run the connect command:
```bash
curl -X POST http://localhost:8000/api/channels/telegram/connect ^
  -H "Content-Type: application/json" ^
  -d "{\"agent_id\":1,\"chat_id\":\"YOUR_CHAT_ID\"}"
```

---

## Advanced Testing

### Test Webhook Mode (Alternative to Polling)

1. **Set webhook URL:**
```bash
curl -X POST http://localhost:8000/api/channels/telegram/webhook/set ^
  -H "Content-Type: application/json" ^
  -d "{\"webhook_url\":\"https://your-domain.com/api/channels/telegram/webhook\"}"
```

Note: Requires a public HTTPS URL. For local testing, use polling mode (already enabled).

### Test with Multiple Agents

1. Create multiple agents
2. Connect each to different chat IDs
3. Test concurrent conversations

---

## Quick Test Script

Save this as `test_telegram.ps1`:

```powershell
# Get bot info
Write-Host "=== Bot Info ===" -ForegroundColor Green
curl https://api.telegram.org/bot8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q/getMe

# Get recent updates (to find chat_id)
Write-Host "`n=== Recent Updates ===" -ForegroundColor Green
curl https://api.telegram.org/bot8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q/getUpdates

# Check Telegram status
Write-Host "`n=== Telegram Status ===" -ForegroundColor Green
curl http://localhost:8000/api/channels/telegram/status

# List agents
Write-Host "`n=== Agents ===" -ForegroundColor Green
curl http://localhost:8000/api/agents
```

Run with: `powershell -File test_telegram.ps1`

---

## Expected Behavior

When everything is working:
1. ✅ You send a message to the bot in Telegram
2. ✅ Backend logs show "telegram webhook received" or polling detects the message
3. ✅ Agent processes the message using the LLM (OpenAI GPT-4o-mini)
4. ✅ Bot sends a response back to you in Telegram
5. ✅ Message history is stored in the database

---

## Next Steps

After basic testing works:
- Test with different agent configurations
- Try multi-agent workflows
- Test scheduled messages
- Integrate with other channels
- Test error handling and edge cases
