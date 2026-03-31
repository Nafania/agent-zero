import { createStore } from "/js/AlpineStore.js";

const BUILTIN_COMMANDS = [
  {
    command: "/skill-install",
    description: "Install skills from GitHub (skills.sh)",
    usage: "/skill-install owner/repo[/skill-name]",
    isSkill: false,
  },
  {
    command: "/skill-list",
    description: "Show installed skills",
    usage: "/skill-list",
    isSkill: false,
  },
  {
    command: "/skill-remove",
    description: "Remove an installed skill",
    usage: "/skill-remove <skill-path>",
    isSkill: false,
  },
];

let _skillsCache = [];
let _cacheTimestamp = 0;
const CACHE_TTL_MS = 30_000;

async function _fetchInstalledSkills() {
  const now = Date.now();
  if (_skillsCache.length > 0 && now - _cacheTimestamp < CACHE_TTL_MS) {
    return _skillsCache;
  }

  try {
    const fetchApi = globalThis.fetchApi;
    if (!fetchApi) return _skillsCache;
    const resp = await fetchApi("/api/skills", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "list" }),
    });
    if (!resp.ok) return _skillsCache;
    const result = await resp.json();
    if (result.ok && result.data) {
      _skillsCache = result.data.map((s) => ({
        command: "/" + s.name,
        description: s.description || "Installed skill",
        usage: "/" + s.name,
        isSkill: true,
        skillPath: s.path,
      }));
      _cacheTimestamp = now;
    }
  } catch (e) {
    console.error("[slash] failed to fetch skills:", e);
  }
  return _skillsCache;
}

const model = {
  visible: false,
  commands: [],
  selectedIndex: 0,
  _allCommands: [],

  _slashPrefix: "",

  async onInput(value, cursorPos) {
    const textUpToCursor = typeof cursorPos === "number"
      ? value.slice(0, cursorPos)
      : value;

    const match = textUpToCursor.match(/(?:^|\s)(\/[^\s]*)$/);
    if (!match) {
      this.hide();
      return;
    }

    const typed = match[1].toLowerCase();
    this._slashPrefix = match[1];

    const skills = await _fetchInstalledSkills();
    this._allCommands = [...BUILTIN_COMMANDS, ...skills];

    this.commands = this._allCommands.filter((c) =>
      c.command.startsWith(typed)
    );

    if (this.commands.length === 0) {
      this.hide();
      return;
    }

    this.selectedIndex = 0;
    this.visible = true;
  },

  hide() {
    this.visible = false;
    this.commands = [];
    this.selectedIndex = 0;
  },

  invalidateCache() {
    _skillsCache = [];
    _cacheTimestamp = 0;
  },

  isInstalledSkill(name) {
    const normalized = name.toLowerCase();
    return _skillsCache.some(
      (s) => s.command === "/" + normalized || s.command === "/" + name
    );
  },

  selectCommand(index) {
    const cmd = this.commands[index];
    if (!cmd) return;

    const input = document.getElementById("chat-input");
    if (!input) return;

    const store = globalThis.Alpine?.store("chatInput");
    const prefix = this._slashPrefix || "/";
    const msg = store ? store.message : input.value;
    const prefixStart = msg.lastIndexOf(prefix);
    const before = prefixStart > 0 ? msg.slice(0, prefixStart) : "";
    const after = msg.slice(prefixStart + prefix.length);

    if (cmd.isSkill && store) {
      store.activeSkill = cmd.command.slice(1);
      store.message = (before + after).trim();
    } else if (store) {
      store.message = before + cmd.command + " " + after;
    } else {
      input.value = before + cmd.command + " " + after;
    }

    this.hide();
    input.focus();
  },

  onKeydown(event) {
    if (!this.visible) return false;

    switch (event.key) {
      case "ArrowUp":
        event.preventDefault();
        this.selectedIndex = Math.max(0, this.selectedIndex - 1);
        return true;

      case "ArrowDown":
        event.preventDefault();
        this.selectedIndex = Math.min(
          this.commands.length - 1,
          this.selectedIndex + 1
        );
        return true;

      case "Tab":
      case "Enter":
        if (this.commands.length > 0) {
          event.preventDefault();
          event.stopPropagation();
          this.selectCommand(this.selectedIndex);
          return true;
        }
        return false;

      case "Escape":
        event.preventDefault();
        this.hide();
        return true;

      default:
        return false;
    }
  },
};

const store = createStore("slashCommands", model);

export { store, BUILTIN_COMMANDS };
