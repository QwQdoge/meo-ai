import { useTranslation } from "react-i18next";
import SettingsCenter from "./SettingsCenter";
import PluginLibrary from "./PluginLibrary";
import navigation from "../../../../ui-schema/navigation.json";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMeoSession } from "./session";
import MeoChat from "./MeoChat";
import "./MeoDesktopApp.css";

type PrimaryMode = "chat" | "work" | "projects" | "skills";
type IconName =
  | "add"
  | "chat"
  | "work"
  | "projects"
  | "skills"
  | "settings"
  | "computer"
  | "menu"
  | "panel";

const icons: Record<IconName, React.ReactNode> = {
  add: <path d="M12 5v14M5 12h14" />,
  chat: <path d="M5 5h14v10H9l-4 4V5Z" />,
  work: (
    <>
      <path d="M8 7V5h8v2" />
      <rect x="4" y="7" width="16" height="11" rx="2" />
      <path d="M4 12h16" />
    </>
  ),
  projects: <path d="M3.5 6.5h6l2 2h9v10h-17v-12Z" />,
  skills: (
    <>
      <path d="M8.5 3.5h7v4h4v7h-4v4h-7v-4h-4v-7h4v-4Z" />
      <path d="M11 8.5h2v2h2v2h-2v2h-2v-2H9v-2h2v-2Z" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4" />
    </>
  ),
  computer: (
    <>
      <rect x="3" y="4" width="18" height="13" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </>
  ),
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  panel: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M15 4v16" />
    </>
  ),
};

function Icon({ name }: { name: IconName }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="meo-desktop-icon">
      <g
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {icons[name]}
      </g>
    </svg>
  );
}

const modeCopy: Record<
  Exclude<PrimaryMode, "chat">,
  { title: string; description: string; icon: IconName }
> = {
  work: {
    title: "Work",
    description:
      "Run agentic tasks on a chosen computer or environment. Local execution comes first; authenticated remote devices can join later.",
    icon: "work",
  },
  projects: {
    title: "Projects",
    description:
      "Keep related chats, files and Work together in one persistent place.",
    icon: "projects",
  },
  skills: {
    title: "Skills",
    description:
      "Use reusable capabilities without mixing them into model, memory or provider settings.",
    icon: "skills",
  },
};

