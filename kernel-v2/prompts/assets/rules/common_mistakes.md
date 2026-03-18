## Common Mistakes to Avoid

- Don't output XML - Always use JSON
- Don't skip the reasoning section - It's required for complex tasks
- Don't put technical details in explanation - Keep it user-friendly
- Don't use markdown code blocks - Output raw JSON
- Don't forget to escape special characters in strings

## Validation Checklist

Before submitting your response, verify:
- [ ] Output is valid JSON (can be parsed by JSON.parse)
- [ ] Contains all required fields: reasoning, explanation, actions
- [ ] Actions array exists (can be empty for final responses)
- [ ] Each action has required fields: type, id, skill, tool, parameters
- [ ] Explanation is appropriate for user visibility
- [ ] Strings are properly escaped
