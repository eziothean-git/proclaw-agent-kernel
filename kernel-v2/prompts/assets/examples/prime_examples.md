## Examples

### Example 1: Simple File Read
User: "读取文件 /home/user/doc.txt"

```json
{
  "analysis": {
    "observation": "User wants to read file /home/user/doc.txt",
    "complexity": "simple"
  },
  "processes": [
    {
      "id": "p1",
      "name": "read_document",
      "goal": "Read file /home/user/doc.txt and return its complete content",
      "capabilities": ["bash"],
      "constraints": ["read_only"],
      "security_level": "low"
    }
  ],
  "explanation": "I'll read the document for you."
}
```

### Example 2: File Chain Traversal
User: "遍历文件链 /data/chain/start.md"

```json
{
  "analysis": {
    "observation": "User wants to traverse a linked chain of markdown files starting at /data/chain/start.md",
    "complexity": "moderate"
  },
  "processes": [
    {
      "id": "p1",
      "name": "traverse_chain",
      "goal": "Starting from /data/chain/start.md, read the file, find markdown links to next files, follow them recursively until reaching a file with no outgoing links or max depth 10. Return all collected content from the chain.",
      "capabilities": ["bash"],
      "constraints": ["read_only", "max_depth:10"],
      "security_level": "low"
    }
  ],
  "explanation": "I'll traverse the file chain and collect all content."
}
```

### Example 3: Greeting (Still needs JSON!)
User: "你好"

```json
{
  "analysis": {
    "observation": "User greeted me",
    "complexity": "simple"
  },
  "processes": [],
  "explanation": "你好！很高兴见到你。有什么我可以帮助你的吗？"
}
```

### Example 4: Multiple Steps
User: "分析这个 Rust 项目的结构并找到所有公开函数"

```json
{
  "analysis": {
    "observation": "User wants to analyze a Rust project structure and find all public functions",
    "complexity": "moderate"
  },
  "processes": [
    {
      "id": "p1",
      "name": "analyze_project",
      "goal": "Analyze the Rust project structure, find all public functions (pub fn), and return a summary",
      "capabilities": ["bash", "code"],
      "constraints": ["read_only"],
      "security_level": "low"
    }
  ],
  "explanation": "I'll analyze your Rust project to find all public functions."
}
```
