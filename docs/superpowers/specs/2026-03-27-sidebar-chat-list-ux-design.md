# Sidebar Chat List UX Improvements

## Problem

Three usability issues in the sidebar chat list:

1. **Unread indicator overlaps project color** — the blue "unread" dot overrides the project color ball, losing project identity.
2. **No timestamp** — no way to see when a chat was last active without opening it.
3. **Static sort order** — chats are sorted by creation time. Active chats stay buried, making it hard to find recently active conversations.

## Design

### Chat item layout

```
[project-ball] [chat-name] [unread-dot?] [timestamp] [close-btn]
```

- `project-ball` — always shows project color (never overridden by unread state)
- `chat-name` — truncated with ellipsis, `flex: 1`
- `unread-dot` — 6px blue circle, shown only when `context.unread === true` and chat is not selected
- `timestamp` — relative time since `last_message`, right-aligned
- `close-btn` — existing delete button, visible on hover

### 1. Unread indicator

**Current**: `.chat-unread .project-color-ball` CSS rule overrides background to blue.

**Change**: Remove the `.chat-unread .project-color-ball` CSS rules. Add a separate `<span class="unread-dot">` element after the chat name, controlled by `x-show="context.unread && context.id !== $store.chats.selected"`.

Styling:
- `width: 6px; height: 6px; border-radius: 50%`
- `background-color: #4fc3f7` (dark mode), `#0288d1` (light mode)
- `flex-shrink: 0`

Keep `.chat-unread .chat-name { font-weight: 600 }` — bold name is a good secondary signal.

### 2. Relative timestamp

Add `<span class="chat-timestamp">` after the unread dot. Shows time since `last_message` in compact format.

Format rules:
| Elapsed | Display |
|---|---|
| < 60s | `Ns` (e.g. `5s`) |
| < 60m | `Nm` (e.g. `10m`) |
| < 24h | `Nh` (e.g. `5h`) |
| < 7d | `Nd` (e.g. `3d`) |
| >= 7d | `Nw` (e.g. `2w`) |

`title` attribute shows full localized datetime on hover (using `Date.toLocaleString()`).

The helper function `formatRelativeTime(isoString)` lives in `chats-store.js` (or inline in the template via Alpine `x-text`). It computes relative time from `context.last_message`.

Timestamps update on every `applyContexts` call (snapshot push, every ~2-5s during active sessions). No separate `setInterval` timer needed — staleness of a few seconds is acceptable.

Styling:
- `font-size: var(--font-size-xs, 0.7em)`
- `color: var(--color-secondary); opacity: 0.6`
- `flex-shrink: 0; margin-left: auto; padding: 0 4px`
- `white-space: nowrap`

### 3. Sort by last update

**Current** (line 47 of `chats-store.js`):
```javascript
this.contexts = contextsList.sort(
  (a, b) => (b.created_at || 0) - (a.created_at || 0)
);
```

**Change**: Sort by `last_message` descending. The `last_message` field is an ISO datetime string from `AgentContext.output()`. Convert to comparable values:
```javascript
this.contexts = contextsList.sort((a, b) => {
  const ta = a.last_message ? new Date(a.last_message).getTime() : 0;
  const tb = b.last_message ? new Date(b.last_message).getTime() : 0;
  return tb - ta;
});
```

Chats with more recent activity float to the top.

## Files changed

| File | Change |
|---|---|
| `webui/components/sidebar/chats/chats-list.html` | Add unread-dot span, timestamp span; remove `.chat-unread .project-color-ball` CSS; add new CSS for `.unread-dot` and `.chat-timestamp` |
| `webui/components/sidebar/chats/chats-store.js` | Change sort key from `created_at` to `last_message`; add `formatRelativeTime()` helper |

## Testing

Manual verification:
1. Create a new chat, send a message — verify timestamp shows `1s`, `2s`, etc.
2. Switch away and back — verify unread dot appears to the right of the name, project color ball keeps its color.
3. Send messages in different chats — verify most recently active chat moves to the top.
4. Hover over timestamp — verify full datetime tooltip.
5. Light mode — verify unread dot uses `#0288d1`.
