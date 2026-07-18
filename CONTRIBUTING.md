# Contributing

Thanks for contributing to **Agent Hub**.

## Dev setup

```bash
git clone https://github.com/xielab2017/Agent-Hub.git
cd Agent-Hub
python3 -m venv .venv && source .venv/bin/activate   # optional
./ctl.sh start
```

UI: `static/` · Backend: `ali/` · Entry: `server.py`

## Guidelines

- Do **not** commit secrets (`.env`, real API keys, `secrets.json`, machine-local absolute paths).
- Prefer small, focused PRs; update `CHANGELOG.md` / README version notes for user-visible changes.
- Match existing code style (Python 3.9+, vanilla JS frontend).

## License

By contributing, you agree your code is released under the MIT License.
