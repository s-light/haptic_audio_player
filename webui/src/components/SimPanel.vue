<template>
  <q-card
    class="sim-panel shadow-8"
    :style="{
      left: `${pos.x}px`,
      top: `${pos.y}px`,
      width: `${width ?? 260}px`
    }"
  >
    <q-bar
      class="bg-primary text-white cursor-move"
      v-touch-pan.prevent.mouse="onPan"
    >
      <q-icon :name="icon" />
      <div class="text-weight-medium">{{ title }}</div>
      <q-space />
      <q-btn
        dense
        flat
        round
        icon="close"
        @click="emit('close')"
        @mousedown.stop
        @touchstart.stop
      />
    </q-bar>
    <q-card-section class="q-pa-sm sim-body">
      <slot />
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
// Floating, draggable panel for the simulation helpers; the position is remembered per panel id.
import { reactive, watch } from "vue";
import type { TouchPanValue } from "quasar";

const props = defineProps<{
  id: string;
  title: string;
  icon: string;
  x: number;
  y: number;
  width?: number;
}>();
const emit = defineEmits<{ close: [] }>();

const KEY = `sim-panel-pos-${props.id}`;
const pos = reactive({ x: props.x, y: props.y });
try {
  const saved = JSON.parse(localStorage.getItem(KEY) ?? "null") as {
    x: number;
    y: number;
  } | null;
  if (saved) Object.assign(pos, saved);
} catch {
  /* no storage: keep the default position */
}

const clamp = (v: number, max: number) =>
  Math.max(0, Math.min(v, Math.max(0, max)));

function onPan(
  e: Parameters<Extract<TouchPanValue, (...args: never[]) => unknown>>[0]
) {
  pos.x = clamp(pos.x + (e.delta?.x ?? 0), window.innerWidth - 120);
  pos.y = clamp(pos.y + (e.delta?.y ?? 0), window.innerHeight - 60);
}

watch(pos, () => {
  try {
    localStorage.setItem(KEY, JSON.stringify(pos));
  } catch {
    /* ignore */
  }
});
</script>

<style scoped>
.sim-panel {
  position: fixed;
  z-index: 3000;
  max-width: calc(100vw - 16px);
}
.sim-body {
  max-height: calc(100vh - 150px);
  overflow: auto;
}
</style>
