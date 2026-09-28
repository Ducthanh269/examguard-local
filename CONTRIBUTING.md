# Contributing to ExamGuard Local

Thank you for your interest in contributing! 🎉

## How to Contribute

### Reporting Bugs

1. Check [existing issues](../../issues) first
2. Create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots/logs if applicable
   - Your environment (OS, Python version)

### Suggesting Features

1. Open an issue with the `enhancement` label
2. Describe the use case
3. Explain why it would be useful

### Pull Requests

1. Fork the repository
2. Create a branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass: `scripts\TEST.cmd`
6. Update documentation if needed
7. Commit with clear messages
8. Push and create a Pull Request

## Development Setup

```cmd
# Clone your fork
git clone https://github.com/your-username/examguard-local.git
cd examguard-local

# Setup environment
scripts\SETUP.cmd

# Run tests
scripts\TEST.cmd
```

## Code Style

- Follow [PEP 8](https://pep8.org/)
- Use type hints where possible
- Write docstrings for public functions
- Keep functions focused and small
- Add comments for complex logic

## Testing

- All new features must include tests
- Maintain or improve test coverage
- Tests should be deterministic (no random failures)

## Commit Messages

Use clear, descriptive commit messages:

```
feat: Add audio level detection
fix: Resolve calibration reset on stream gap
docs: Update installation instructions
test: Add tests for phone track switching
refactor: Extract risk calculation to separate function
```

## Questions?

Feel free to open a [Discussion](../../discussions) or reach out to maintainers.