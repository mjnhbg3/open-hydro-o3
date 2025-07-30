# Configuration

This directory holds all JSON configuration used by Open Hydro O3.

## Files

- **default.json** – Base configuration shipped with the project. Use this file as a starting point when creating a new configuration version.
- **current.json** – Symlink to the active configuration file. Point this link at whichever version you want the system to load.
- **safety_limits.json** – Hard safety limits that are merged at runtime. These values should rarely be changed.

Additional versioned configuration files can be created in this directory. To activate one, update `current.json` to point to it.

## Editing configuration

1. Copy `default.json` to a new file (e.g. `2024-04-01.json`) and edit the values.
2. Replace the `current.json` symlink with one pointing at your new file: `ln -sf 2024-04-01.json current.json`.
3. Restart any running services so they reload the configuration.

Configuration is loaded by `app.utils.load_config()` which merges `default.json`, the file referenced by `current.json`, and any overrides from environment variables.
