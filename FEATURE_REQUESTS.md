# Feature requests

Things we missed in the APIs we used, collected during build week (23-29 Nov 2026). The hackathon passes these to the teams behind the apps.

## Even Hub SDK and simulator

1. A per-app device token. `getUserInfo().uid` is a small number, the same in every app, so it can't be used to authenticate glasses to our own server. We generate a random key and keep it in localStorage instead; a signed, app-scoped token from the SDK would be safer and survive a WebView data reset.
2. A wider glyph set in the firmware font, or a documented list of supported characters. A check mark and the ellipsis character render as nothing, which we found only by testing.
3. Audio injection in the simulator automation API (for example `POST /api/audio` with a WAV file), so voice features can be tested in CI without a real microphone.

## Telegram Bot API

4. (to be filled)
