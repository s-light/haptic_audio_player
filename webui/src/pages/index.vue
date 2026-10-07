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
          color="info"
          text-color="white"
          icon="science"
        >
          Simulation
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
  </q-layout>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { api } from "@/api";
import { usePlayerStore } from "@/stores/player";

const player = usePlayerStore();
onMounted(() => player.connect());
const backToPlayer = () => api("POST", "/api/storage", { mode: "player" });
</script>
