try:
    from web_release_polish import install
    install()
except Exception as exc:
    print(f"[web-release-polish] disabled: {exc}", flush=True)

try:
    from editor_runtime_stabilization import install as install_editor_stabilization
    install_editor_stabilization()
except Exception as exc:
    print(f"[editor-runtime-stabilization] disabled: {exc}", flush=True)
