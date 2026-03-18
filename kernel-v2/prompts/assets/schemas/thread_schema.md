### JSON Schema

```json
{
  "reasoning": {
    "observation": "string - What you see/understand from context",
    "thought": "string - Your internal reasoning process",
    "plan": [
      "step 1 description",
      "step 2 description"
    ]
  },
  "explanation": "string - What you tell the user (ONLY part visible to user)",
  "actions": [
    {
      "type": "tool_call",
      "id": "act_001",
      "skill": "bash|file|code|search",
      "tool": "execute|read|write|search",
      "parameters": {
        "key": "value"
      },
      "metadata": {
        "reasoning": "Why this action is needed",
        "expected_output": "What result we expect"
      }
    }
  ],
  "state_update": {
    "phase": "Explore|Execute|Complete",
    "artifacts": []
  }
}
```
