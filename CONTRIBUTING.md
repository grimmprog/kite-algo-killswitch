# Contributing to Kite Algo Kill Switch

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/grimmprog/kite-algo-killswitch/issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - System information (OS, Python version, etc.)
   - Relevant logs (remove sensitive data!)

### Suggesting Features

1. Check [Discussions](https://github.com/grimmprog/kite-algo-killswitch/discussions) for similar ideas
2. Create a new discussion with:
   - Clear description of the feature
   - Use case and benefits
   - Possible implementation approach

### Pull Requests

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**
   - Follow existing code style
   - Add comments for complex logic
   - Update documentation if needed

4. **Test your changes**
   - Test manually
   - Ensure no regressions
   - Test on both Windows and Linux if possible

5. **Commit your changes**
   ```bash
   git commit -m "Add feature: brief description"
   ```

6. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create a Pull Request**
   - Describe what changes you made
   - Reference any related issues
   - Explain why the changes are needed

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/kite-algo-killswitch.git
cd kite-algo-killswitch

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your test credentials
```

## Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and small
- Comment complex logic

## Testing

- Test with paper trading first
- Verify Telegram commands work
- Test kill switch triggers with small amounts
- Check logs for errors
- Test on clean Ubuntu installation

## Documentation

- Update README.md if adding features
- Add comments to complex code
- Update deployment guides if needed
- Create examples for new features

## Security

- Never commit credentials or API keys
- Use `.env` for sensitive data
- Sanitize logs before sharing
- Report security issues privately

## Questions?

- Open a [Discussion](https://github.com/grimmprog/kite-algo-killswitch/discussions)
- Check existing documentation
- Ask in Issues if stuck

Thank you for contributing! 🙏
