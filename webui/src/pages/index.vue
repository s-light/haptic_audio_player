<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-primary">
      <q-toolbar>
        <q-toolbar-title>🎵 Haptic Player</q-toolbar-title>
        <q-chip
          dense
          :color="player.state.nfc_ok ? 'positive' : 'grey'"
          text-color="white"
          icon="nfc"
        >
          {{ player.state.nfc_ok ? "Leser ok" : "kein Leser" }}
        </q-chip>
        <q-icon :name="player.connected ? 'wifi' : 'wifi_off'" size="sm" />
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
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { usePlayerStore } from "@/stores/player";

const player = usePlayerStore();
onMounted(() => player.connect());
</script>
