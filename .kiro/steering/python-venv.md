# Python Environment

This project uses a virtual environment located at `.venv/` in the workspace root.

## Always use the venv

Run all Python-related commands through the venv rather than the system interpreter. Use the executables directly so no shell activation step is needed:

- Python: `.venv/bin/python`
- Pytest: `.venv/bin/pytest`
- Pip: `.venv/bin/pip`

Examples:

```bash
.venv/bin/python main.py
.venv/bin/pytest
.venv/bin/pytest tests/test_storage.py
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

Do not call bare `python`, `pytest`, or `pip` for this project, and do not install packages globally.
