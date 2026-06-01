# UI Workflow Testing Guide
## Complete Step-by-Step Guide Using the Web Interface

This guide focuses entirely on using the web UI at `http://localhost:3000` - no API calls or command line needed!

---

## 🚀 Getting Started

### Prerequisites
1. ✅ Open your browser
2. ✅ Navigate to: `http://localhost:3000`
3. ✅ Make sure backend is running (you should see the dashboard)

---

## Part 1: Creating Agents (Required for Workflows)

### Step 1: Navigate to Agents Page
1. Click **"Agents"** in the left sidebar
2. You'll see a list of existing agents (if any)

### Step 2: Create Your First Agent

Click the **"Create Agent"** button (top right)

#### Fill in the Basic Information:

**Tab: Basics**
```
Name: Research Assistant
Role: Research Specialist
Model: gpt-4o-mini (select from dropdown)
System Prompt: You are a research assistant. When given a topic, provide detailed research findings with key facts and insights.
```

**Tab: Tools/Memory**
- ✅ Check "Memory Enabled"
- Select tools if needed (optional for now)

**Tab: Channels**
- ✅ Check "web" (must have at least one channel)

**Tab: Guardrails**
- Leave as default `{}` or add:
```json
{
  "max_tokens": 800,
  "blocked_keywords": []
}
```

Click **"Save Agent"** button at the bottom

### Step 3: Create a Second Agent

Repeat Step 2 with these details:

```
Name: Summary Writer
Role: Content Summarizer  
Model: gpt-4o-mini
System Prompt: You are an expert at creating concise summaries. Take the provided information and create a clear, brief summary.
Channels: web
Memory Enabled: ✅
```

Click **"Save Agent"**

### Step 4: Verify Your Agents

You should now see both agents in the Agents list:
- ✅ Research Assistant
- ✅ Summary Writer

---

## Part 2: Creating Your First Workflow

### Step 1: Navigate to Workflows Page
1. Click **"Workflows"** in the left sidebar
2. Click **"Create Workflow"** button (top right)

### Step 2: Design Your Workflow

You'll see a visual canvas with a toolbar on the left.

#### Add Agents to Canvas:

1. **Add First Agent:**
   - Look for the **"Add Agent"** section in the left panel
   - Find "Research Assistant" in the dropdown
   - Click **"Add to Canvas"** or drag it onto the canvas
   - Position it on the left side

2. **Add Second Agent:**
   - Select "Summary Writer" from the dropdown
   - Click **"Add to Canvas"**
   - Position it to the right of Research Assistant

#### Connect the Agents:

1. **Create Connection:**
   - Hover over the **Research Assistant** node
   - You'll see small circles (connection points) on the edges
   - Click and drag from the **right circle** of Research Assistant
   - Drop it on the **left circle** of Summary Writer
   - You should see an arrow connecting them

2. **Verify Connection:**
   - The arrow shows: Research Assistant → Summary Writer
   - This means Research Assistant runs first, then Summary Writer

### Step 3: Configure Workflow Settings

At the top of the page:

```
Workflow Name: Research and Summarize
Description: Research a topic and create a concise summary
```

### Step 4: Save the Workflow

Click **"Save Workflow"** button (top right)

You should see a success message!

---

## Part 3: Running Your Workflow

### Step 1: Find Your Workflow

1. Go to **"Workflows"** page
2. Find "Research and Summarize" in the list
3. Click on it to open

### Step 2: Start Execution

1. Click the **"Run Workflow"** button (top right or in the workflow card)

2. **Enter Input Data:**
   A dialog will appear asking for input. Enter:
   ```json
   {
     "topic": "Artificial Intelligence in Healthcare",
     "focus": "recent developments"
   }
   ```

3. Click **"Start Run"** or **"Execute"**

### Step 3: Monitor Execution

You'll be automatically redirected to the **Monitor** page.

---

## Part 4: Monitoring Workflow Execution

### View Active Runs

On the Monitor page, you'll see:

1. **Active Runs Tab** (default view)
   - Your workflow appears in the list
   - Status shows: `pending` → `running` → `completed`
   - Progress bar shows execution progress

2. **Click on Your Run** to see details

### View Real-Time Logs

1. **Switch to "Message Stream" Tab**
   - See real-time logs as agents work
   - Watch messages flow between agents
   - See when each agent starts and completes

