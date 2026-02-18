# odin-bots is deprecated

**This package has been renamed to [`iconfucius`](https://pypi.org/project/iconfucius/).**

## Migration

```bash
pip uninstall odin-bots
pip install iconfucius
```

Then replace `odin-bots` with `iconfucius` in your workflow:

```bash
cd my-bots
iconfucius
```

`iconfucius` will detect your existing `odin-bots.toml` and offer to upgrade it
to `iconfucius.toml`. Your `.wallet/`, `.cache/`, and `.memory/` directories
are fully compatible.

## Links

- New package: [pypi.org/project/iconfucius](https://pypi.org/project/iconfucius/)
- Source: [github.com/onicai/IConfucius](https://github.com/onicai/IConfucius)

## License

MIT
