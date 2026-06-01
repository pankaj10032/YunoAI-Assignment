# Quick Start Guide - Using the UI Only

## 🎯 Goal
Get your first workflow running in 10 minutes using only the web interface!

---

## Step 1: Open the Application (1 minute)

1. Open your web browser
2. Go to: **http://localhost:3000**
3. You should see the Dashboard

✅ **Success Check:** You see the AI Orchestrator dashboard

---

## Step 2: Create Your First Agent (3 minutes)

1. Click **"Agents"** in the left sidebar
2. Click **"Create Agent"** button (top right)
3. Fill in these fields:

### Basics Tab:
```
Name: Content Writer
Role: Writing Assistant
Model: gpt-4o-mini (select from dropdown)
System Prompt: You are a professional content writer. Create engaging content based on the given topic.
```

### Channels Tab:
- ✅ Check "web"

4. Click **"Save Agent"** at the bottom

✅ **Success Check:** You see "Content Writer" in the agents list

---

## Step 3: Create a Second Agent (2 minutes)

1. Click **"Create Agent"** again
2. Fill in:

```
Name: Editor
Role: Content Editor
Model: gpt-4o-mini
System Prompt: You are an editor. Review and improve the provided content for clarity and grammar.
```

3. Check "web" channel
4. Click **"Save Agent"**

✅ **Success Check:** You now have 2 agents

---

## Step 4: Create a Simple Workflow (2 minutes)

1. Click **"Workflows"** in the left sidebar
2. Click **"Create Workflow"** button
3. You'll see a visual canvas

### Add Agents:
1. Find the agent dropdown on the left
2. Select "Content Writer" → Click "Add to Canvas"
3. Select "Editor" → Click "Add to Canvas"

### Connect Them:
1. Click and drag from Content Writer's right edge
2. Drop on Editor's left edge
3. You should see an arrow: Content Writer → Editor

### Name Your Workflow:
```
Workflow Name: Write and Edit
Description: Create content and edit it
```

4. Click **"Save Workflow"**

✅ **Success Check:** Workflow saved successfully

---

## Step 5: Run Your Workflow (2 minutes)

1. Find your "Write and Edit" workflow in the list
2. Click **"Run Workflow"** button
3. Enter input data:

```json
{
  "topic": "Benefits of Exercise",
  "length": "short"
}
```

4. Click **"Start Run"**

✅ **Success Check:** You're redirected to the Monitor page

---

## Step 6: Watch It Run!

You'll automatically see:
- Status changing: pending → running → completed
- Real-time logs in Message Stream
- Progress bar moving

**Wait 30-60 seconds** for completion.

✅ **Success Check:** Status shows "completed" in green

---

## 🎉 Congratulations!

You just:
- ✅ Created 2 AI agents
- ✅ Built a workflow
- ✅ Ran it successfully
- ✅ Saw real-time execution

---

## What's Next?

### Try These:
1. **Add a third agent** to make a 3-step workflow
2. **Change the input** and run again
3. **View the timeline** to see step-by-step execution
4. **Check token usage** in the Token/Cost tab

### Learn More:
- Read `UI_WORKFLOW_GUIDE.md` for detailed instructions
- Check `TELEGRAM_TESTING_GUIDE.md` to connect Telegram
- See `FIXES_APPLIED.md` for recent improvements

---

## Troubleshooting

### "Validation Error" when saving agent?
- Make sure Name is filled in
- Make sure at least one channel is checked
- Try removing all tools and just use Memory

### Workflow not starting?
- Check that both agents exist
- Make sure they're connected with an arrow
- Try refreshing the page

### Can't see results?
- Go to Monitor page
- Click on your run
- Switch to "Message Stream" tab
- Look for the last message

---

## Quick Tips

💡 **Always save** after making changes  
💡 **Start simple** - 2 agents first, then add more  
💡 **Check Message Stream** to see what's happening  
💡 **Use gpt-4o-mini** for testing (it's cheaper)  
💡 **Name things clearly** so you can find them later  

---

## Need Help?

1. Check the Message Stream for error messages
2. Read the full `UI_WORKFLOW_GUIDE.md`
3. Check if backend is running: `docker-compose ps`
4. Restart if needed: `docker-compose restart`

---

Happy Building! 🚀
