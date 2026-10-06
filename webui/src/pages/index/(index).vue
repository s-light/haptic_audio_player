<template>
  <q-page padding class="page">
    <div class="column q-gutter-md">
      <q-banner v-if="state.message" class="bg-orange-2 text-black" rounded>{{
        state.message
      }}</q-banner>
      <q-banner v-if="state.learn" class="bg-blue-2 text-black" rounded>
        <template #avatar><q-icon name="nfc" /></template>
        Warte auf Tag für „{{ state.learn.label || state.learn.target }}“ –
        bitte jetzt auflegen.
        <template #action>
          <q-btn
            flat
            label="Abbrechen"
            @click="api('DELETE', '/api/tags/learn')"
          />
        </template>
      </q-banner>

      <q-card>
        <q-card-section horizontal>
          <q-img
            v-if="state.now.cover"
            :src="coverUrl(state.now.cover)"
            style="width: 140px; min-height: 140px"
          />
          <q-card-section
            v-else
            class="flex flex-center bg-grey-3"
            style="width: 140px"
          >
            <q-icon
              :name="
                state.mode === 'recording'
                  ? 'fiber_manual_record'
                  : 'music_note'
              "
              size="64px"
              :color="state.mode === 'recording' ? 'negative' : 'grey-6'"
            />
          </q-card-section>
          <q-card-section class="col">
            <q-badge :color="badge.color">{{ badge.text }}</q-badge>
            <div class="text-h6 q-mt-sm">
              {{
                state.mode === "recording"
                  ? "Aufnahme läuft"
                  : state.now.title || "Tag auflegen …"
              }}
            </div>
            <div class="text-subtitle2 text-grey">{{ state.now.subtitle }}</div>
            <div v-if="state.player.count > 1" class="text-caption">
              Titel {{ state.player.index + 1 }} / {{ state.player.count }}
            </div>
          </q-card-section>
        </q-card-section>

        <q-card-section v-if="state.mode !== 'recording'">
          <q-slider
            :model-value="state.player.position"
            :max="Math.max(state.player.duration, 1)"
            :disable="!state.player.active"
            color="primary"
            @change="(v: number | null) => control('seek', v ?? 0)"
          />
          <div class="row justify-between text-caption">
            <span>{{ fmtTime(state.player.position) }}</span>
            <span>{{ fmtTime(state.player.duration) }}</span>
          </div>
        </q-card-section>
        <q-card-section v-else class="text-h5 text-center">
          {{ fmtTime(state.recording.elapsed) }} (Slot
          {{ state.recording.slot }})
        </q-card-section>

        <q-card-actions align="center" class="q-gutter-sm">
          <q-btn
            round
            size="lg"
            icon="skip_previous"
            @click="control('prev')"
          />
          <q-btn
            round
            size="xl"
            color="primary"
            :icon="state.mode === 'playing' ? 'pause' : 'play_arrow'"
            @click="control('play_pause')"
          />
          <q-btn round size="lg" icon="stop" @click="control('stop')" />
          <q-btn round size="lg" icon="skip_next" @click="control('next')" />
          <q-btn
            round
            size="lg"
            :color="state.mode === 'recording' ? 'negative' : 'red-3'"
            icon="mic"
            @click="control('record')"
          >
            <q-tooltip>Aufnahme starten/stoppen</q-tooltip>
          </q-btn>
        </q-card-actions>
      </q-card>

      <q-card>
        <q-card-section>
          <div class="row items-center q-gutter-md">
            <q-icon name="volume_up" size="sm" />
            <q-slider
              class="col"
              :model-value="state.player.volume"
              :min="0"
              :max="100"
              label
              @change="(v: number | null) => control('volume', v ?? 0)"
            />
          </div>
          <div class="row items-center q-gutter-md">
            <q-icon name="mic" size="sm" />
            <q-btn-toggle
              :model-value="state.slot"
              no-caps
              dense
              toggle-color="primary"
              :options="slotOptions"
              @update:model-value="(v: number) => control('select_slot', v)"
            />
          </div>
        </q-card-section>
      </q-card>

      <q-card v-if="state.last_scan">
        <q-card-section>
          <div class="text-subtitle2">Zuletzt gelesener Tag</div>
          <code>{{ state.last_scan.uid }}</code>
          <q-badge
            class="q-ml-sm"
            :color="state.last_scan.known ? 'positive' : 'orange'"
          >
            {{
              state.last_scan.known
                ? `${state.last_scan.type}: ${state.last_scan.label || state.last_scan.target}`
                : "unbekannt"
            }}
          </q-badge>
        </q-card-section>
        <q-card-actions v-if="!state.last_scan.known">
          <q-btn
            flat
            color="primary"
            icon="add_link"
            label="Zuweisen"
            :to="{ path: '/tags', query: { uid: state.last_scan.uid } }"
          />
        </q-card-actions>
      </q-card>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { storeToRefs } from "pinia";
import { api, control, coverUrl, fmtTime, type Mode } from "@/api";
import { usePlayerStore } from "@/stores/player";

const { state } = storeToRefs(usePlayerStore());

const BADGES: Partial<Record<Mode, { text: string; color: string }>> = {
  playing: { text: "spielt", color: "positive" },
  paused: { text: "pausiert", color: "warning" },
  recording: { text: "Aufnahme", color: "negative" }
};
const badge = computed(
  () => BADGES[state.value.mode] ?? { text: "bereit", color: "grey" }
);

const slotOptions = [
  { label: "kein Slot", value: 0 },
  ...[1, 2, 3, 4, 5, 6, 7, 8].map(n => ({ label: String(n), value: n }))
];
</script>

<style scoped>
.page {
  max-width: 900px;
  margin: 0 auto;
}
</style>
