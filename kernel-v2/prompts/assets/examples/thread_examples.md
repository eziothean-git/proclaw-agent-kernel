## Examples

### Example 1: Reading a File

```json
{
  "reasoning": {
    "observation": "User asked to read /home/user/readme.md. This is a file read operation within the allowed path.",
    "thought": "The user wants to see the content of a markdown file. This is a straightforward file operation. I should use the bash skill with the cat command to read the file.",
    "plan": [
      "Execute cat command to read the file",
      "Return the content to the user"
    ]
  },
  "explanation": "I'll read the readme file for you. Just a moment...",
  "actions": [
    {
      "type": "tool_call",
      "id": "act_001",
      "skill": "bash",
      "tool": "execute",
      "parameters": {
        "command": "cat /home/user/readme.md"
      },
      "metadata": {
        "reasoning": "Read the requested markdown file",
        "expected_output": "Content of readme.md file"
      }
    }
  ],
  "state_update": {
    "phase": "Execute",
    "artifacts": []
  }
}
```

### Example 2: Multiple Actions

```json
{
  "reasoning": {
    "observation": "User wants to analyze a Rust project's structure and find all public functions. The project is at /home/user/myapp.",
    "thought": "This requires multiple steps: 1. First, explore the project structure. 2. Look at source files for public functions. 3. Use grep to find 'pub fn' declarations.",
    "plan": [
      "List the project root to see structure",
      "Check Cargo.toml for project info",
      "Search for public functions using grep"
    ]
  },
  "explanation": "I'll analyze your Rust project to find all public functions. Let me start by exploring the project structure.",
  "actions": [
    {
      "type": "tool_call",
      "id": "act_001",
      "skill": "bash",
      "tool": "execute",
      "parameters": {
        "command": "ls -la",
        "working_dir": "/home/user/myapp"
      },
      "metadata": {
        "reasoning": "Get overview of project structure"
      }
    },
    {
      "type": "tool_call",
      "id": "act_002",
      "skill": "bash",
      "tool": "execute",
      "parameters": {
        "command": "cat Cargo.toml",
        "working_dir": "/home/user/myapp"
      },
      "metadata": {
        "reasoning": "Read project configuration"
      }
    },
    {
      "type": "tool_call",
      "id": "act_003",
      "skill": "bash",
      "tool": "execute",
      "parameters": {
        "command": "rg \"pub fn\" src/ -n",
        "working_dir": "/home/user/myapp"
      },
      "metadata": {
        "reasoning": "Search for public function declarations"
      }
    }
  ],
  "state_update": {
    "phase": "Execute",
    "artifacts": []
  }
}
```

### Example 3: Task Complete (No More Actions)

```json
{
  "reasoning": {
    "observation": "Task is complete. The file has been read and the content returned to the user.",
    "thought": "No more actions needed. The user's request has been fulfilled.",
    "plan": []
  },
  "explanation": "Here's the content of the file. Let me know if you need anything else!",
  "actions": [],
  "state_update": {
    "phase": "Complete",
    "artifacts": []
  }
}
```

### Example 4: Asking for Clarification

```json
{
  "reasoning": {
    "observation": "User asked to 'fix the bug' but didn't specify which bug or provide any context.",
    "thought": "I don't have enough information to proceed. There could be many potential bugs. I need to ask the user for more details.",
    "plan": [
      "Ask user for clarification about the bug"
    ]
  },
  "explanation": "I'd be happy to help fix the bug! Could you provide more details:\n- What specific error message or behavior are you seeing?\n- What were you trying to do when the bug occurred?\n- Do you know which file or part of the code is affected?",
  "actions": [],
  "state_update": {
    "phase": "Complete",
    "artifacts": []
  }
}
```
