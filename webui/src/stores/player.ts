import { defineStore, acceptHMRUpdate } from "pinia";
import { ref } from "vue";
import type { Snapshot } from "@/api";

/** Live player state pushed by the backend over the WebSocket (`/ws`); reconnects automatically. */
export const usePlayerStore = defineStore("player", () => {
  const connected = ref(false);
  const state = ref<Snapshot>({
    mode: "idle",
    player: {
      active: false,
      paused: false,
      file: "",
      title: "",
      position: 0,
      duration: 0,
      index: 0,
      count: 0,
      volume: 0,
      label: ""
    },
    now: { title: "", subtitle: "", cover: null, path: null },
    slot: 0,
    recording: { active: false, slot: null, elapsed: 0 },
    last_scan: null,
    learn: null,
    message: "",
    nfc_ok: false,
    simulate: false,
    audio: "none",
    storage: { mode: "player", host: false, available: false, error: "" },
    volume: 0,
    on_tag_remove: "none"
  });

  let socket: WebSocket | null = null;

  function connect() {
    if (socket) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    socket = ws;
    ws.onopen = () => (connected.value = true);
    ws.onmessage = e => {
      state.value = JSON.parse(e.data as string) as Snapshot;
    };
    ws.onclose = () => {
      connected.value = false;
      socket = null;
      setTimeout(connect, 2000);
    };
  }

  return { connected, state, connect };
});

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(usePlayerStore, import.meta.hot));
}
