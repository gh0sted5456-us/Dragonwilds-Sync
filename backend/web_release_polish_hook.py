try:
    from shell_persistence_stabilization import install as install_shell_persistence
    install_shell_persistence()
except Exception as exc:
    print(f"[shell-persistence-stabilization] disabled: {exc}", flush=True)

try:
    from web_release_polish import install
    install()
except Exception as exc:
    print(f"[web-release-polish] disabled: {exc}", flush=True)

try:
    from v3_phase4_web import install as install_v3_phase4_web
    install_v3_phase4_web()
except Exception as exc:
    print(f"[v3-phase4-web] disabled: {exc}", flush=True)

try:
    from editor_runtime_stabilization import install as install_editor_stabilization
    install_editor_stabilization()
except Exception as exc:
    print(f"[editor-runtime-stabilization] disabled: {exc}", flush=True)