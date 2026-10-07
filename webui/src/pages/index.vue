<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-primary">
      <q-toolbar>
        <q-toolbar-title>🎵 Haptic Player</q-toolbar-title>
        <q-chip
          v-if="!player.connected"
          dense
          color="negative"
          text-color="white"
          icon="wifi_off"
        >
          keine Verbindung zum Player
        </q-chip>
        <q-chip
          v-else-if="player.state.simulate"
          dense
          :color="player.state.audio === 'mpv' ? 'info' : 'warning'"
          text-color="white"
          :icon="player.state.audio === 'mpv' ? 'science' : 'volume_off'"
        >
          {{
            player.state.audio === "mpv"
              ? "Simulation"
              : "Simulation – kein Ton (mpv fehlt)"
          }}
        </q-chip>
        <q-chip
          v-else
          dense
          :color="player.state.nfc_ok ? 'positive' : 'grey'"
          text-color="white"
          icon="nfc"
        >
          {{ player.state.nfc_ok ? "Leser ok" : "kein Leser" }}
        </q-chip>
      </q-toolbar>
      <q-tabs align="left" dense no-caps inline-label>
        <q-route-tab to="/" icon="play_circle" label="Player" exact />
        <q-route-tab to="/library" icon="library_music" label="Bibliothek" />
        <q-route-tab to="/tags" icon="nfc" label="Tags" />
        <q-route-tab to="/recordings" icon="mic" label="Aufnahmen" />
        <q-route-tab to="/system" icon="settings" label="System" />
      </q-tabs>
    </q-header>

    <q-page-container>
      <q-banner v-if="!player.connected" class="bg-red-2 text-black" dense>
        Backend nicht erreichbar – läuft der Player (<code
          >python -m haptic_player</code
        >)? Im Dev-Modus muss er auf Port 8080 laufen. Es wird alle 2 s neu
        verbunden.
      </q-banner>
      <q-banner
        v-if="player.state.storage.mode === 'computer'"
        class="bg-orange-3 text-black"
        dense
      >
        <template #avatar><q-icon name="usb" /></template>
        Der Datenträger gehört gerade dem Computer – der Player pausiert. Am
        Computer auswerfen oder Kabel ziehen gibt ihn zurück.
        <template #action>
          <q-btn flat dense label="Zurück zum Player" @click="backToPlayer" />
        </template>
      </q-banner>
      <router-view />
    </q-page-container>

    <template v-if="player.state.simulate">
      <q-page-sticky position="bottom-right" :offset="[18, 18]">
        <div class="column q-gutter-sm items-end">
          <q-btn
            fab-mini
            color="secondary"
            icon="smart_display"
            @click="displayOpen = !displayOpen"
          >
            <q-tooltip anchor="center left" self="center right"
              >Display-Vorschau</q-tooltip
            >
          </q-btn>
          <q-btn fab color="secondary" icon="nfc" @click="tagOpen = !tagOpen">
            <q-tooltip anchor="center left" self="center right"
              >Tag auflegen (Simulation)</q-tooltip
            >
          </q-btn>
        </div>
      </q-page-sticky>
      <SimTagPanel v-if="tagOpen" :x="16" :y="110" @close="tagOpen = false" />
      <SimDisplayPanel
        v-if="displayOpen"
        :x="Math.max(16, innerWidth - 290)"
        :y="110"
        @close="displayOpen = false"
      />
    </template>
  </q-layout>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import SimDisplayPanel from "@/components/SimDisplayPanel.vue";
import SimTagPanel from "@/components/SimTagPanel.vue";
import { api } from "@/api";
import { usePlayerStore } from "@/stores/player";

const player = usePlayerStore();
onMounted(() => player.connect());
// simulation overlays (only when the backend runs with --simulate); open state survives reloads
const stored = (k: string) => {
  try {
    return localStorage.getItem(k) === "1";
  } catch {
    return false;
  }
};
const tagOpen = ref(stored("sim-tag-open"));
const displayOpen = ref(stored("sim-display-open"));
watch(tagOpen, v => {
  try {
    localStorage.setItem("sim-tag-open", v ? "1" : "0");
  } catch {
    /* ignore */
  }
});
watch(displayOpen, v => {
  try {
    localStorage.setItem("sim-display-open", v ? "1" : "0");
  } catch {
    /* ignore */
  }
});

const innerWidth = window.innerWidth;

const backToPlayer = () => api("POST", "/api/storage", { mode: "player" });
</script>
