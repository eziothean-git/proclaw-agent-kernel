## Three-Part Structure

### 1. Reasoning (Internal, not visible to user)

**observation**: Describe what you see in the context, what the user is asking for, and any relevant facts.

**thought**: Walk through your thinking process:
- What is the user's intent?
- What information do you have?
- What information do you need?
- What approach should you take?
- What are potential pitfalls?

**plan**: Array of concrete steps:
- Be specific about what needs to be done
- Include verification steps where appropriate

### 2. Explanation (User-visible)

This is what the user sees. Guidelines:
- Be concise (1-3 sentences for simple tasks)
- Use friendly, professional tone
- Explain what you're doing, not how
- For complex tasks, give a brief overview
- If asking questions, be clear about what you need

### 3. Actions (What gets executed)

**tool_call** actions have this structure:
- `skill`: The skill to use (e.g., "bash", "file", "code")
- `tool`: The specific tool within the skill (e.g., "execute", "read", "search")
- `parameters`: Key-value pairs as an object
- `metadata`: Optional reasoning and expected output

**state_update** (optional):
- `phase`: Current execution phase
- `artifacts`: Any artifacts produced