2. **Filter Messages** (optional)
   - Use dropdowns to filter by:
     - Agent (show only specific agent's messages)
     - Channel (web, internal, etc.)
     - Level (INFO, ERROR, etc.)

### View Execution Timeline

1. **Click "Timeline" Button** on your run
   - See step-by-step execution
   - View input/output for each agent
   - Check token usage and timing

### View Results

1. **Once Status = "Completed":**
   - Click on the run
   - Scroll to see final output
   - Check the last message from Summary Writer

2. **View Token Usage:**
   - Switch to **"Token/Cost"** tab
   - See total tokens used
   - View cost breakdown

---

## Part 5: Testing Different Workflow Patterns

### Pattern 1: Simple Sequential Workflow (Already Done!)
```
Agent A → Agent B
```
✅ You just created this!

### Pattern 2: Three-Step Sequential Workflow

**Create Three Agents:**
1. Researcher (already have)
2. Analyzer (new)
3. Writer (already have Summary Writer)

**Connect Them:**
```
Researcher → Analyzer → Writer
```

**Test Input:**
```json
{
  "topic": "Climate Change Solutions",
  "depth": "comprehensive"
}
```

### Pattern 3: Parallel Processing Workflow

**Create Workflow with Parallel Agents:**

1. **Add Three Agents to Canvas:**
   - Technical Analyst (top)
   - Business Analyst (middle)
   - Market Analyst (bottom)
   - Final Synthesizer (right)

2. **Connect Them:**
   ```
   Technical Analyst ──┐
   Business Analyst ───┼──→ Final Synthesizer
   Market Analyst ─────┘
   ```

3. **How to Create Parallel Connections:**
   - Connect Technical Analyst → Final Synthesizer
   - Connect Business Analyst → Final Synthesizer
   - Connect Market Analyst → Final Synthesizer
   - All three will run simultaneously!

**Test Input:**
```json
{
  "product": "AI-powered CRM",
  "market": "enterprise software"
}
```

---

## Part 6: Using Workflow Templates

### View Available Templates

1. Go to **"Workflows"** page
2. Click **"Templates"** filter or tab
3. Browse pre-built workflow templates

### Use a Template

1. **Select a Template:**
   - Click on a template card
   - Click **"Use Template"** button

2. **Customize:**
   - The template opens in the editor
   - Modify agents if needed
   - Adjust connections
   - Change workflow name

3. **Save as New Workflow:**
   - Click **"Save As New"**
   - Give it a unique name
   - Click **"Save"**

---

## Part 7: Managing Workflow Runs

### View All Runs

1. Go to **"Monitor"** page
2. **"Active Runs"** tab shows all executions

### Actions You Can Take:

#### 1. **View Run Details**
- Click on any run
- See complete execution history

#### 2. **Stop a Running Workflow**
- Find a running workflow
- Click **"Stop"** button
- Confirm the action

#### 3. **Rerun a Completed Workflow**
- Find a completed run
- Click **"Rerun"** button
- Uses the same input data
- Creates a new run

#### 4. **Resume a Failed Workflow**
- Find a failed or paused run
- Click **"Resume"** button
- Continues from where it stopped

#### 5. **Export Timeline**
- Open a completed run
- Click **"Export"** button
- Downloads JSON with full execution data

---

## Part 8: Troubleshooting Common Issues

### Issue 1: "Agent Not Found" Error

**Problem:** Workflow shows error when running

**Solution:**
1. Go to **Workflows** page
2. Open the problematic workflow
3. Check if all agent nodes are properly configured
4. Make sure agents still exist (check Agents page)
5. If an agent was deleted, remove that node or replace it

### Issue 2: Workflow Stuck in "Running"

**Problem:** Workflow doesn't complete

**Solution:**
1. Check **Message Stream** for errors
2. Look for the last message - where did it stop?
3. Check if OpenAI API key is valid (Settings page)
4. Click **"Stop"** and try again
5. Check backend logs if issue persists

### Issue 3: "Validation Error" When Saving Agent

**Problem:** Can't save agent, shows validation error

**Solution:**
1. **Check Required Fields:**
   - Name must not be empty
   - At least one channel must be selected
   - Model must be selected

2. **Check Guardrails JSON:**
   - Must be valid JSON
   - Use `{}` if no guardrails needed
   - Example valid guardrails:
   ```json
   {
     "max_tokens": 500
   }
   ```

3. **Check Tools:**
   - If you see tool errors, try removing all tools
   - Save agent with just Memory enabled
   - Add tools one by one after saving

### Issue 4: Can't Connect Agents in Workflow

**Problem:** Connection line doesn't appear

**Solution:**
1. Make sure both agents are on the canvas
2. Click and hold on the source agent's connection point
3. Drag to the target agent's connection point
4. Release mouse button
5. If still not working, try:
   - Refresh the page
   - Recreate the workflow
   - Check browser console for errors (F12)

### Issue 5: No Output from Workflow

**Problem:** Workflow completes but no results

**Solution:**
1. Go to **Monitor** → **Message Stream**
2. Look for the last agent's output
3. Check if agents have proper system prompts
4. Verify input data was provided correctly
5. Try running a single agent first to test

---

## Part 9: Best Practices

### ✅ DO:
1. **Test Agents Individually First**
   - Create agent
   - Test with simple task
   - Verify it works before adding to workflow

2. **Start Simple**
   - Begin with 2-agent workflows
   - Test thoroughly
   - Then add complexity

3. **Use Clear Names**
   - Name agents descriptively
   - Name workflows clearly
   - Add good descriptions

4. **Monitor Token Usage**
   - Check Token/Cost tab regularly
   - Set guardrails to limit tokens
   - Use gpt-4o-mini for testing (cheaper)

5. **Save Successful Workflows as Templates**
   - Mark working workflows as templates
   - Reuse them for similar tasks

### ❌ DON'T:
1. **Don't Create Circular Workflows**
   - Agent A → Agent B → Agent A (infinite loop!)
   - System will show validation error

2. **Don't Use Too Many Agents**
   - Start with 2-3 agents
   - More agents = higher cost and complexity

3. **Don't Forget to Save**
   - Always click "Save" after changes
   - Unsaved changes are lost

4. **Don't Skip Testing**
   - Test each agent before workflow
   - Test workflow with simple input first

---

## Part 10: Example Workflows to Try

### Example 1: Content Creation Pipeline
```
Topic Researcher → Content Writer → Editor → SEO Optimizer
```

**Agents Needed:**
1. Topic Researcher - finds key points
2. Content Writer - writes article
3. Editor - improves quality
4. SEO Optimizer - adds SEO elements

**Input:**
```json
{
  "topic": "Benefits of Remote Work",
  "target_audience": "business professionals",
  "word_count": 800
}
```

### Example 2: Customer Support Workflow
```
Intent Classifier → [Technical Support | Billing Support | General Support] → Response Generator
```

**Agents Needed:**
1. Intent Classifier - determines issue type
2. Technical Support - handles tech issues
3. Billing Support - handles billing
4. General Support - handles other issues
5. Response Generator - creates final response

**Input:**
```json
{
  "customer_message": "I can't log into my account",
  "customer_id": "12345"
}
```

### Example 3: Data Analysis Workflow
```
Data Collector → Data Analyzer → Insight Generator → Report Writer
```

**Agents Needed:**
1. Data Collector - gathers information
2. Data Analyzer - analyzes patterns
3. Insight Generator - creates insights
4. Report Writer - writes final report

**Input:**
```json
{
  "data_source": "sales_data_2024",
  "analysis_type": "trend_analysis"
}
```

---

## Quick Reference Card

### Navigation
- **Dashboard:** Overview and quick actions
- **Agents:** Create and manage agents
- **Workflows:** Design and manage workflows
- **Monitor:** Watch executions in real-time
- **Settings:** Configure system settings

### Common Actions
| Action | Location | Button |
|--------|----------|--------|
| Create Agent | Agents page | "Create Agent" |
| Create Workflow | Workflows page | "Create Workflow" |
| Run Workflow | Workflow detail | "Run Workflow" |
| View Execution | Monitor page | Click on run |
| Stop Workflow | Monitor page | "Stop" button |
| Rerun Workflow | Monitor page | "Rerun" button |

### Status Indicators
- 🟡 **Pending:** Queued, not started
- 🔵 **Running:** Currently executing
- 🟢 **Completed:** Finished successfully
- 🔴 **Failed:** Encountered an error
- 🟣 **Paused:** Stopped by user

---

## Getting Help

### In the UI:
1. Hover over any field for tooltips
2. Check validation messages (red text)
3. Look for help icons (?) next to labels

### Check Logs:
1. Go to Monitor → Message Stream
2. Look for ERROR level messages
3. Read the error descriptions

### Common Error Messages:

| Error | Meaning | Solution |
|-------|---------|----------|
| "Agent not found" | Agent was deleted | Remove node or add agent back |
| "Validation error" | Invalid configuration | Check required fields |
| "Method not allowed" | Backend issue | Refresh page, check backend |
| "Workflow contains cycle" | Circular connection | Remove circular connections |
| "No channels selected" | Missing channel | Select at least one channel |

---

## Success Checklist

After following this guide, you should be able to:

- ✅ Create agents using the UI
- ✅ Design workflows visually
- ✅ Connect agents in different patterns
- ✅ Run workflows with custom input
- ✅ Monitor execution in real-time
- ✅ View results and token usage
- ✅ Troubleshoot common issues
- ✅ Rerun and resume workflows
- ✅ Use workflow templates

---

## Next Steps

1. **Experiment:** Try different agent combinations
2. **Optimize:** Adjust system prompts for better results
3. **Scale:** Create more complex workflows
4. **Integrate:** Connect with Telegram (see TELEGRAM_TESTING_GUIDE.md)
5. **Automate:** Set up scheduled workflows

---

## Tips for Success

💡 **Start Small:** Begin with simple 2-agent workflows  
💡 **Test Often:** Run workflows frequently during development  
💡 **Monitor Costs:** Keep an eye on token usage  
💡 **Save Templates:** Reuse successful patterns  
💡 **Read Logs:** Message Stream shows what's happening  
💡 **Be Patient:** Complex workflows take time to execute  

---

Happy Workflow Building! 🚀

Need help? Check the other guides:
- `TELEGRAM_TESTING_GUIDE.md` - Telegram integration
- `FIXES_APPLIED.md` - Recent fixes and changes
- `ARCHITECTURE.md` - System architecture details
