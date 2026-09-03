from external_mod_hosting import install_import_hooks

# Install before dragonwilds_service imports the retained legacy/service graph.
# This keeps hybrid delivery active in the desktop service and runtime-worker
# modes without creating a second synchronization implementation.
install_import_hooks()
