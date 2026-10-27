import React from "react";
import {
  Box, Brain, Check, ChevronDown, ChevronRight, CircleAlert, CircleCheck, CircleX, Cloud, Copy, FileText, Globe,
  Image as ImageIcon, Info, Lightbulb, Loader, Mail, OctagonAlert, Pencil, RefreshCw, Search, Send, Shield,
  SlidersHorizontal, Sparkles, TriangleAlert, Workflow, Briefcase, Folder, MessageSquare, Menu, MoreVertical, Monitor,
  PanelLeftClose, PanelLeftOpen, Paperclip, Plus, Puzzle, Settings, ArrowUp, Square, X, type LucideIcon,
} from "lucide-react";

// The core names icons with Material Symbols names (desktop and Android draw those). The Web draws
// the same names with Lucide so one line style runs through the whole page.
const MAP: Record<string, LucideIcon> = {
  cloud: Cloud, deployed_code: Box, tune: SlidersHorizontal, psychology: Brain, image: ImageIcon, description: FileText,
  info: Info, lightbulb: Lightbulb, priority_high: CircleAlert, warning: TriangleAlert, report: OctagonAlert,
  check_circle: CircleCheck, check: Check, error: CircleX, language: Globe, account_tree: Workflow, shield: Shield,
  search: Search, content_copy: Copy, edit: Pencil, refresh: RefreshCw, mail: Mail, send: Send, auto_awesome: Sparkles,
  expand_more: ChevronDown, chat: MessageSquare, work: Briefcase, skills: Puzzle, projects: Folder, settings: Settings,
  add: Plus, menu: Menu, more: MoreVertical, attach: Paperclip, arrow_up: ArrowUp, stop: Square, close: X, device: Monitor,
  collapse: PanelLeftClose, expand: PanelLeftOpen, chevron_right: ChevronRight, progress_activity: Loader,
};

export function hasIcon(name: string): boolean {
  return name in MAP;
}

export function Icon({ name, size = 16, className }: { name: string; size?: number; className?: string }) {
  const Glyph = MAP[name];
  return Glyph ? <Glyph size={size} strokeWidth={1.75} className={`core-icon${className ? " " + className : ""}`} aria-hidden /> : null;
}
