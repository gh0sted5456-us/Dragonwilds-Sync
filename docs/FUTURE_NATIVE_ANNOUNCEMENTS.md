# Future feature: native game announcements

Dragonwilds Sync 3.0 delivers server notices through its own application and
authenticated WebGUI surfaces. These notices are non-intrusive, dismissible,
and do not inject input, alter game widgets, or impersonate game chat.

## Current V3 contract

- Application notifications are the only supported delivery path.
- Scheduled restart and update warnings use the existing launcher notification
  flow, including the 30, 10, 5, and 1 minute milestones.
- Gameplay broadcast, Sync discovery, file transfer, and administrative notices
  remain separate responsibilities.
- No V3 setting may imply that a notice was delivered inside Dragonwilds.

## Investigated native path

FModel exports and runtime symbols show that Dragonwilds has a player chat
component and server/client chat RPCs, including `Server_SendChatMessage` and
`Client_ReceiveChatMessage`. The runtime also exposes system-message events and
`DisplayScreenMessage`. Those are stronger future integration candidates than
simulated keyboard input or UI scraping.

The sleep interface contains randomized transition text such as "The world
wakes." It is a presentation widget, not a general announcement transport, so
Dragonwilds Sync must not repurpose it without a verified game-side API.

## Future acceptance boundary

A future **Application / Game / Both** delivery selector may be enabled only
after a versioned bridge can prove at runtime that it can:

1. discover a supported native chat or system-message endpoint;
2. send a bounded server-authored notice without polling or input simulation;
3. report delivery success or failure back to Sync;
4. fail closed to the application notification path when the game build or
   bridge is incompatible; and
5. preserve moderation, permissions, rate limits, and audit history.

Until those conditions are met, the Game and Both choices remain roadmap items
and the application notification path remains authoritative.
