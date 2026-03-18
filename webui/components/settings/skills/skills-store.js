import { createStore } from "/js/AlpineStore.js";

const fetchApi = globalThis.fetchApi;

const model = {
    searchQuery: "",
    catalogResults: [],
    catalogLoading: false,
    catalogError: "",

    directSource: "",
    installLoading: false,
    installError: "",
    installResult: null,

    installed: [],
    installedLoading: false,
    installedError: "",

    projects: [],
    projectFilter: "",

    updateStatus: "",
    updateLoading: false,

    async init() {
        await Promise.all([this.loadInstalled(), this.loadProjects()]);
    },

    onClose() {
        this.catalogResults = [];
        this.catalogError = "";
        this.installResult = null;
        this.installError = "";
    },

    async searchCatalog() {
        const query = this.searchQuery.trim();
        if (!query) return;
        this.catalogLoading = true;
        this.catalogError = "";
        this.catalogResults = [];
        try {
            const resp = await fetchApi("/skills_catalog", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query }),
            });
            const result = await resp.json().catch(() => ({}));
            if (result.ok) {
                this.catalogResults = result.results || [];
            } else {
                this.catalogError = result.error || "Search failed";
            }
        } catch (e) {
            this.catalogError = e?.message || "Search failed";
        } finally {
            this.catalogLoading = false;
        }
    },

    async installSkill(source) {
        if (!source) return;
        this.installLoading = true;
        this.installError = "";
        this.installResult = null;
        try {
            const resp = await fetchApi("/skill_install", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ source }),
            });
            const result = await resp.json().catch(() => ({}));
            if (result.ok) {
                this.installResult = result;
                this.directSource = "";
                await this.loadInstalled();
                if (window.toastFrontendSuccess) {
                    window.toastFrontendSuccess(`Installed from ${source}`, "Skills");
                }
            } else {
                this.installError = result.error || "Install failed";
            }
        } catch (e) {
            this.installError = e?.message || "Install failed";
        } finally {
            this.installLoading = false;
        }
    },

    async installDirect() {
        const source = this.directSource.trim();
        if (!source) return;
        await this.installSkill(source);
    },

    async installFromCatalog(item) {
        await this.installSkill(item.source);
    },

    async loadInstalled() {
        this.installedLoading = true;
        this.installedError = "";
        try {
            const resp = await fetchApi("/skills", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    action: "list",
                    project_name: this.projectFilter || null,
                }),
            });
            const result = await resp.json().catch(() => ({}));
            if (result.ok) {
                this.installed = Array.isArray(result.data) ? result.data : [];
            } else {
                this.installedError = result.error || "Failed to load";
                this.installed = [];
            }
        } catch (e) {
            this.installedError = e?.message || "Failed to load";
            this.installed = [];
        } finally {
            this.installedLoading = false;
        }
    },

    async deleteSkill(skill) {
        if (!skill) return;
        try {
            const resp = await fetchApi("/skills", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "delete", skill_path: skill.path }),
            });
            const result = await resp.json().catch(() => ({}));
            if (!result.ok) throw new Error(result.error || "Delete failed");
            if (window.toastFrontendSuccess) {
                window.toastFrontendSuccess("Skill deleted", "Skills");
            }
            await this.loadInstalled();
        } catch (e) {
            if (window.toastFrontendError) {
                window.toastFrontendError(e?.message || "Delete failed", "Skills");
            }
        }
    },

    async loadProjects() {
        try {
            const resp = await fetchApi("/projects", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "list_options" }),
            });
            const data = await resp.json().catch(() => ({}));
            this.projects = data.ok ? (data.data || []) : [];
        } catch (e) {
            this.projects = [];
        }
    },

    async moveSkill(skill, targetProject) {
        if (!skill) return;
        const actualTarget = targetProject === "__global__" ? "" : targetProject;
        try {
            const resp = await fetchApi("/skills", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    action: "move",
                    skill_path: skill.path,
                    target_project: actualTarget,
                }),
            });
            const result = await resp.json().catch(() => ({}));
            if (!result.ok) throw new Error(result.error || "Move failed");
            if (window.toastFrontendSuccess) {
                window.toastFrontendSuccess(
                    `Skill moved to ${actualTarget || "global"}`,
                    "Skills",
                );
            }
            await this.loadInstalled();
        } catch (e) {
            if (window.toastFrontendError) {
                window.toastFrontendError(e?.message || "Move failed", "Skills");
            }
        }
    },

    async checkUpdates() {
        this.updateLoading = true;
        this.updateStatus = "";
        try {
            const resp = await fetchApi("/skills", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "check_updates" }),
            });
            const result = await resp.json().catch(() => ({}));
            if (result.ok) {
                this.updateStatus = result.data?.output || "Check complete";
            } else {
                this.updateStatus = result.error || "Check failed";
            }
        } catch (e) {
            this.updateStatus = e?.message || "Check failed";
        } finally {
            this.updateLoading = false;
        }
    },

    async updateAll() {
        this.updateLoading = true;
        this.updateStatus = "";
        try {
            const resp = await fetchApi("/skills", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "update" }),
            });
            const result = await resp.json().catch(() => ({}));
            if (result.ok) {
                this.updateStatus = result.data?.output || "Update complete";
                await this.loadInstalled();
            } else {
                this.updateStatus = result.error || "Update failed";
            }
        } catch (e) {
            this.updateStatus = e?.message || "Update failed";
        } finally {
            this.updateLoading = false;
        }
    },
};

const store = createStore("skillsStore", model);
export { store };
