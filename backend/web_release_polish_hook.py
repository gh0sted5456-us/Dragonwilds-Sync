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
    from v3_phase4_web_focus import install as install_v3_phase4_web_focus
    install_v3_phase4_web_focus()
except Exception as exc:
    print(f"[v3-phase4-web-focus] disabled: {exc}", flush=True)

try:
    from v3_phase4_host_patch import install as install_v3_phase4_host_patch
    install_v3_phase4_host_patch()
except Exception as exc:
    print(f"[v3-phase4-host-patch] disabled: {exc}", flush=True)

try:
    from phase5_remote_admin import install as install_phase5_remote_admin
    install_phase5_remote_admin()
except Exception as exc:
    print(f"[phase5-remote-admin] disabled: {exc}", flush=True)

try:
    from editor_runtime_stabilization import install as install_editor_stabilization
    install_editor_stabilization()
except Exception as exc:
    print(f"[editor-runtime-stabilization] disabled: {exc}", flush=True)