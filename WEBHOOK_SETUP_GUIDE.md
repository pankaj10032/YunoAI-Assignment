# Telegram Webhook Setup Guide

## Why Use Webhooks?

**Polling Mode (Current):**
- ✅ Easy to set up (already working)
- ✅ Works on localhost
- ❌ Backend constantly checks for new messages
- ❌ Higher latency
- ❌ More resource intensive

**Webhook Mode:**
- ✅ Telegram pushes messages to your server instantly
- ✅ Lower latency
- ✅ More efficient
- ❌ Requires public HTTPS URL
- ❌ More complex setup for local dev

---

## Option 1: Using ngrok (Recommended for Local Testing)

### Step 1: Install ngrok

**Download and Install:**
1. Go to https://ngrok.com/download
2. Download ngrok for Windows
3. Extract the ZIP file
4. (Optional) Sign up for a free account at https://dashboard.ngrok.com/signup
5. Get your auth token from https://dashboard.ngrok.com/get-started/your-authtoken

**Setup ngrok:**
```bash
# Navigate to where you extracted ngrok
cd C:\path\to\ngrok

# Authenticate (optional but recommended)
ngrok config add-authtoken YOUR_AUTH_TOKEN

# Start ngrok tunnel to your backend
ngrok http 8000
```

### Step 2: Get Your Public URL

After running `ngrok http 8000`, you'll see output like:
```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok-free.app`)

### Step 3: Set the Webhook

**Method A: Using the API endpoint**
```bash
curl -X POST http://localhost:8000/api/channels/telegram/webhook/set ^
  -H "Content-Type: application/json" ^
  -d "{\"webhook_url\":\"https://abc123.ngrok-free.app/api/channels/telegram/webhook\"}"
```

**Method B: Using Telegram API directly**
```bash
curl -X POST "https://api.telegram.org/bot8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q/setWebhook" ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://abc123.ngrok-free.app/api/channels/telegram/webhook\"}"
```

### Step 4: Verify Webhook is Set

```bash
curl "https://api.telegram.org/bot8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q/getWebhookInfo"
```

You should see:
```json
{
  "ok": true,
  "result": {
    "url": "https://abc123.ngrok-free.app/api/channels/telegram/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

### Step 5: Update .env to Disable Polling

Edit your `.env` file:
```env
ENABLE_TELEGRAM_POLLING=false
TELEGRAM_WEBHOOK_URL=https://abc123.ngrok-free.app/api/channels/telegram/webhook
```

### Step 6: Restart Backend

```bash
docker-compose restart backend
```

### Step 7: Test

Send a message to your bot in Telegram. You should see the webhook request in:
- ngrok web interface: http://127.0.0.1:4040
- Backend logs: `docker-compose logs backend -f`

---

## Option 2: Using Other Tunneling Services

### LocalTunnel
```bash
npm install -g localtunnel
lt --port 8000 --subdomain mybot
```

### Cloudflare Tunnel
```bash
# Install cloudflared
# Then run:
cloudflared tunnel --url http://localhost:8000
```

---

## Option 3: Deploy to Production (For Production Use)

### Deploy to Render, Railway, or Heroku

1. **Push your code to GitHub**

2. **Deploy to Render:**
   - Go to https://render.com
   - Create new Web Service
   - Connect your GitHub repo
   - Set environment variables from `.env`
   - Deploy

3. **Get your production URL** (e.g., `https://mybot.onrender.com`)

4. **Set webhook:**
```bash
curl -X POST "https://api.telegram.org/bot8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q/setWebhook" ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://mybot.onrender.com/api/channels/telegram/webhook\"}"
```

---

## Quick Setup Script for ngrok

Save as `setup_webhook.ps1`:

