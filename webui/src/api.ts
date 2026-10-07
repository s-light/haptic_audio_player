// Types of the haptic_player REST/WebSocket API (see haptic_player/controller.py snapshot() and web.py)
import { Notify } from "quasar";

export type Mode = "idle" | "playing" | "paused" | "recording";

export interface StorageState {
  mode: "player" | "computer";
  host: boolean; // a computer is connected to the USB port
  available: boolean; // USB storage mode is set up on the board
  error: string;
}
export type TagType = "album" | "track" | "record";

export interface PlayerState {
  active: boolean;
  paused: boolean;
  file: string;
  title: string;
  position: number;
  duration: number;
  index: number;
  count: number;
  volume: number;
  label: string;
}

export interface NowPlaying {
  title: string;
  subtitle: string;
  cover: string | null;
  path: string | null;
}

export interface LastScan {
  uid: string;
  known: boolean;
  time: number;
  type: TagType | null;
  target: string | null;
  label: string | null;
}

export interface LearnState {
  type: TagType;
  target: string;
  label: string;
}

export interface Snapshot {
  mode: Mode;
  player: PlayerState;
  now: NowPlaying;
  slot: number;
  recording: { active: boolean; slot: number | null; elapsed: number };
  last_scan: LastScan | null;
  learn: LearnState | null;
  message: string;
  nfc_ok: boolean;
  simulate: boolean;
  audio: "mpv" | "fake" | "none";
  storage: StorageState;
  volume: number;
  on_tag_remove: "none" | "pause" | "stop";
}

export interface Track {
  path: string;
  title: string;
  artist: string;
  duration: number;
}

export interface Album {
  path: string;
  title: string;
  single: boolean;
  cover: string | null;
  tracks: Track[];
}

export interface Tag {
  uid: string;
  type: TagType;
  target: string;
  label: string;
}

export interface RecordingSlot {
  slot: number;
  files: string[];
  tag: string | null;
}

export interface Settings {
  on_tag_remove: "none" | "pause" | "stop";
  volume_step: number;
  long_press_s: number;
  volume: number;
}

export interface SystemInfo {
  hostname: string;
  ip: string;
  disk: { total: number; free: number } | null;
  root_readonly: boolean | null;
  nfc_ok: boolean;
  simulate: boolean;
  data_dir: string;
}

export async function api<T = unknown>(
  method: "GET" | "POST" | "DELETE",
  url: string,
  body?: unknown
): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const r = await fetch(url, init);
  const data = (await r.json().catch(() => ({}))) as T & { error?: string };
  if (!r.ok) {
    const message = data.error ?? `Fehler ${r.status}`;
    Notify.create({ type: "negative", message });
    throw new Error(message);
  }
  return data;
}

export const control = (action: string, value?: number) =>
  api<Snapshot>("POST", "/api/control", { action, value });

export const fmtTime = (s: number) =>
  `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export const coverUrl = (path: string | null | undefined) =>
  path ? `/api/cover?path=${encodeURIComponent(path)}` : undefined;