export default function MeoDesktopApp() {
  const navigate = useNavigate();
  const { user } = useMeoSession();
  const [mode, setMode] = useState<PrimaryMode | "settings">("chat");
  const { t } = useTranslation();
  const [settingsDirty, setSettingsDirty] = useState(false);
  const [sidebarHidden, setSidebarHidden] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [historyTarget, setHistoryTarget] = useState<HTMLDivElement | null>(null);
  const [newChatRequest, setNewChatRequest] = useState(0);
  const [searchRequest, setSearchRequest] = useState(0);
  const [chatBusy, setChatBusy] = useState(false);
  const [compact, setCompact] = useState(
    () => window.matchMedia("(max-width: 759px)").matches,
  );
  const [mobileOpen, setMobileOpen] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 759px)");
    const update = () => {
      setCompact(media.matches);
      if (!media.matches) setMobileOpen(false);
    };
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!compact || !mobileOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    sidebarRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => previous?.focus();
  }, [compact, mobileOpen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.isComposing || event.repeat || event.altKey) return;
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (mode === "settings" && settingsDirty && !window.confirm(t("meo.settings.discardConfirm")))
          return;
        setMode("chat");
        setInspectorOpen(false);
        setSidebarHidden(false);
        if (compact) setMobileOpen(true);
        setSearchRequest((current) => current + 1);
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        if (chatBusy) return;
        if (
          mode === "settings" &&
          settingsDirty &&
          !window.confirm(t("meo.settings.discardConfirm"))
        )
          return;
        setMode("chat");
        setMobileOpen(false);
        setNewChatRequest((current) => current + 1);
        navigate("/new");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate, mode, settingsDirty, t, chatBusy, compact]);

  const accountLabel = useMemo(
    () => user?.name || user?.email || "Meo Account",
    [user],
  );

  const selectMode = (next: PrimaryMode | "settings") => {
    if (
      mode === "settings" &&
      settingsDirty &&
      !window.confirm(t("meo.settings.discardConfirm"))
    )
      return;
    setMode(next);
    setMobileOpen(false);
    setInspectorOpen(false);
  };

  return (
    <div className="meo-desktop-workspace" data-meo-desktop-parity="">
      <aside
        ref={sidebarRef}
        className={`meo-desktop-sidebar ${!compact && sidebarHidden ? "is-hidden" : ""} ${mobileOpen ? "is-mobile-open" : ""}`}
        role={compact && mobileOpen ? "dialog" : undefined}
        aria-modal={(compact && mobileOpen) || undefined}
        aria-label={t("meo.nav.navigation")}
        onKeyDown={(event) => {
          if (!compact || !mobileOpen) return;
          if (event.key === "Escape") {
            event.preventDefault();
            setMobileOpen(false);
          }
          if (event.key === "Tab") {
            const controls = Array.from(
              event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'),
            );
            const first = controls[0],
              last = controls[controls.length - 1];
            if (event.shiftKey && document.activeElement === first) {
              event.preventDefault();
              last?.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first?.focus();
            }
          }
        }}
      >
        <div className="meo-desktop-brand">
          <div className="meo-desktop-logo">AI</div>
          <div className="meo-desktop-brand-copy">
            <strong>Meo AI</strong>
            <span>A little help. More possibility.</span>
          </div>
        </div>

        <button
          className="meo-desktop-nav meo-desktop-nav-primary"
          type="button"
          disabled={chatBusy}
          onClick={() => {
            if (
              mode === "settings" &&
              settingsDirty &&
              !window.confirm(t("meo.settings.discardConfirm"))
            )
              return;
            if (chatBusy) return;
            setMode("chat");
            setMobileOpen(false);
            setNewChatRequest((current) => current + 1);
            navigate("/new");
          }}
        >
          <Icon name="add" />
          <span>{t("meo_web_new_chat")}</span>
        </button>

        <nav className="meo-desktop-nav-list" aria-label="Meo AI">
          {[...navigation.navigation]
            .filter((item) => item.placement === "primary")
            .sort((a, b) => a.order - b.order)
            .map(
              (item) =>
                [
                  item.id,
                  t(item.labelKey, { defaultValue: item.label }),
                  item.icon,
                ] as [PrimaryMode | "settings", string, IconName],
            )
            .map(([key, label, icon]) => (
              <button
                key={key}
                type="button"
                className={`meo-desktop-nav ${mode === key ? "is-active" : ""}`}
                onClick={() => selectMode(key)}
              >
                <Icon name={icon} />
                <span>{label}</span>
              </button>
            ))}
        </nav>

        {mode === "chat" && <div className="meo-desktop-history-slot" ref={setHistoryTarget} />}

        <div className="meo-desktop-sidebar-spacer" />

        {[...navigation.navigation]
          .filter((item) => item.placement === "secondary")
          .sort((a, b) => a.order - b.order)
          .map((item) => (
            <button
              key={item.id}
              className={`meo-desktop-nav ${mode === item.id ? "is-active" : ""}`}
              type="button"
              onClick={() => selectMode(item.id as PrimaryMode | "settings")}
            >
              <Icon name={item.icon as IconName} />
              <span>{t(item.labelKey, { defaultValue: item.label })}</span>
            </button>
          ))}

        <div className="meo-desktop-device-card">
          <Icon name="computer" />
          <div>
            <strong>This browser</strong>
            <span>{accountLabel}</span>
          </div>
          <i aria-label="Connected" />
        </div>
      </aside>

      {compact && mobileOpen && (
        <button
          className="meo-desktop-scrim"
          type="button"
          aria-label={t("meo.nav.close")}
          onClick={() => setMobileOpen(false)}
        />
      )}
      <section
        className="meo-desktop-main-pane"
        {...(compact && mobileOpen ? { inert: "" } : {})}
      >
        <header className="meo-desktop-header">
          <button
            className="meo-desktop-icon-button meo-desktop-sidebar-toggle"
            type="button"
            aria-label={t(
              compact
                ? "meo.nav.open"
                : sidebarHidden
                  ? "meo.nav.open"
                  : "meo.nav.close",
            )}
            onClick={() =>
              compact
                ? setMobileOpen(true)
                : setSidebarHidden((value) => !value)
            }
          >
            <Icon name="menu" />
          </button>
          <div className="meo-desktop-header-copy">
            <strong>
              {mode === "settings"
                ? t("meo.settings.title")
                : mode === "chat"
                  ? "Meo AI"
                  : modeCopy[mode].title}
            </strong>
            <span>
              {mode === "settings"
                ? t("meo.settings.general.description")
                : mode === "chat"
                  ? t("meo.nav.chat")
                  : mode === "work"
                    ? "Choose where Meo AI can act"
                    : mode === "projects"
                      ? "Persistent context for related work"
                      : "Reusable capabilities"}
            </span>
          </div>
          <button
            className={`meo-desktop-icon-button ${inspectorOpen ? "is-active" : ""}`}
            type="button"
            aria-label={t("meo_web_details")}
            onClick={() => setInspectorOpen((value) => !value)}
          >
            <Icon name="panel" />
          </button>
        </header>

        <div className="meo-desktop-content">
          <div
            className="meo-desktop-chat-host"
            style={mode === "chat" ? undefined : { display: "none" }}
          >
            <MeoChat
              historyTarget={historyTarget}
              newChatRequest={newChatRequest}
              searchRequest={searchRequest}
              onBusyChange={setChatBusy}
              onSelectConversation={() => setMobileOpen(false)}
            />
          </div>
          {mode === "settings" ? (
            <SettingsCenter onDirty={setSettingsDirty} />
          ) : mode === "skills" ? (
            <PluginLibrary />
          ) : mode !== "chat" ? (
            <ModeLanding mode={mode} />
          ) : null}
        </div>
      </section>

      {inspectorOpen && (
        <aside
          className="meo-desktop-inspector"
          aria-label={t("meo_web_details")}
        >
          <div className="meo-desktop-inspector-head">
            <div>
              <strong>{t("meo_web_details")}</strong>
              <span>{t("meo_web_details_subtitle")}</span>
            </div>
            <button
              type="button"
              onClick={() => setInspectorOpen(false)}
              aria-label={t("meo_web_close_details")}
            >
              ×
            </button>
          </div>
          <div className="meo-desktop-inspector-empty">
            <Icon name="panel" />
            <strong>{t("meo_web_details")}</strong>
            <span>{t("meo_web_details_unavailable")}</span>
          </div>
        </aside>
      )}
    </div>
  );
}

function ModeLanding({ mode }: { mode: Exclude<PrimaryMode, "chat"> }) {
  const { t } = useTranslation();
  const copy = modeCopy[mode];
  return (
    <section className="meo-desktop-mode-landing">
      <div className="meo-desktop-mode-icon">
        <Icon name={copy.icon} />
      </div>
      <h1>{copy.title}</h1>
      <p>{copy.description}</p>
      <p role="status">{t("meo.workspace.unavailable")}</p>
    </section>
  );
}