```powershell
# Telegram Webhook Setup with ngrok

$botToken = "8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Telegram Webhook Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if ngrok is running
Write-Host "Checking for ngrok tunnel..." -ForegroundColor Yellow
try {
    $ngrokApi = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -UseBasicParsing
    $publicUrl = $ngrokApi.tunnels[0].public_url
    
    if ($publicUrl) {
        Write-Host "✓ Found ngrok tunnel: $publicUrl" -ForegroundColor Green
    } else {
        throw "No tunnel found"
    }
} catch {
    Write-Host "✗ ngrok is not running!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please start ngrok first:" -ForegroundColor Yellow
    Write-Host "  ngrok http 8000" -ForegroundColor Cyan
    Write-Host ""
    exit
}

# Construct webhook URL
$webhookUrl = "$publicUrl/api/channels/telegram/webhook"
Write-Host "Webhook URL: $webhookUrl" -ForegroundColor Cyan
Write-Host ""

# Set webhook
Write-Host "Setting webhook..." -ForegroundColor Yellow
$setWebhookUrl = "https://api.telegram.org/bot$botToken/setWebhook"
$body = @{
    url = $webhookUrl
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri $setWebhookUrl -Method Post -Body $body -ContentType "application/json" -UseBasicParsing
    
    if ($response.ok) {
        Write-Host "✓ Webhook set successfully!" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to set webhook: $($response.description)" -ForegroundColor Red
    }
} catch {
    Write-Host "✗ Error: $_" -ForegroundColor Red
}

Write-Host ""

# Verify webhook
Write-Host "Verifying webhook..." -ForegroundColor Yellow
$getWebhookUrl = "https://api.telegram.org/bot$botToken/getWebhookInfo"

try {
    $info = Invoke-RestMethod -Uri $getWebhookUrl -UseBasicParsing
    
    if ($info.ok) {
        Write-Host "✓ Webhook Info:" -ForegroundColor Green
        Write-Host "  URL: $($info.result.url)" -ForegroundColor Cyan
        Write-Host "  Pending Updates: $($info.result.pending_update_count)" -ForegroundColor Cyan
        Write-Host "  Last Error: $($info.result.last_error_message)" -ForegroundColor $(if ($info.result.last_error_message) { "Red" } else { "Green" })
    }
} catch {
    Write-Host "✗ Error getting webhook info: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Next Steps:" -ForegroundColor Green
Write-Host "1. Update .env: ENABLE_TELEGRAM_POLLING=false" -ForegroundColor White
Write-Host "2. Restart backend: docker-compose restart backend" -ForegroundColor White
Write-Host "3. Monitor ngrok: http://127.0.0.1:4040" -ForegroundColor White
Write-Host "4. Send a test message to your bot" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
```

---

## Troubleshooting

### Webhook not receiving messages?

1. **Check webhook status:**
```bash
curl "https://api.telegram.org/bot8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q/getWebhookInfo"
```

2. **Check for errors in webhook info:**
Look for `last_error_message` in the response

3. **Verify ngrok is running:**
Visit http://127.0.0.1:4040 to see incoming requests

4. **Check backend logs:**
```bash
docker-compose logs backend -f
```

5. **Test webhook endpoint directly:**
```bash
curl https://your-ngrok-url.ngrok-free.app/api/channels/telegram/webhook
```

### Remove webhook (go back to polling):

```bash
curl -X POST "https://api.telegram.org/bot8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q/deleteWebhook"
```

Then update `.env`:
```env
ENABLE_TELEGRAM_POLLING=true
TELEGRAM_WEBHOOK_URL=
```

And restart:
```bash
docker-compose restart backend
```

---

## Comparison: Polling vs Webhook

| Feature | Polling (Current) | Webhook |
|---------|------------------|---------|
| Setup Complexity | ✅ Easy | ⚠️ Medium |
| Local Development | ✅ Works | ⚠️ Needs tunnel |
| Latency | ⚠️ 1-3 seconds | ✅ Instant |
| Resource Usage | ⚠️ Higher | ✅ Lower |
| Production Ready | ✅ Yes | ✅ Yes |
| Recommended For | Development | Production |

---

## Recommendation

**For Local Development:** Keep using polling mode (already working)

**For Production:** Use webhooks with a proper deployment (Render, Railway, etc.)

**For Testing Webhooks Locally:** Use ngrok
