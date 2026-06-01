# Telegram Bot Testing Script
# This script helps you test your Telegram bot integration

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Telegram Bot Testing Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$botToken = "8607688418:AAF7Iv0xbH8DRizxeSH1URegzGYhxhWJ47Q"
$backendUrl = "http://localhost:8000"

# Function to make API calls
function Invoke-ApiCall {
    param($url, $method = "GET", $body = $null)
    try {
        if ($body) {
            $response = Invoke-RestMethod -Uri $url -Method $method -Body $body -ContentType "application/json" -UseBasicParsing
        } else {
            $response = Invoke-RestMethod -Uri $url -Method $method -UseBasicParsing
        }
        return $response
    } catch {
        Write-Host "Error: $_" -ForegroundColor Red
        return $null
    }
}

# 1. Check Bot Info
Write-Host "1. Checking Bot Information..." -ForegroundColor Yellow
$botInfo = Invoke-ApiCall "https://api.telegram.org/bot$botToken/getMe"
if ($botInfo.ok) {
    Write-Host "   ✓ Bot Username: @$($botInfo.result.username)" -ForegroundColor Green
    Write-Host "   ✓ Bot Name: $($botInfo.result.first_name)" -ForegroundColor Green
    Write-Host "   ✓ Bot ID: $($botInfo.result.id)" -ForegroundColor Green
} else {
    Write-Host "   ✗ Failed to get bot info" -ForegroundColor Red
    exit
}
Write-Host ""

# 2. Check Backend Telegram Status
Write-Host "2. Checking Backend Telegram Status..." -ForegroundColor Yellow
$status = Invoke-ApiCall "$backendUrl/api/channels/telegram/status"
if ($status) {
    Write-Host "   ✓ Configured: $($status.configured)" -ForegroundColor Green
    Write-Host "   ✓ Connected: $($status.connected)" -ForegroundColor Green
    Write-Host "   ✓ Polling: $($status.polling)" -ForegroundColor Green
} else {
    Write-Host "   ✗ Failed to get status" -ForegroundColor Red
}
Write-Host ""

# 3. Get Recent Updates (to find chat_id)
Write-Host "3. Getting Recent Updates (to find your Chat ID)..." -ForegroundColor Yellow
$updates = Invoke-ApiCall "https://api.telegram.org/bot$botToken/getUpdates"
if ($updates.ok -and $updates.result.Count -gt 0) {
    Write-Host "   ✓ Found $($updates.result.Count) recent message(s)" -ForegroundColor Green
    $latestUpdate = $updates.result[-1]
    $chatId = $latestUpdate.message.chat.id
    $username = $latestUpdate.message.from.username
    $firstName = $latestUpdate.message.from.first_name
    
    Write-Host "   ✓ Latest Chat ID: $chatId" -ForegroundColor Green
    Write-Host "   ✓ User: $firstName (@$username)" -ForegroundColor Green
    Write-Host "   ✓ Last Message: $($latestUpdate.message.text)" -ForegroundColor Green
    
    # Save chat_id for later use
    $global:chatId = $chatId
} else {
    Write-Host "   ⚠ No recent messages found" -ForegroundColor Yellow
    Write-Host "   → Please send a message to your bot in Telegram first!" -ForegroundColor Yellow
    Write-Host "   → Search for: @$($botInfo.result.username)" -ForegroundColor Yellow
    Write-Host "   → Then run this script again" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit
}
Write-Host ""

# 4. List Existing Agents
Write-Host "4. Checking Existing Agents..." -ForegroundColor Yellow
$agents = Invoke-ApiCall "$backendUrl/api/agents"
if ($agents -and $agents.Count -gt 0) {
    Write-Host "   ✓ Found $($agents.Count) agent(s):" -ForegroundColor Green
    foreach ($agent in $agents) {
        Write-Host "      - ID: $($agent.id), Name: $($agent.name), Channels: $($agent.channels -join ', ')" -ForegroundColor Cyan
    }
    $agentId = $agents[0].id
} else {
    Write-Host "   ⚠ No agents found. Creating a test agent..." -ForegroundColor Yellow
    
    $agentData = @{
        name = "Telegram Test Agent"
        model = "gpt-4o-mini"
        system_prompt = "You are a helpful AI assistant. Be friendly and concise."
        channels = @("telegram")
        guardrails = @{}
    } | ConvertTo-Json
    
    $newAgent = Invoke-ApiCall "$backendUrl/agents" "POST" $agentData
    if ($newAgent) {
        Write-Host "   ✓ Created agent: $($newAgent.name) (ID: $($newAgent.id))" -ForegroundColor Green
        $agentId = $newAgent.id
    } else {
        Write-Host "   ✗ Failed to create agent" -ForegroundColor Red
        exit
    }
}
Write-Host ""

# 5. Connect Agent to Telegram Chat
Write-Host "5. Connecting Agent to Your Telegram Chat..." -ForegroundColor Yellow
$connectData = @{
    agent_id = $agentId
    chat_id = $chatId.ToString()
} | ConvertTo-Json

$connected = Invoke-ApiCall "$backendUrl/api/channels/telegram/connect" "POST" $connectData
if ($connected) {
    Write-Host "   ✓ Agent connected successfully!" -ForegroundColor Green
    Write-Host "   ✓ Agent ID: $agentId" -ForegroundColor Green
    Write-Host "   ✓ Chat ID: $chatId" -ForegroundColor Green
} else {
    Write-Host "   ⚠ Connection may have already existed or failed" -ForegroundColor Yellow
}
Write-Host ""

# 6. Test Instructions
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup Complete! Ready to Test" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Green
Write-Host "1. Open Telegram and go to your bot: @$($botInfo.result.username)" -ForegroundColor White
Write-Host "2. Send a message like: 'Hello, can you help me?'" -ForegroundColor White
Write-Host "3. The bot should respond within a few seconds" -ForegroundColor White
Write-Host ""
Write-Host "To monitor backend logs, run:" -ForegroundColor Yellow
Write-Host "   docker-compose logs backend -f" -ForegroundColor Cyan
Write-Host ""
Write-Host "To view message history:" -ForegroundColor Yellow
Write-Host "   curl http://localhost:8000/api/messages?channel=telegram" -ForegroundColor Cyan
Write-Host ""

# Optional: Send a test message
Write-Host "Would you like to send a test message from the API? (Y/N)" -ForegroundColor Yellow
$response = Read-Host
if ($response -eq "Y" -or $response -eq "y") {
    $testMessage = @{
        chat_id = $chatId.ToString()
        text = "🤖 Test message from AI Orchestrator API! Your bot is working correctly."
    } | ConvertTo-Json
    
    $sent = Invoke-ApiCall "$backendUrl/api/channels/telegram/send" "POST" $testMessage
    if ($sent) {
        Write-Host "   ✓ Test message sent! Check your Telegram." -ForegroundColor Green
    } else {
        Write-Host "   ⚠ Could not send test message (endpoint may not be fully implemented)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Testing complete! 🎉" -ForegroundColor Green
Write-Host ""
