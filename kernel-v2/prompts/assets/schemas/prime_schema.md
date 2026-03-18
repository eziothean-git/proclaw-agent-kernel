## MANDATORY Output Format

You MUST output ONLY valid JSON. No natural language before or after. No markdown code block indicators. Just raw JSON.

### JSON Schema

```json
{
  "analysis": {
    "observation": "string - What the user wants",
    "complexity": "simple|moderate|complex"
  },
  "processes": [
    {
      "id": "string - process id like p1, p2",
      "name": "string - descriptive_name",
      "goal": "string - Specific goal with ALL necessary details: file paths, commands, expected outcomes",
      "capabilities": ["bash", "file", "code", "search"],
      "constraints": ["read_only", "max_depth:10"],
      "security_level": "low|medium|high"
    }
  ],
  "explanation": "string - Brief user-friendly explanation"
}
```

### Field Descriptions

- **analysis.observation**: What you understand from the user's request
- **analysis.complexity**: Task complexity (simple, moderate, or complex)
- **processes**: Array of process definitions (can be empty for greetings)
  - **id**: Unique identifier (p1, p2, etc.)
  - **name**: Descriptive process name (snake_case)
  - **goal**: Complete, specific goal with all necessary details
  - **capabilities**: Array of required capabilities
  - **constraints**: Array of constraints (optional)
  - **security_level**: Security level (low, medium, high)
- **explanation**: User-facing explanation (this is the only text the user sees)
