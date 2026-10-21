<template>
  <SimPanel
    id="display"
    title="Simulation: Display"
    icon="smart_display"
    :x="x"
    :y="y"
    @close="emit('close')"
  >
    <img
      :src="`/api/display.png?t=${stamp}`"
      width="240"
      height="320"
      class="display-frame"
      alt="Display-Vorschau"
      @click="tap"
      @error="failed = true"
      @load="failed = false"
    />
    <div v-if="failed" class="text-caption text-grey q-mt-xs"
      >noch kein Bild – Display in der Konfiguration aktiviert?</div
    >
  </SimPanel>
</template>

<script setup lang="ts">
// The backend writes the rendered frame to /api/display.png (240x320 as the real panel); reload it whenever
// the player state changes, plus once a second for the progress bar.
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import SimPanel from "@/components/SimPanel.vue";
import { usePlayerStore } from "@/stores/player";
import { api } from "@/api";

defineProps<{ x: number; y: number }>();
const emit = defineEmits<{ close: [] }>();

const { state } = storeToRefs(usePlayerStore());
const stamp = ref(Date.now());
const failed = ref(false);
let timer: ReturnType<typeof setInterval> | undefined;

const refresh = () => {
  stamp.value = Date.now();
};
onMounted(() => {
  timer = setInterval(refresh, 1000);
});
onBeforeUnmount(() => clearInterval(timer));
// a click acts like a finger on the on-screen buttons (image pixels = panel pixels)
const tap = (e: MouseEvent) => {
  const img = e.currentTarget as HTMLImageElement;
  const r = img.getBoundingClientRect();
  void api("POST", "/api/dev/touch", {
    x: Math.round(((e.clientX - r.left) / r.width) * 240),
    y: Math.round(((e.clientY - r.top) / r.height) * 320)
  });
};
// small delay: the backend renders the frame a moment after it publishes the state
watch(state, () => setTimeout(refresh, 150));
</script>

<style scoped>
.display-frame {
  display: block;
  cursor: pointer;
  border: 1px solid #888;
  border-radius: 4px;
  background: #000;
}
</style>
