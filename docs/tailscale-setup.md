# Secure Remote Access via Tailscale

WaveTouchOS binds to `127.0.0.1:7000` only — it is never exposed on a LAN
or public interface. Tailscale gives you a private, encrypted (WireGuard)
overlay network ("tailnet") so you can reach the server from anywhere
without opening any ports on your router.

The admin panel (Settings → System → Tailscale) shows live connection
status (connected/disconnected, tailnet IP, MagicDNS name, peer count) via
`GET /api/auth/tailscale/status` (admin-only).

## 1. Install

**Server (the machine running WaveTouchOS):**

```bash
# Linux
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh
```

```powershell
# Windows — download installer from https://tailscale.com/download
# then from an elevated PowerShell:
tailscale up
```

**Client devices** (phone, laptop you'll connect from): install the
Tailscale app and sign in with the *same account/tailnet*.

## 2. Lock down the tailnet account

In the Tailscale admin console (https://login.tailscale.com/admin):

- **Enable two-factor auth (2FA/MFA)** on the identity provider used to
  log in to your tailnet (Google/Microsoft/GitHub/passkey). This is the
  single most important step — anyone who can log in to the tailnet
  console can add devices and read your ACLs.
- **Settings → Device management → Key expiry**: leave key expiry
  *enabled* for all devices except the server itself. For the server,
  either re-authenticate periodically (`tailscale up` prompts when the
  key is about to expire) or mark just that node's key as
  non-expiring (Admin console → Machines → your server → Disable key
  expiry). Don't disable expiry tailnet-wide.
- **Settings → Device management → Device approval**: turn this **on**.
  New devices (including ones added by a compromised login) won't join
  the tailnet until you approve them.

## 3. Restrict access with ACLs (tag-based)

Tag the server so ACLs can target it specifically, then write an ACL
policy that only lets your personal devices reach it. In the admin
console → Access controls, replace the default policy with something
like:

```json
{
  "tagOwners": {
    "tag:server": ["autogroup:admin"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["autogroup:member"],
      "dst": ["tag:server:443", "tag:server:7000"]
    }
  ],
  "ssh": [
    {
      "action": "check",
      "src": ["autogroup:member"],
      "dst": ["tag:server"],
      "users": ["autogroup:nonroot", "root"]
    }
  ]
}
```

Then tag the server node:

```bash
sudo tailscale up --advertise-tags=tag:server --ssh
```

`autogroup:member` = your own logged-in tailnet identities only — random
devices that get added later won't reach the server unless you also add
them to the tailnet (and device approval gates that).

The `ssh` block enables **Tailscale SSH** with per-connection checks
(`action: check` re-prompts for tailnet auth periodically), so you can
retire password/key-based SSH exposure entirely.

## 4. Expose WaveTouchOS over HTTPS — tailnet-only

Use `tailscale serve` to terminate HTTPS and proxy to the local app. This
publishes the service **only inside your tailnet** (not the public
internet):

```bash
sudo tailscale serve --bg https / http://127.0.0.1:7000
```

Check status any time:

```bash
tailscale serve status
```

To stop serving: `sudo tailscale serve --https=443 off`.

**Do not use `tailscale funnel`** for this service — Funnel makes the
endpoint reachable from the public internet, which defeats the purpose
of keeping WaveTouchOS off any public surface. Only use Funnel if you
deliberately want a specific path to be public, and scope it narrowly.

## 5. Optional hardening

- **Tailnet Lock** (`tailscale lock`): cryptographically signs which
  nodes are allowed on the tailnet, protecting against a compromised
  control-plane account being able to silently add a spy node. Worth
  enabling once your device set is stable (adding nodes later requires
  signing with a key from an existing locked node).
- **`--accept-routes=false`** (default) on the server unless you're
  intentionally using it as a subnet router/exit node.
- **Firewall**: even though Tailscale already isolates traffic, keep the
  host firewall enabled and only allow inbound on the `tailscale0` /
  `Tailscale` interface for port 7000 (or none at all if only using
  `tailscale serve`, which listens on the Tailscale interface itself).
- Periodically review **Admin console → Machines** and remove any
  device you don't recognize.

## 6. Connecting from away

- Install Tailscale on your phone/laptop, sign in to the same tailnet.
- Browse to `https://<server-magicdns-name>` (shown in Settings → System
  → Tailscale → MagicDNS, e.g. `myserver.tailxxxx.ts.net`) or the
  Tailscale IP shown there (`100.x.y.z:7000` if not using `serve`).
