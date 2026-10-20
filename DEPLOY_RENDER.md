# Deployment status

The final deliverable is tested as a local, single-process application. No site or code has been deployed or pushed to GitHub.

Use `README.md` for local startup and `compose.yaml` for an optional Docker configuration. Docker was not available to build in the delivery environment. Review `SECURITY.md` before exposing this application beyond loopback.

The earlier Render configuration is preserved at `docs/legacy-render.yaml` as historical reference only. It is not the final deployment specification and should not be activated without review of HTTPS, cookies, allowed hosts, persistent storage, server ports and the single-worker requirement. No paid deployment has been requested or provisioned.
