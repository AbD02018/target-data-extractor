# Contributing

Thanks for considering a contribution.

## Adding a new platform

1. Add `src/target_data_extractor/platforms/<name>.py` with a class extending `BasePlatform`.
2. Set `platform_name`, `hostnames`, and implement `async def extract(url, **kwargs) -> BountyProgram`.
3. Register in `src/target_data_extractor/platforms/__init__.py`.
4. Add tests in `tests/test_platforms.py`.
5. Update README's coverage matrix.

## Code style

- Python 3.10+
- Type hints everywhere
- `ruff` for linting
- `mypy --strict` clean

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Pull requests

- One feature per PR.
- Include tests.
- Update CHANGELOG.md.
- Don't bypass auth on platforms that require it for private data.
