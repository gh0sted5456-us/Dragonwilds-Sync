try:
    from web_release_polish import install
    install()
except Exception as exc:
    print(f"[web-release-polish] disabled: {exc}", flush=True)
